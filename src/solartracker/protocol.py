"""Serial protocol for the Metalogalva solar tracker (STS.2A firmware V2.31).

Derived from the HCS12 firmware and STcontrol V4.0.4.0. See docs/protocol.md.

Frame:  81 DST SRC 82 LEN_HI LEN_LO CMD DATA[LEN-1] 83 CHK
  LEN = number of CMD + DATA bytes, CHK = sum of all preceding bytes mod 256.

The tracker (address 0x01) broadcasts a status frame (CMD 0x50) by itself
once per second. There is no status request.
"""

import struct
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Iterator, Optional

SOF = 0x81
MARK = 0x82
EOF = 0x83

ADDR_PC = 0x00
ADDR_TRACKER = 0x01
ADDR_BROADCAST = 0xFF

MAX_PAYLOAD = 292  # tracker receive buffer is 300 bytes


class Cmd(IntEnum):
    """Command codes."""
    # PC -> tracker
    MODE_MANUAL = 0x10
    MODE_AUTO = 0x11
    MOVE_EAST = 0x20
    MOVE_WEST = 0x21
    MOVE_UP = 0x22
    MOVE_DOWN = 0x23
    MOVE_STOP = 0x24
    GOTO_MAINTENANCE = 0x25
    GOTO_HORIZONTAL = 0x26
    GOTO_VERTICAL = 0x27
    SET_CLOCK = 0x30
    ZERO_PANEL = 0x31          # starts the homing routine
    CONFIRM_SUN_AIMED = 0x32   # azimuth calibration
    SET_LOCATION = 0x33
    SET_SUN_LIMITS = 0x34
    STORE_MAINTENANCE = 0x35
    STORE_VERTICAL_LIMIT = 0x36
    CLEAR_ALARMS = 0x40
    READ_PARAM = 0x41
    WRITE_PARAM = 0x42
    # tracker -> PC
    STATUS = 0x50
    PARAM_REPLY = 0x51
    ACK = 0x86
    NAK_A = 0x95
    NAK_B = 0x96


# 0xF0-0xF2 enter the firmware-update path. Never send them.
FORBIDDEN_COMMANDS = frozenset({0xF0, 0xF1, 0xF2})

PARAM_WIND = 0x03
PARAM_MAX_WIND_RECORD = 0x0A


@dataclass(frozen=True)
class AlarmDef:
    bit: int
    code: str
    message: str
    severity: str  # "fault", "warning" or "info"


# Bit order matches the 16-bit alarm word and STcontrol's message table.
ALARMS: tuple[AlarmDef, ...] = (
    AlarmDef(0, "rotation_encoder", "Rotation motor encoder error", "fault"),
    AlarmDef(1, "actuator_encoder", "Actuator motor encoder error", "fault"),
    AlarmDef(2, "rotation_direction", "Rotation moving in the wrong direction", "fault"),
    AlarmDef(3, "actuator_direction", "Actuator moving in the wrong direction", "fault"),
    AlarmDef(4, "east_limit_position", "East limit switch out of position", "fault"),
    AlarmDef(5, "west_limit_position", "West limit switch out of position", "fault"),
    AlarmDef(6, "horizontal_limit_position", "Horizontal limit switch out of position", "fault"),
    AlarmDef(7, "vertical_limit_position", "Vertical limit switch out of position", "fault"),
    AlarmDef(8, "not_configured", "No initial configuration", "fault"),
    AlarmDef(9, "east_limit", "East limit switch active", "info"),
    AlarmDef(10, "west_limit", "West limit switch active", "info"),
    AlarmDef(11, "horizontal_limit", "Horizontal limit switch active (panel flat)", "info"),
    AlarmDef(12, "vertical_limit", "Vertical limit switch active", "info"),
    AlarmDef(13, "rotation_overcurrent", "Rotation motor current exceeded", "fault"),
    AlarmDef(14, "actuator_overcurrent", "Actuator motor current exceeded", "fault"),
    AlarmDef(15, "wind", "Wind limit exceeded", "warning"),
)
ALARM_BY_CODE = {a.code: a for a in ALARMS}


@dataclass
class Frame:
    dst: int
    src: int
    cmd: int
    data: bytes
    raw: bytes


def checksum(data: bytes) -> int:
    return sum(data) & 0xFF


def build_frame(cmd: int, data: bytes = b"", dst: int = ADDR_BROADCAST, src: int = ADDR_PC) -> bytes:
    """Build a complete frame."""
    if cmd in FORBIDDEN_COMMANDS:
        raise ValueError(f"command 0x{cmd:02X} is the firmware-update path and is blocked")
    length = 1 + len(data)
    if length > MAX_PAYLOAD:
        raise ValueError("payload too long")
    body = bytes([SOF, dst, src, MARK, length >> 8, length & 0xFF, cmd]) + bytes(data) + bytes([EOF])
    return body + bytes([checksum(body)])


class FrameDecoder:
    """Incremental decoder: feed bytes, get validated frames."""

    def __init__(self):
        self._buf = bytearray()
        self.frames_ok = 0
        self.frames_bad = 0

    def reset(self):
        self._buf.clear()

    def feed(self, data: bytes) -> Iterator[Frame]:
        self._buf.extend(data)
        buf = self._buf
        while True:
            start = buf.find(SOF)
            if start < 0:
                buf.clear()
                return
            if start:
                del buf[:start]
            if len(buf) < 6:
                return
            length = (buf[4] << 8) | buf[5]
            if buf[3] != MARK or not 1 <= length <= MAX_PAYLOAD:
                del buf[:1]  # false start, resync on the next 0x81
                continue
            total = length + 8
            if len(buf) < total:
                return
            raw = bytes(buf[:total])
            if raw[-2] != EOF or checksum(raw[:-1]) != raw[-1]:
                self.frames_bad += 1
                del buf[:1]
                continue
            del buf[:total]
            self.frames_ok += 1
            yield Frame(dst=raw[1], src=raw[2], cmd=raw[6], data=raw[7:-2], raw=raw)


def parse_frame(raw: bytes) -> Optional[Frame]:
    """Parse exactly one complete frame, or return None."""
    frames = list(FrameDecoder().feed(raw))
    return frames[0] if len(frames) == 1 and frames[0].raw == bytes(raw) else None


def decode_alarm_word(word: int) -> list[AlarmDef]:
    return [a for a in ALARMS if word & (1 << a.bit)]


def _round(value: float) -> Optional[float]:
    if value != value or abs(value) > 1e6:  # NaN or nonsense
        return None
    return round(value, 2)


def parse_status(frame: Frame) -> Optional[dict]:
    """Decode a CMD 0x50 status frame. Offsets below are relative to the data (frame offset - 7)."""
    d = frame.data
    if frame.cmd != Cmd.STATUS or len(d) < 111:
        return None

    tilt_count, = struct.unpack_from("<h", d, 7)
    panel_alt, = struct.unpack_from("<f", d, 9)
    rot_count, = struct.unpack_from("<h", d, 13)
    panel_azi, sun_alt, sun_azi = struct.unpack_from("<fff", d, 15)
    wind, alarm_word = struct.unpack_from("<hH", d, 27)

    try:
        clock = datetime(2000 + d[3], d[2], d[1], d[6], d[5], d[4])
    except ValueError:
        clock = None

    # One log slot per alarm bit: year, month, day, hour, minute of its last activation
    log = []
    for a in ALARMS:
        y, mo, da, h, mi = d[31 + 5 * a.bit: 36 + 5 * a.bit]
        try:
            when = datetime(2000 + y, mo, da, h, mi)
        except ValueError:
            continue
        log.append({"code": a.code, "message": a.message, "severity": a.severity, "timestamp": when})

    version = d[111:].split(b"\x00")[0].decode("ascii", "replace").strip()

    return {
        "manual": d[0] != 0,
        "clock": clock,
        "tilt_encoder": tilt_count,
        "rotation_encoder": rot_count,
        "panel_altitude": _round(panel_alt),
        "panel_azimuth": _round(panel_azi),
        "sun_altitude": _round(sun_alt),
        "sun_azimuth": _round(sun_azi),
        "wind_speed": wind,
        "alarm_word": alarm_word,
        "alarms": decode_alarm_word(alarm_word),
        "alarm_log": log,
        "version": version.removeprefix("Version ").strip() or None,
    }


def parse_param_reply(frame: Frame) -> Optional[dict]:
    """Decode a CMD 0x51 reply to READ_PARAM."""
    d = frame.data
    if frame.cmd != Cmd.PARAM_REPLY or not d:
        return None
    if d[0] == PARAM_WIND and len(d) >= 6:
        hold, = struct.unpack_from("<H", d, 1)
        return {"param": "wind", "hold_minutes": hold, "count": d[3], "release": d[4], "trip": d[5]}
    if d[0] == PARAM_MAX_WIND_RECORD and len(d) >= 8:
        speed, = struct.unpack_from("<H", d, 1)
        try:
            when = datetime(2000 + d[3], d[4], d[5], d[6], d[7])
        except ValueError:
            when = None
        return {"param": "max_wind_record", "speed": speed, "timestamp": when}
    return None


# --- Command builders ---------------------------------------------------------

def set_mode(automatic: bool) -> bytes:
    """Switch mode. Each switch rewrites the tracker's flash, so do not spam it."""
    return build_frame(Cmd.MODE_AUTO if automatic else Cmd.MODE_MANUAL)


def move(cmd: Cmd) -> bytes:
    """Manual movement (MOVE_EAST/WEST/UP/DOWN/STOP). Only acted on in manual mode."""
    if not Cmd.MOVE_EAST <= cmd <= Cmd.MOVE_STOP:
        raise ValueError("not a movement command")
    return build_frame(cmd, b"\x01")  # STcontrol sends 01; the firmware ignores it


def stop() -> bytes:
    return move(Cmd.MOVE_STOP)


def goto(cmd: Cmd) -> bytes:
    if cmd not in (Cmd.GOTO_MAINTENANCE, Cmd.GOTO_HORIZONTAL, Cmd.GOTO_VERTICAL):
        raise ValueError("not a go-to command")
    return build_frame(cmd)


def clear_alarms() -> bytes:
    return build_frame(Cmd.CLEAR_ALARMS)


def set_clock(when: datetime) -> bytes:
    """Set the tracker clock. The tracker expects UTC."""
    weekday = (when.weekday() + 1) % 7  # 0 = Sunday
    return build_frame(Cmd.SET_CLOCK, bytes([
        when.second, when.minute, when.hour, weekday, when.day, when.month, when.year % 100,
    ]))


def set_location(latitude: float, longitude: float) -> bytes:
    return build_frame(Cmd.SET_LOCATION, struct.pack("<ff", latitude, longitude))


def zero_panel() -> bytes:
    """ZERAR PAINEL: starts the homing routine. The tracker will move."""
    return build_frame(Cmd.ZERO_PANEL)


def read_wind_settings() -> bytes:
    return build_frame(Cmd.READ_PARAM, bytes([PARAM_WIND]))


def read_max_wind_record() -> bytes:
    return build_frame(Cmd.READ_PARAM, bytes([PARAM_MAX_WIND_RECORD]))


def write_wind_settings(trip: int, release: int, hold_minutes: int = 10, count: int = 1) -> bytes:
    """Wind alarm trips above `trip` km/h and holds until wind stays below `release` for `hold_minutes`."""
    if not (0 < release <= trip <= 255 and 0 < count <= 255 and 0 < hold_minutes <= 0xFFFF):
        raise ValueError("invalid wind settings")
    return build_frame(Cmd.WRITE_PARAM, bytes([PARAM_WIND]) + struct.pack("<H", hold_minutes)
                       + bytes([count, release, trip]))
