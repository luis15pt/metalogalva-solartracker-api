"""Main FastAPI application for the Solar Tracker API."""

import asyncio
import logging
import time
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import HTMLResponse

from .config import settings
from .models import (
    TrackerStatus,
    CommandResponse,
    MoveCommand,
    SetWindThresholdCommand,
    WindSettings,
    SetGPSLocationCommand,
    SetDateTimeCommand,
    PresetPosition,
    Direction,
    OperatingMode,
    ConnectionStatus,
    AlarmEntry,
    ObservedLimits,
    GotoCommand,
)
from .serial_handler import serial_handler
from .mqtt_handler import mqtt_handler
from . import protocol
from .protocol import Cmd
from .inverter import router as inverter_router
from .goto import GotoController, GotoError

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# File logging for persistent state change logs
import os
from logging.handlers import RotatingFileHandler
_log_dir = settings.data_dir
os.makedirs(_log_dir, exist_ok=True)
_file_handler = RotatingFileHandler(
    os.path.join(_log_dir, "solartracker.log"),
    maxBytes=20 * 1024 * 1024,  # 20MB per file
    backupCount=5,               # Keep 5 rotated files (100MB total)
)
_file_handler.setLevel(logging.INFO)
_file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(_file_handler)

# WebSocket connections for live updates
websocket_connections: List[WebSocket] = []

# Current tracker status (updated from the tracker's status broadcasts)
current_status = TrackerStatus()

# Validating frame decoder for the serial byte stream
decoder = protocol.FrameDecoder()

# Last logged state, for change-only logging
_last_logged: dict = {}

# Ask the tracker for its wind settings after the next status frame (set on every (re)connect)
_need_wind_read = True

# Observed limits persistence
LIMITS_FILE = os.path.join(settings.data_dir, "observed_limits.json")


def load_observed_limits() -> ObservedLimits:
    """Load observed limits from persistent storage."""
    import json
    import os
    try:
        if os.path.exists(LIMITS_FILE):
            with open(LIMITS_FILE, "r") as f:
                data = json.load(f)
            logger.info(f"Loaded observed limits: {data}")
            return ObservedLimits(**data)
    except Exception as e:
        logger.warning(f"Failed to load observed limits: {e}")
    return ObservedLimits()


def save_observed_limits(limits: ObservedLimits):
    """Save observed limits to persistent storage."""
    import json
    import os
    try:
        os.makedirs(os.path.dirname(LIMITS_FILE), exist_ok=True)
        with open(LIMITS_FILE, "w") as f:
            json.dump(limits.model_dump(mode="json"), f, default=str)
    except Exception as e:
        logger.warning(f"Failed to save observed limits: {e}")


def update_observed_limits(horizontal: float | None, vertical: float | None):
    """Update observed min/max limits from a new position reading."""
    limits = current_status.observed_limits
    changed = False

    if horizontal is not None:
        if limits.horizontal_min is None or horizontal < limits.horizontal_min:
            limits.horizontal_min = horizontal
            changed = True
        if limits.horizontal_max is None or horizontal > limits.horizontal_max:
            limits.horizontal_max = horizontal
            changed = True

    if vertical is not None:
        if limits.vertical_min is None or vertical < limits.vertical_min:
            limits.vertical_min = vertical
            changed = True
        if limits.vertical_max is None or vertical > limits.vertical_max:
            limits.vertical_max = vertical
            changed = True

    if changed:
        now = datetime.now(timezone.utc)
        if limits.first_seen is None:
            limits.first_seen = now
        limits.last_updated = now
        save_observed_limits(limits)


async def broadcast_status():
    """Broadcast status to all WebSocket clients."""
    if not websocket_connections:
        return

    message = current_status.model_dump_json()
    disconnected = []

    for ws in websocket_connections:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.append(ws)

    for ws in disconnected:
        try:
            websocket_connections.remove(ws)
        except ValueError:
            pass  # Already removed by websocket_endpoint finally block


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _log_state_changes(st: dict, raw: bytes):
    """Log when mode, alarms or wind alarm state change."""
    global _last_logged
    state = {
        "mode": "manual" if st["manual"] else "auto",
        "alarm_word": f"0x{st['alarm_word']:04x}",
    }
    changed = [f"{k}: {_last_logged.get(k)}->{v}" for k, v in state.items() if _last_logged.get(k) != v]
    if changed:
        logger.info(
            f"STATE CHANGE: {', '.join(changed)} | alarms={[a.code for a in st['alarms']]} "
            f"panel=(azi {st['panel_azimuth']}, alt {st['panel_altitude']}) "
            f"sun=(azi {st['sun_azimuth']}, alt {st['sun_altitude']}) wind={st['wind_speed']} "
            f"enc=(rot {st['rotation_encoder']}, tilt {st['tilt_encoder']}) frame={raw.hex()}"
        )
    _last_logged = state


def _apply_status(st: dict):
    """Copy a decoded status frame into current_status."""
    cs = current_status
    cs.mode = OperatingMode.MANUAL if st["manual"] else OperatingMode.AUTOMATIC
    cs.position.horizontal = st["panel_azimuth"]
    cs.position.vertical = st["panel_altitude"]
    update_observed_limits(st["panel_azimuth"], st["panel_altitude"])
    cs.sun_position.azimuth = st["sun_azimuth"]
    cs.sun_position.altitude = st["sun_altitude"]
    cs.wind_speed = st["wind_speed"]
    cs.tilt_encoder = st["tilt_encoder"]
    cs.rotation_encoder = st["rotation_encoder"]
    cs.utc_time = st["clock"]
    if st["version"]:
        cs.firmware_version = st["version"]

    log_times = {e["code"]: e["timestamp"] for e in st["alarm_log"]}
    cs.alarm_word = st["alarm_word"]
    cs.active_alarms = [
        AlarmEntry(code=a.code, message=a.message, severity=a.severity, timestamp=log_times.get(a.code))
        for a in st["alarms"]
    ]
    cs.alarms = [a.code for a in st["alarms"] if a.severity != "info"]
    cs.limit_switches = [a.code for a in st["alarms"] if a.severity == "info"]
    # Limit switches are normal states; keep only real alarms in the log
    cs.alarm_history = sorted(
        (AlarmEntry(**e) for e in st["alarm_log"] if e["severity"] != "info"),
        key=lambda e: e.timestamp, reverse=True,
    )
    cs.last_frame = _utcnow()
    cs.link_ok = True


async def _goto_changed():
    current_status.goto = goto.state
    if not goto.state.active and goto.state.phase == "failed" and current_status.link_ok:
        await _verified_stop()
    await broadcast_status()


goto = GotoController(serial_handler, lambda: current_status, _goto_changed)


# Verified stop. A single frame can be lost on the serial line (seen on the real
# tracker), and a lost stop leaves the motor running. So: send stop twice, then
# watch the position and repeat the stop until the panel is actually still.
_frame_event = asyncio.Event()
_stop_guard_task: asyncio.Task | None = None


def _panel_pos():
    p = current_status.position
    return (p.vertical or 0.0, p.horizontal or 0.0)


async def _stop_guard():
    try:
        prev, still = None, 0
        for i in range(15):
            _frame_event.clear()
            await asyncio.wait_for(_frame_event.wait(), 4)
            if current_status.mode != OperatingMode.MANUAL:
                return  # in automatic the tracker moves by itself
            pos = _panel_pos()
            if prev is not None:
                if all(abs(a - b) < 0.02 for a, b in zip(pos, prev)):
                    still += 1
                    if still >= 2:
                        return
                else:
                    still = 0
                    if i >= 2:
                        logger.warning(f"Panel still moving after stop (at {pos}), repeating stop")
                        await serial_handler.stop()
            prev = pos
        logger.error("Panel did not stop after repeated stop commands")
    except asyncio.TimeoutError:
        logger.warning("Stop could not be verified: no status frames")


def _disarm_stop_guard():
    """A new movement was requested; stop watching for a standstill."""
    global _stop_guard_task
    if _stop_guard_task and not _stop_guard_task.done():
        _stop_guard_task.cancel()
    _stop_guard_task = None


async def _verified_stop() -> bool:
    """Send stop (twice) and keep checking until the panel is still."""
    global _stop_guard_task
    _disarm_stop_guard()
    ok = await serial_handler.stop()
    await asyncio.sleep(0.25)
    ok = await serial_handler.stop() or ok
    _stop_guard_task = asyncio.create_task(_stop_guard())
    return ok


async def _move(direction: Direction, start: bool = True) -> bool:
    """Start a jog, or stop with verification."""
    if not start:
        return await _verified_stop()
    _disarm_stop_guard()
    return await serial_handler.move(direction, start=True)


# Hold-to-move: the browser refreshes the jog while an arrow is held. If the
# refreshes stop (released, page closed, WiFi dropped) the Pi sends stop itself.
JOG_KEEPALIVE = 2.0   # seconds a jog survives without a refresh
JOG_MIN_RUN = 2.0     # the tracker needs ~1.5 s to start moving, so a tap runs this long
_jog = {"direction": None, "started": 0.0, "deadline": 0.0}


async def _jog_watchdog(token: float):
    """Send stop once the current jog's deadline passes; retry a start that had no effect."""
    start_pos, retried = _panel_pos(), False
    while _jog["direction"] is not None and _jog["started"] == token:
        now = time.monotonic()
        if now >= _jog["deadline"]:
            _jog["direction"] = None
            await _verified_stop()
            return
        if not retried and now - token > 3.5 and _panel_pos() == start_pos:
            retried = True
            logger.warning("Jog had no effect, repeating the command")
            await serial_handler.move(_jog["direction"], start=True)
        await asyncio.sleep(0.1)


async def _preempt():
    """Another command takes over: forget any held jog and abort a running go-to."""
    _jog["direction"] = None
    _disarm_stop_guard()
    await goto.cancel("Stopped by another command")


async def on_serial_data(data: bytes):
    """Handle bytes received from the serial port."""
    updated = False
    for frame in decoder.feed(data):
        if frame.cmd == Cmd.STATUS:
            st = protocol.parse_status(frame)
            if st is None:
                logger.warning(f"Unparseable status frame: {frame.raw.hex()}")
                continue
            global _need_wind_read
            _log_state_changes(st, frame.raw)
            _apply_status(st)
            goto.notify_frame()
            _frame_event.set()
            updated = True
            if _need_wind_read:
                # Read-only query; the reply (0x51) fills in wind_settings
                _need_wind_read = False
                asyncio.create_task(serial_handler.read_wind_settings())
        elif frame.cmd == Cmd.PARAM_REPLY:
            reply = protocol.parse_param_reply(frame)
            logger.info(f"Parameter reply: {reply}")
            if reply and reply["param"] == "wind":
                current_status.wind_settings = WindSettings(
                    trip=reply["trip"], release=reply["release"],
                    hold_minutes=reply["hold_minutes"], count=reply["count"],
                )
                current_status.max_wind_threshold = reply["trip"]
                updated = True
        elif frame.cmd == Cmd.ACK:
            logger.info("Tracker acknowledged command")
        elif frame.src == protocol.ADDR_TRACKER:
            logger.info(f"Tracker frame cmd=0x{frame.cmd:02x} data={frame.data.hex()}")

    current_status.frames_ok = decoder.frames_ok
    current_status.frames_bad = decoder.frames_bad
    if updated:
        await broadcast_status()
        await mqtt_handler.publish_status(current_status)


async def housekeeping_loop():
    """Track link health and reconnect the serial port when it drops."""
    global _need_wind_read
    while True:
        try:
            if not serial_handler.is_connected:
                decoder.reset()
                if await serial_handler.connect():
                    _need_wind_read = True
                    logger.info(f"Serial reconnected to {settings.serial_port}")

            cs = current_status
            cs.connection = serial_handler.get_status()
            was_ok = cs.link_ok
            cs.link_ok = (
                serial_handler.is_connected and cs.last_frame is not None
                and (_utcnow() - cs.last_frame).total_seconds() < settings.link_timeout
            )
            if was_ok and not cs.link_ok:
                logger.warning("No status frames from tracker: link stale")
            await broadcast_status()
            await mqtt_handler.publish_status(cs)
        except Exception as e:
            logger.error(f"Housekeeping error: {e}")
        await asyncio.sleep(settings.reconnect_interval if not serial_handler.is_connected else 5)


async def _set_wind(trip: int, release: int | None = None) -> bool:
    """Write the wind trip threshold, keeping the other stored settings."""
    ws = current_status.wind_settings
    if release is None:
        release = ws.release if ws and ws.release <= trip else round(trip * 0.75)
    release = min(release, trip)
    ok = await serial_handler.write_wind_settings(
        trip, release, ws.hold_minutes if ws else 10, ws.count if ws else 1
    )
    if ok:
        await asyncio.sleep(1.0)
        await serial_handler.read_wind_settings()  # confirm what the tracker stored
    return ok


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Solar Tracker API...")

    # Load persisted observed limits
    current_status.observed_limits = load_observed_limits()

    # Set up serial handler callback
    serial_handler.set_data_callback(on_serial_data)

    # Set up MQTT callbacks

    mqtt_handler.set_callbacks(
        on_move=lambda d, s: _move(d, s),
        on_mode=lambda auto: serial_handler.set_mode(auto),
        on_clear_alarms=lambda: serial_handler.clear_alarms(),
        on_set_wind=lambda v: _set_wind(v),
        on_go_home=lambda: serial_handler.go_to_position(PresetPosition.MAINTENANCE),
        on_go_stow=lambda: serial_handler.go_to_position(PresetPosition.HORIZONTAL),
        on_set_gps=lambda lat, lon: serial_handler.set_gps_location(lat, lon),
        on_sync_datetime=lambda: serial_handler.set_datetime(_utcnow()),
    )

    # Connect to MQTT
    mqtt_connected = await mqtt_handler.connect()
    if mqtt_connected:
        logger.info("MQTT connected")
    else:
        logger.warning("MQTT connection failed - continuing without MQTT")

    # Try to auto-connect to serial port
    try:
        serial_connected = await serial_handler.connect()
        if serial_connected:
            logger.info(f"Serial connected to {settings.serial_port}")
        else:
            logger.warning("Serial connection failed - manual connection required")
    except Exception as e:
        logger.warning(f"Serial auto-connect failed: {e}")

    # Link watchdog / reconnect task
    poll_task = asyncio.create_task(housekeeping_loop())

    yield

    # Cleanup
    logger.info("Shutting down Solar Tracker API...")
    poll_task.cancel()
    try:
        await poll_task
    except asyncio.CancelledError:
        pass

    await goto.cancel("Shutting down")
    await serial_handler.disconnect()
    await mqtt_handler.disconnect()


# Create FastAPI app
app = FastAPI(
    title="Solar Tracker API",
    description="REST API for controlling solar tracking systems",
    version="0.2.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(inverter_router)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")


# =============================================================================
# Health & Info Endpoints
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "serial_connected": serial_handler.is_connected,
        "tracker_link_ok": current_status.link_ok,
        "mqtt_connected": mqtt_handler.is_connected,
    }


@app.get("/info")
async def get_info():
    """Get API information."""
    return {
        "name": "Solar Tracker API",
        "version": "0.2.0",
        "commands": [c.name for c in Cmd],
        "alarms": [{"bit": a.bit, "code": a.code, "message": a.message, "severity": a.severity}
                   for a in protocol.ALARMS],
    }


# =============================================================================
# Serial Connection Endpoints
# =============================================================================

@app.get("/serial/ports")
async def list_serial_ports():
    """List available serial ports."""
    return {"ports": serial_handler.list_ports()}


@app.get("/serial/status", response_model=ConnectionStatus)
async def get_serial_status():
    """Get serial connection status."""
    return serial_handler.get_status()


@app.post("/serial/connect", response_model=CommandResponse)
async def connect_serial(port: str = None, baudrate: int = None):
    """Connect to serial port."""
    success = await serial_handler.connect(port, baudrate)
    return CommandResponse(
        success=success,
        message="Connected" if success else "Connection failed",
    )


@app.post("/serial/disconnect", response_model=CommandResponse)
async def disconnect_serial():
    """Disconnect from serial port."""
    success = await serial_handler.disconnect()
    return CommandResponse(
        success=success,
        message="Disconnected" if success else "Disconnect failed",
    )


@app.post("/serial/send")
async def send_raw(data: str):
    """Send raw hex data to serial port (for debugging)."""
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    try:
        raw_bytes = bytes.fromhex(data)
        frame = protocol.parse_frame(raw_bytes)
        if frame is None:
            raise HTTPException(status_code=400, detail="Not a valid frame (length or checksum)")
        if frame.cmd in protocol.FORBIDDEN_COMMANDS:
            raise HTTPException(status_code=400, detail="Firmware-update commands are blocked")
        success = await serial_handler.send(raw_bytes)
        return CommandResponse(
            success=success,
            message=f"Sent {len(raw_bytes)} bytes" if success else "Send failed",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid hex data: {e}")


# =============================================================================
# Tracker Control Endpoints
# =============================================================================

@app.get("/tracker/status", response_model=TrackerStatus)
async def get_tracker_status():
    """Get current tracker status."""
    current_status.connection = serial_handler.get_status()
    return current_status


@app.post("/tracker/move", response_model=CommandResponse)
async def move_tracker(command: MoveCommand):
    """Move tracker in a direction."""
    await _preempt()
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    success = await _move(command.direction, start=True)

    # If duration specified, stop after delay
    if success and command.duration_ms:
        async def stop_after_delay():
            await asyncio.sleep(command.duration_ms / 1000)
            await _verified_stop()

        asyncio.create_task(stop_after_delay())

    return CommandResponse(
        success=success,
        message=f"Moving {command.direction.value}" if success else "Command failed",
    )


@app.post("/tracker/move/{direction}/start", response_model=CommandResponse)
async def start_move(direction: Direction):
    """Start moving in a direction (hold)."""
    await _preempt()
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    success = await _move(direction, start=True)
    return CommandResponse(
        success=success,
        message=f"Started moving {direction.value}" if success else "Command failed",
    )


@app.post("/tracker/move/{direction}/stop", response_model=CommandResponse)
async def stop_move(direction: Direction):
    """Stop moving in a direction."""
    await _preempt()
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    success = await _verified_stop()
    return CommandResponse(
        success=success,
        message="Stopped" if success else "Command failed",
    )


@app.post("/tracker/jog/release", response_model=CommandResponse)
async def jog_release():
    """The arrow was released: stop, but not before the minimum run time."""
    if _jog["direction"] is not None:
        _jog["deadline"] = max(time.monotonic(), _jog["started"] + JOG_MIN_RUN)
    return CommandResponse(success=True, message="Released")


@app.post("/tracker/jog/{direction}", response_model=CommandResponse)
async def jog(direction: Direction):
    """
    Hold-to-move. Call repeatedly (about once a second) while the arrow is held.

    The first call starts the movement; later calls only keep it alive. Without a
    refresh for 2 seconds the Pi sends stop. /tracker/stop stops immediately.
    """
    if not serial_handler.is_connected or not current_status.link_ok:
        raise HTTPException(status_code=400, detail="No link to the tracker")
    if current_status.mode != OperatingMode.MANUAL:
        raise HTTPException(status_code=409, detail="Switch to manual mode first")
    await goto.cancel("Stopped by another command")
    now = time.monotonic()
    if _jog["direction"] != direction:
        _disarm_stop_guard()
        if not await serial_handler.move(direction, start=True):
            _jog["direction"] = None
            raise HTTPException(status_code=500, detail="Command failed")
        _jog.update(direction=direction, started=now, deadline=now + JOG_KEEPALIVE)
        asyncio.create_task(_jog_watchdog(now))
    else:
        _jog["deadline"] = now + JOG_KEEPALIVE
    return CommandResponse(success=True, message=f"Moving {direction.value}")


@app.post("/tracker/stop", response_model=CommandResponse)
async def stop_all():
    """Stop all movement."""
    await _preempt()
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    success = await _verified_stop()
    return CommandResponse(
        success=success,
        message="Stopped" if success else "Command failed",
    )


@app.post("/tracker/mode/{mode}", response_model=CommandResponse)
async def set_mode(mode: OperatingMode):
    """Set operating mode."""
    await _preempt()
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    automatic = mode == OperatingMode.AUTOMATIC
    logger.info(f"Mode endpoint called: {mode.value} (automatic={automatic})")
    success = await serial_handler.set_mode(automatic)

    # The tracker confirms the new mode in its next status broadcast

    return CommandResponse(
        success=success,
        message=f"Mode command sent: {mode.value}" if success else "Command failed",
    )


@app.post("/tracker/alarms/clear", response_model=CommandResponse)
async def clear_alarms():
    """Clear all alarms."""
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    success = await serial_handler.clear_alarms()

    return CommandResponse(
        success=success,
        message="Alarms cleared" if success else "Command failed",
    )


@app.post("/tracker/wind", response_model=CommandResponse)
async def set_wind_threshold(command: SetWindThresholdCommand):
    """Set the wind trip threshold (km/h). Writes the tracker's flash."""
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    success = await _set_wind(command.max_wind, command.release)
    return CommandResponse(
        success=success,
        message=f"Wind threshold {command.max_wind} km/h sent" if success else "Command failed",
    )


@app.post("/tracker/wind/read", response_model=CommandResponse)
async def read_wind_settings():
    """Ask the tracker for its stored wind settings (appear in status.wind_settings)."""
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")
    success = await serial_handler.read_wind_settings()
    return CommandResponse(success=success, message="Requested" if success else "Command failed")


@app.post("/tracker/gps", response_model=CommandResponse)
async def set_gps_location(command: SetGPSLocationCommand):
    """Set GPS location for sun position calculations."""
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    success = await serial_handler.set_gps_location(command.latitude, command.longitude)

    return CommandResponse(
        success=success,
        message=f"GPS set to {command.latitude:.4f}, {command.longitude:.4f}" if success else "Command failed",
    )


@app.post("/tracker/datetime", response_model=CommandResponse)
async def set_datetime(command: SetDateTimeCommand):
    """Set tracker internal clock (the tracker expects UTC)."""
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        when = datetime(command.year, command.month, command.day,
                        command.hour, command.minute, command.second)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    success = await serial_handler.set_datetime(when)
    return CommandResponse(
        success=success,
        message=f"DateTime set to {when:%Y-%m-%d %H:%M:%S}" if success else "Command failed",
    )


@app.post("/tracker/datetime/sync", response_model=CommandResponse)
async def sync_datetime():
    """Sync tracker clock with server UTC time."""
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")
    now = _utcnow()
    success = await serial_handler.set_datetime(now)
    return CommandResponse(
        success=success,
        message=f"Synced to {now:%Y-%m-%d %H:%M:%S UTC}" if success else "Command failed",
    )


@app.post("/tracker/position/{position}", response_model=CommandResponse)
async def go_to_preset_position(position: PresetPosition):
    """
    Drive to a stored position (manual mode only).

    - maintenance: the stored maintenance position
    - horizontal: panel flat
    - vertical: panel at its most upright (altitude 25 degrees)
    """
    await _preempt()
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")
    success = await serial_handler.go_to_position(position)
    return CommandResponse(
        success=success,
        message=f"Going to {position.value} position" if success else "Command failed",
    )


@app.post("/tracker/goto", response_model=CommandResponse)
async def go_to_angle(command: GotoCommand):
    """
    Drive to a tilt (altitude) and/or azimuth and stop there. Manual mode only.

    The Pi jogs the motors and watches the status frames; /tracker/stop aborts it.
    """
    if command.altitude is None and command.azimuth is None:
        raise HTTPException(status_code=400, detail="Give an altitude, an azimuth or both")
    if not serial_handler.is_connected or not current_status.link_ok:
        raise HTTPException(status_code=400, detail="No link to the tracker")
    if current_status.mode != OperatingMode.MANUAL:
        raise HTTPException(status_code=409, detail="Switch to manual mode first")
    _jog["direction"] = None
    _disarm_stop_guard()
    try:
        goto.start(command.altitude, command.azimuth)
    except GotoError as e:
        raise HTTPException(status_code=409, detail=str(e))
    current_status.goto = goto.state
    return CommandResponse(success=True, message="Move started")


@app.post("/tracker/home", response_model=CommandResponse)
async def go_home():
    """Drive to the maintenance position (kept for compatibility)."""
    return await go_to_preset_position(PresetPosition.MAINTENANCE)


@app.post("/tracker/stow", response_model=CommandResponse)
async def go_stow():
    """Lay the panel flat (kept for compatibility)."""
    return await go_to_preset_position(PresetPosition.HORIZONTAL)


@app.post("/tracker/zero", response_model=CommandResponse)
async def zero_panel(confirm: bool = False):
    """ZERAR PAINEL: start the tracker's homing routine. The tracker will move."""
    if not confirm:
        raise HTTPException(status_code=400, detail="Homing moves the tracker; pass confirm=true")
    await _preempt()
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")
    success = await serial_handler.zero_panel()
    return CommandResponse(
        success=success,
        message="Homing routine started" if success else "Command failed",
    )


@app.post("/tracker/limits/reset", response_model=CommandResponse)
async def reset_observed_limits():
    """Reset observed position limits and start tracking fresh."""
    current_status.observed_limits = ObservedLimits()
    save_observed_limits(current_status.observed_limits)
    return CommandResponse(
        success=True,
        message="Observed limits reset",
    )


@app.get("/tracker/limits")
async def get_observed_limits():
    """Get current observed position limits."""
    return current_status.observed_limits


# =============================================================================
# WebSocket Endpoint
# =============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates."""
    await websocket.accept()
    websocket_connections.append(websocket)
    logger.info(f"WebSocket client connected ({len(websocket_connections)} total)")

    try:
        # Send current status immediately
        await websocket.send_text(current_status.model_dump_json())

        # Keep connection alive and handle incoming messages
        while True:
            data = await websocket.receive_text()
            # Handle any client commands via WebSocket if needed
            logger.debug(f"WebSocket received: {data}")

    except WebSocketDisconnect:
        pass
    finally:
        if websocket in websocket_connections:
            websocket_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected ({len(websocket_connections)} remaining)")


# =============================================================================
# Web UI Endpoint
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def web_ui(request: Request):
    """Serve the web UI."""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "title": "Solar Tracker Control",
    })
