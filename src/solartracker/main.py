"""Main FastAPI application for the Solar Tracker API."""

import asyncio
import logging
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
    SetLimitsCommand,
    SetWindThresholdCommand,
    SetGPSLocationCommand,
    SetDateTimeCommand,
    PresetPosition,
    Direction,
    OperatingMode,
    ConnectionStatus,
    AlarmEntry,
    ObservedLimits,
)
from .serial_handler import serial_handler
from .mqtt_handler import mqtt_handler
from .protocol import SolarTrackerProtocol, ResponseOffsets

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# File logging for persistent state change logs
import os
from logging.handlers import RotatingFileHandler
_log_dir = "/app/data"
os.makedirs(_log_dir, exist_ok=True)
_file_handler = RotatingFileHandler(
    os.path.join(_log_dir, "solartracker.log"),
    maxBytes=5 * 1024 * 1024,  # 5MB per file
    backupCount=5,              # Keep 5 rotated files (25MB total)
)
_file_handler.setLevel(logging.INFO)
_file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(_file_handler)

# WebSocket connections for live updates
websocket_connections: List[WebSocket] = []

# Current tracker status (updated from serial responses)
current_status = TrackerStatus()

# Buffer for accumulating serial data
receive_buffer = bytearray()

# State change tracking for diagnostic logging
_last_logged_state = {
    "alarm_code": None,
    "status_flags": None,
    "mode_byte": None,
    "is_auto_mode": None,
    "vertical": None,
    "raw_bytes_34_37": None,
}

# Observed limits persistence
LIMITS_FILE = "/app/data/observed_limits.json"


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
    from datetime import datetime
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
        now = datetime.utcnow()
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


def _log_state_changes(parsed: dict, packet: bytes):
    """Log when alarm, mode, status flags, or position state changes."""
    global _last_logged_state

    flags = parsed.get("status_flags", {})
    alarms = parsed.get("alarms", {})
    position = parsed.get("position", {})

    new_alarm_code = alarms.get("code")
    new_status_flags = flags.get("raw")
    new_mode_byte = flags.get("mode_byte")
    new_is_auto = flags.get("is_auto_mode")
    new_vertical = position.get("vertical")

    # Raw bytes around the alarm region for analysis
    raw_34_37 = packet[34:38].hex() if len(packet) >= 38 else None

    changed = []
    if new_alarm_code != _last_logged_state["alarm_code"]:
        changed.append(f"alarm: 0x{_last_logged_state['alarm_code'] or 0:02x}->0x{new_alarm_code or 0:02x} ({alarms.get('list', [])})")
    if new_status_flags != _last_logged_state["status_flags"]:
        changed.append(f"status_flags: 0x{_last_logged_state['status_flags'] or 0:02x}->0x{new_status_flags or 0:02x}")
    if new_is_auto != _last_logged_state["is_auto_mode"]:
        changed.append(f"mode: {'auto' if _last_logged_state['is_auto_mode'] else 'manual'}->{'auto' if new_is_auto else 'manual'}")
    if new_vertical != _last_logged_state["vertical"]:
        old_v = _last_logged_state["vertical"]
        changed.append(f"vertical: {old_v}->{new_vertical}")
    if raw_34_37 != _last_logged_state["raw_bytes_34_37"]:
        changed.append(f"bytes[34:38]: {_last_logged_state['raw_bytes_34_37']}->{raw_34_37}")

    if changed:
        sun = parsed.get("sun_position", {})
        logger.info(
            f"STATE CHANGE: {', '.join(changed)} | "
            f"pos=({position.get('horizontal')}, {new_vertical}) "
            f"sun=({sun.get('azimuth')}, {sun.get('altitude')}) "
            f"raw[34:38]={raw_34_37}"
        )

    _last_logged_state["alarm_code"] = new_alarm_code
    _last_logged_state["status_flags"] = new_status_flags
    _last_logged_state["mode_byte"] = new_mode_byte
    _last_logged_state["is_auto_mode"] = new_is_auto
    _last_logged_state["vertical"] = new_vertical
    _last_logged_state["raw_bytes_34_37"] = raw_34_37


async def on_serial_data(data: bytes):
    """Handle data received from serial port."""
    global current_status, receive_buffer
    logger.debug(f"Received serial data: {data.hex()}")

    # Accumulate data in buffer
    receive_buffer.extend(data)

    # Use constants from protocol module
    RESPONSE_HEADER = SolarTrackerProtocol.RESPONSE_HEADER
    MIN_PACKET_SIZE = ResponseOffsets.MIN_PACKET_SIZE
    MAX_PACKET_SIZE = ResponseOffsets.MAX_PACKET_SIZE
    HEADER_LENGTH = ResponseOffsets.HEADER_LENGTH

    while len(receive_buffer) >= MIN_PACKET_SIZE:
        # Check for response header
        header_idx = -1
        for i in range(len(receive_buffer) - HEADER_LENGTH + 1):
            if receive_buffer[i:i + HEADER_LENGTH] == RESPONSE_HEADER:
                header_idx = i
                break

        if header_idx == -1:
            # No header found, keep last bytes in case header is split
            receive_buffer = receive_buffer[-(HEADER_LENGTH - 1):] if len(receive_buffer) > HEADER_LENGTH - 1 else receive_buffer
            break

        # Discard data before header
        if header_idx > 0:
            receive_buffer = receive_buffer[header_idx:]

        # Find the end of this packet (next header or end of meaningful data)
        packet_end = MIN_PACKET_SIZE

        # Look for version string "Version " which marks end of useful data
        version_marker = b'Version '
        version_idx = receive_buffer.find(version_marker, MIN_PACKET_SIZE)
        if version_idx != -1 and version_idx < MAX_PACKET_SIZE:
            # Include version string + "2.31" + footer (83) + checksum
            packet_end = min(version_idx + 15, len(receive_buffer))

        # Also check for next header
        next_header = -1
        for i in range(MIN_PACKET_SIZE, min(len(receive_buffer) - HEADER_LENGTH + 1, MAX_PACKET_SIZE)):
            if receive_buffer[i:i + HEADER_LENGTH] == RESPONSE_HEADER:
                next_header = i
                break

        if next_header != -1:
            packet_end = next_header
        elif len(receive_buffer) < packet_end:
            # Wait for more data
            break

        # Extract and parse packet
        packet = bytes(receive_buffer[:packet_end])
        receive_buffer = receive_buffer[packet_end:]

        parsed = SolarTrackerProtocol.parse_response(packet)
        if parsed:
            logger.debug(f"Parsed response: {parsed}")

            # Diagnostic logging: log on state changes only
            _log_state_changes(parsed, packet)

            # Update current_status with parsed data
            if "position" in parsed:
                pos = parsed["position"]
                current_status.position.horizontal = pos.get("horizontal")
                current_status.position.vertical = pos.get("vertical")
                update_observed_limits(pos.get("horizontal"), pos.get("vertical"))

            if "sun_position" in parsed:
                sun = parsed["sun_position"]
                current_status.sun_position.altitude = sun.get("altitude")
                current_status.sun_position.azimuth = sun.get("azimuth")

            if "date" in parsed:
                d = parsed["date"]
                try:
                    from datetime import datetime
                    current_status.utc_time = datetime(
                        d["year"], d["month"], d["day"],
                        d["hour"], d.get("minute", 0), d.get("second", 0)
                    )
                except:
                    pass

            if "version" in parsed:
                current_status.firmware_version = parsed["version"]

            # Update mode based on status flags
            if "status_flags" in parsed:
                flags = parsed["status_flags"]
                new_mode = OperatingMode.AUTOMATIC if flags.get("is_auto_mode") else OperatingMode.MANUAL
                if new_mode != current_status.mode:
                    logger.warning(f"Mode transition: {current_status.mode.value} → {new_mode.value} (mode_byte={flags.get('mode_byte')})")
                current_status.mode = new_mode

            if "alarms" in parsed and "list" in parsed["alarms"]:
                new_alarms = parsed["alarms"]["list"]
                # Detect new alarms and add to history
                from datetime import datetime
                for alarm in new_alarms:
                    if alarm not in current_status.alarms:
                        # New alarm detected - add to history
                        alarm_names = {
                            'vertical_limit': 'Vertical Limit',
                            'tilt_limit_flat': 'Tilt Limit - Panel Flat (stow position)',
                            'west_limit': 'West Limit',
                            'wind_speed': 'Wind Speed Exceeded',
                            'actuator_current': 'Actuator Current',
                            'rotation_current': 'Rotation Current',
                            'unknown_alarm_6': 'Unknown Alarm (bit 6)',
                            'encoder_error': 'Encoder Error',
                        }
                        entry = AlarmEntry(
                            alarm_type=alarm,
                            timestamp=current_status.utc_time or datetime.utcnow(),
                            message=alarm_names.get(alarm, alarm)
                        )
                        current_status.alarm_history.insert(0, entry)  # Newest first
                        # Keep only last 20 alarms in history
                        current_status.alarm_history = current_status.alarm_history[:20]
                        logger.warning(f"Alarm triggered: {alarm}")
                current_status.alarms = new_alarms

    # Broadcast to WebSocket clients
    await broadcast_status()

    # Publish to MQTT
    await mqtt_handler.publish_status(current_status)


async def status_poll_loop():
    """Periodically poll status from tracker."""
    while True:
        try:
            if serial_handler.is_connected:
                await serial_handler.request_status()

            # Update connection status
            current_status.connection = serial_handler.get_status()

            # Broadcast updates
            await broadcast_status()
            await mqtt_handler.publish_status(current_status)

        except Exception as e:
            logger.error(f"Status poll error: {e}")

        await asyncio.sleep(settings.status_poll_interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Solar Tracker API...")

    # Load persisted observed limits
    current_status.observed_limits = load_observed_limits()

    # Set up serial handler callback
    serial_handler.set_data_callback(on_serial_data)

    # Set up MQTT callbacks
    async def sync_datetime_callback():
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        return await serial_handler.set_datetime(
            now.year, now.month, now.day,
            now.hour, now.minute, now.second
        )

    mqtt_handler.set_callbacks(
        on_move=lambda d, s: serial_handler.move(d, s),
        on_mode=lambda auto: serial_handler.set_mode(auto),
        on_clear_alarms=lambda: serial_handler.clear_alarms(),
        on_set_wind=lambda v: serial_handler.set_max_wind(v),
        on_go_home=lambda: serial_handler.go_home(),
        on_go_stow=lambda: serial_handler.go_stow(),
        on_set_gps=lambda lat, lon: serial_handler.set_gps_location(lat, lon),
        on_sync_datetime=sync_datetime_callback,
        on_zero_panel=lambda: serial_handler.zero_panel(),
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

    # Start status polling task
    poll_task = asyncio.create_task(status_poll_loop())

    yield

    # Cleanup
    logger.info("Shutting down Solar Tracker API...")
    poll_task.cancel()
    try:
        await poll_task
    except asyncio.CancelledError:
        pass

    await serial_handler.disconnect()
    await mqtt_handler.disconnect()


# Create FastAPI app
app = FastAPI(
    title="Solar Tracker API",
    description="REST API for controlling solar tracking systems",
    version="0.1.0",
    lifespan=lifespan,
)

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
        "mqtt_connected": mqtt_handler.is_connected,
    }


@app.get("/info")
async def get_info():
    """Get API information."""
    return {
        "name": "Solar Tracker API",
        "version": "0.1.0",
        "protocol_defined": SolarTrackerProtocol.is_protocol_defined(),
        "defined_commands": [c.name for c in SolarTrackerProtocol.get_defined_commands()],
        "undefined_commands": [c.name for c in SolarTrackerProtocol.get_undefined_commands()],
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
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    success = await serial_handler.move(command.direction, start=True)

    # If duration specified, stop after delay
    if success and command.duration_ms:
        async def stop_after_delay():
            await asyncio.sleep(command.duration_ms / 1000)
            await serial_handler.move(command.direction, start=False)

        asyncio.create_task(stop_after_delay())

    return CommandResponse(
        success=success,
        message=f"Moving {command.direction.value}" if success else "Command failed",
    )


@app.post("/tracker/move/{direction}/start", response_model=CommandResponse)
async def start_move(direction: Direction):
    """Start moving in a direction (hold)."""
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    success = await serial_handler.move(direction, start=True)
    return CommandResponse(
        success=success,
        message=f"Started moving {direction.value}" if success else "Command failed",
    )


@app.post("/tracker/move/{direction}/stop", response_model=CommandResponse)
async def stop_move(direction: Direction):
    """Stop moving in a direction."""
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    success = await serial_handler.move(direction, start=False)
    return CommandResponse(
        success=success,
        message="Stopped" if success else "Command failed",
    )


@app.post("/tracker/stop", response_model=CommandResponse)
async def stop_all():
    """Stop all movement."""
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    success = await serial_handler.stop()
    return CommandResponse(
        success=success,
        message="Stopped" if success else "Command failed",
    )


@app.post("/tracker/mode/{mode}", response_model=CommandResponse)
async def set_mode(mode: OperatingMode):
    """Set operating mode."""
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    automatic = mode == OperatingMode.AUTOMATIC
    logger.info(f"Mode endpoint called: {mode.value} (automatic={automatic})")
    success = await serial_handler.set_mode(automatic)

    # Don't set current_status.mode here — let tracker confirm via next status response
    # (parsed in on_serial_data → status_flags → is_auto_mode)

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

    if success:
        current_status.alarms = []

    return CommandResponse(
        success=success,
        message="Alarms cleared" if success else "Command failed",
    )


@app.post("/tracker/wind", response_model=CommandResponse)
async def set_wind_threshold(command: SetWindThresholdCommand):
    """Set maximum wind threshold."""
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    success = await serial_handler.set_max_wind(command.max_wind)

    if success:
        current_status.max_wind_threshold = command.max_wind

    return CommandResponse(
        success=success,
        message=f"Max wind set to {command.max_wind}" if success else "Command failed",
    )


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
    """Set tracker internal clock."""
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    success = await serial_handler.set_datetime(
        command.year, command.month, command.day,
        command.hour, command.minute, command.second
    )

    return CommandResponse(
        success=success,
        message=f"DateTime set to {command.year}-{command.month:02d}-{command.day:02d} {command.hour:02d}:{command.minute:02d}:{command.second:02d}" if success else "Command failed",
    )


@app.post("/tracker/datetime/sync", response_model=CommandResponse)
async def sync_datetime():
    """Sync tracker clock with server UTC time."""
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    success = await serial_handler.set_datetime(
        now.year, now.month, now.day,
        now.hour, now.minute, now.second
    )

    return CommandResponse(
        success=success,
        message=f"Synced to {now.strftime('%Y-%m-%d %H:%M:%S UTC')}" if success else "Command failed",
    )


@app.post("/tracker/position/{position}", response_model=CommandResponse)
async def go_to_preset_position(position: PresetPosition):
    """
    Go to a preset position.

    - position 1: Unknown preset
    - position 2 (HOME): Home position
    - position 3 (STOW): Stow/safe position
    """
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    success = await serial_handler.go_to_position(position.value)

    position_names = {1: "Position 1", 2: "HOME", 3: "STOW"}
    return CommandResponse(
        success=success,
        message=f"Going to {position_names[position.value]}" if success else "Command failed",
    )


@app.post("/tracker/home", response_model=CommandResponse)
async def go_home():
    """Move panel to HOME position."""
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    success = await serial_handler.go_home()
    return CommandResponse(
        success=success,
        message="Going to HOME position" if success else "Command failed",
    )


@app.post("/tracker/stow", response_model=CommandResponse)
async def go_stow():
    """Move panel to STOW (safe) position."""
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    success = await serial_handler.go_stow()
    return CommandResponse(
        success=success,
        message="Going to STOW position" if success else "Command failed",
    )


@app.post("/tracker/zero", response_model=CommandResponse)
async def zero_panel():
    """Reset panel position encoders to zero."""
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    success = await serial_handler.zero_panel()
    return CommandResponse(
        success=success,
        message="Panel position zeroed" if success else "Command failed",
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


@app.post("/tracker/alarms/query", response_model=CommandResponse)
async def query_alarms():
    """Query detailed alarm status from tracker."""
    if not serial_handler.is_connected:
        raise HTTPException(status_code=400, detail="Not connected")

    success = await serial_handler.query_alarms()
    return CommandResponse(
        success=success,
        message="Alarm query sent" if success else "Command failed",
    )


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
