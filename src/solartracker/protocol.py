"""
Solar Tracker Serial Protocol Implementation.

Protocol reverse-engineered from STcontrol V4.0.4.0.exe using radare2.
See docs/protocol.md for full protocol documentation.
"""

import struct
from dataclasses import dataclass
from typing import Optional, List
from enum import IntEnum


class MovementCommand(IntEnum):
    """Movement command codes (captured from STcontrol and firmware analysis)."""
    RIGHT = 0x20  # Rotate East
    LEFT = 0x21   # Rotate West
    UP = 0x22     # Tilt up
    DOWN = 0x23   # Tilt down
    STOP = 0x24   # Stop all movement
    # Discovered from firmware analysis (STS.2A_V2.31) - need testing
    GO_POSITION_1 = 0x25  # Unknown preset position (firmware loads direction 4)
    GO_POSITION_2 = 0x26  # Unknown preset position (firmware loads direction 5) - possibly HOME
    GO_POSITION_3 = 0x27  # Unknown preset position (firmware loads direction 6) - possibly STOW


class ModeCommand(IntEnum):
    """Mode command codes (verified by observing tracker behavior)."""
    AUTO = 0x10    # Switch to automatic tracking mode
    MANUAL = 0x11  # Switch to manual mode


class CommandType(IntEnum):
    """Command type codes (byte 6) - legacy, kept for compatibility."""
    # Movement commands (packet type 0x02)
    START = 0x23  # '#' - Start movement (old format)
    STOP = 0x24   # '$' - Stop movement
    # Alarm commands (packet type 0x01)
    CLEAR_ALARMS = 0x40  # '@' - Clear all alarms
    # Status commands (packet type 0x08)
    STATUS_REQUEST = 0x30  # '0' - Request status


# Legacy Direction enum for backwards compatibility
class Direction(IntEnum):
    """Movement direction codes (legacy - use MovementCommand instead)."""
    STOP = 0x00
    DOWN = 0x01
    UP = 0x02
    LEFT = 0x03
    RIGHT = 0x04


class PacketType(IntEnum):
    """Packet type codes (byte 5)."""
    ALARM = 0x01      # 9-byte alarm/mode commands (0x10, 0x11, 0x31-0x36, 0x40)
    MOVEMENT = 0x02   # 10-byte movement commands (0x20-0x27)
    CONFIG = 0x03     # Configuration commands (0x34 = zero/reset)
    STATUS = 0x08     # 9-byte status requests (0x30)
    SETTINGS = 0x09   # 16-byte settings commands (0x33 = GPS location)


class QueryCommand(IntEnum):
    """Query command codes for Type 0x01 packets (discovered from COM capture)."""
    ALARM_QUERY = 0x31    # Query alarm status
    QUERY_32 = 0x32       # Unknown query - needs investigation
    QUERY_35 = 0x35       # Unknown query - needs investigation
    QUERY_36 = 0x36       # Unknown query - needs investigation
    # Extended commands (discovered from firmware STS.2A_V2.31)
    EXTENDED_CTRL_A = 0x41  # Advanced calibration (sub-cmds: 0x02, 0x03, 0x0A)
    EXTENDED_CTRL_B = 0x42  # GPS/Position data operations (sub-cmds: 0x03, 0x07)


class DiagnosticCommand(IntEnum):
    """Diagnostic command codes (discovered from firmware analysis)."""
    DIAG_DEBUG = 0xF0     # Enter debug/diagnostic mode (sub-cmd: 0x0D)
    DIAG_FIRMWARE = 0xF1  # Firmware information/operations
    DIAG_EXTENDED = 0xF2  # Extended diagnostics


@dataclass
class ProtocolConstants:
    """Protocol constant bytes (corrected from direct serial capture)."""
    HEADER = 0x81
    BYTE1 = 0xFF
    BYTE2 = 0x00      # Corrected: direct serial capture shows 0x00 (TCP had telnet corruption)
    CMD_GROUP = 0x82
    BYTE4 = 0x00
    MOVEMENT_PARAM = 0x01  # Extra byte in movement commands
    FOOTER = 0x83


@dataclass
class ResponseOffsets:
    """
    Byte offsets for parsing status response packets.

    Response packet structure (38+ bytes):
    ┌─────────────────────────────────────────────────────────────────┐
    │ Offset │ Length │ Type        │ Description                    │
    ├────────┼────────┼─────────────┼────────────────────────────────┤
    │ 0-6    │ 7      │ bytes       │ Header: 81 00 01 82 00 7c 50   │
    │ 7      │ 1      │ byte        │ Mode: 0x00=AUTO, 0x01=MANUAL   │
    │ 8      │ 1      │ uint8       │ Day (1-31)                     │
    │ 9      │ 1      │ uint8       │ Month (1-12)                   │
    │ 10     │ 1      │ uint8       │ Year (offset from 2000)        │
    │ 11     │ 1      │ uint8       │ Second (0-59)                  │
    │ 12     │ 1      │ uint8       │ Minute (0-59)                  │
    │ 13     │ 1      │ uint8       │ Hour (0-23)                    │
    │ 14-15  │ 2      │ bytes       │ Reserved/Unknown               │
    │ 16-19  │ 4      │ float32 LE  │ Panel Vertical/Tilt (degrees)  │
    │ 20     │ 1      │ uint8       │ Status/Mode flags (see below)  │
    │ 21     │ 1      │ uint8       │ Unknown (observed: 0x14)       │
    │ 22-25  │ 4      │ float32 LE  │ Panel Horizontal/Azi (degrees) │
    │ 26-29  │ 4      │ float32 LE  │ Sun Altitude (degrees)         │
    │ 30-33  │ 4      │ float32 LE  │ Sun Azimuth (degrees)          │
    │ 34     │ 1      │ uint8       │ Alarm bitmask                  │
    │ 35-37  │ 3      │ bytes       │ Reserved/Padding               │
    └────────┴────────┴─────────────┴────────────────────────────────┘

    Extended packets (134+ bytes) include firmware version string
    starting with "Version " followed by version number (e.g., "2.31").
    """
    # Header
    HEADER_START = 0
    HEADER_LENGTH = 7

    # Mode byte (byte 7): 0x00 = AUTO tracking (default), 0x01 = MANUAL
    MODE_BYTE = 7

    # Date/Time (bytes 8-13)
    DAY = 8
    MONTH = 9
    YEAR = 10      # Add 2000 to get full year
    SECOND = 11
    MINUTE = 12
    HOUR = 13

    # Panel Position (little-endian floats)
    PANEL_VERTICAL = 16    # 4 bytes, tilt angle in degrees
    PANEL_HORIZONTAL = 22  # 4 bytes, azimuth angle in degrees

    # Sun Position (little-endian floats)
    SUN_AZIMUTH = 30       # 4 bytes, degrees
    SUN_ALTITUDE = 26      # 4 bytes, degrees

    # Status/Mode flags (byte 20)
    # Observed value 0xCF - meaning under investigation
    STATUS_FLAGS = 20

    # Alarms (corrected - byte 36, confirmed with stowed panel showing horizontal_limit)
    ALARM_BYTE = 37        # Bitmask for active alarms

    # Minimum packet sizes
    MIN_PACKET_SIZE = 38
    MAX_PACKET_SIZE = 150  # Extended packets with version string


class SolarTrackerProtocol:
    """
    Solar Tracker Protocol Handler.

    Builds and parses command packets for the Metalogalva solar tracker.

    Packet Structure (10 bytes):
    [0x81][0xFF][0x00][0x82][0x00][0x02][CMD][DIR][0x83][CHECKSUM]

    Where:
    - CMD: 0x23 (start) or 0x24 (stop)
    - DIR: Direction code (0-4)
    - CHECKSUM: Sum of bytes 0-8, mod 256
    """

    # Response header for status packets (used in parse_response)
    # Note: Command packets are built dynamically by each method

    @staticmethod
    def calculate_checksum(data: bytes) -> int:
        """
        Calculate checksum for a packet.

        The checksum is sum of all bytes, modulo 256.
        Note: Direct serial capture confirmed no +1 offset (TCP capture had telnet corruption).

        Args:
            data: Packet bytes (without checksum)

        Returns:
            Checksum byte (0-255)
        """
        return sum(data) & 0xFF

    @classmethod
    def build_movement_command_v2(cls, movement: MovementCommand) -> bytes:
        """
        Build a movement command packet (correct format from direct serial capture).

        Packet format (10 bytes):
        81 FF 00 82 00 02 [CMD] 01 83 [CHECKSUM]

        Args:
            movement: MovementCommand (UP, DOWN, LEFT, RIGHT, STOP)

        Returns:
            10-byte command packet
        """
        packet = bytearray([
            ProtocolConstants.HEADER,    # 0x81
            ProtocolConstants.BYTE1,     # 0xFF
            ProtocolConstants.BYTE2,     # 0x00
            ProtocolConstants.CMD_GROUP, # 0x82
            ProtocolConstants.BYTE4,     # 0x00
            PacketType.MOVEMENT,         # 0x02
            movement,                    # Command: 0x20-0x24
            ProtocolConstants.MOVEMENT_PARAM,  # 0x01
            ProtocolConstants.FOOTER,    # 0x83
        ])
        checksum = cls.calculate_checksum(packet)
        packet.append(checksum)
        return bytes(packet)

    @classmethod
    def build_movement_command(cls, direction: Direction, start: bool = True) -> bytes:
        """
        Build a movement command packet (legacy format - redirects to v2).

        Args:
            direction: Movement direction
            start: True for start command, False for stop

        Returns:
            11-byte command packet
        """
        if not start or direction == Direction.STOP:
            return cls.build_movement_command_v2(MovementCommand.STOP)

        # Map old direction codes to new movement commands
        direction_map = {
            Direction.UP: MovementCommand.UP,
            Direction.DOWN: MovementCommand.DOWN,
            Direction.LEFT: MovementCommand.LEFT,
            Direction.RIGHT: MovementCommand.RIGHT,
        }
        movement = direction_map.get(direction, MovementCommand.STOP)
        return cls.build_movement_command_v2(movement)

    @classmethod
    def build_stop_command(cls) -> bytes:
        """
        Build a stop all movement command.

        Returns:
            11-byte stop command packet
        """
        return cls.build_movement_command_v2(MovementCommand.STOP)

    @classmethod
    def build_mode_command(cls, auto_mode: bool) -> bytes:
        """
        Build a mode switch command packet.

        Packet format (9 bytes):
        81 FF 00 82 00 01 [10/11] 83 [CHECKSUM]

        Args:
            auto_mode: True for automatic mode, False for manual mode

        Returns:
            9-byte command packet
        """
        mode_cmd = ModeCommand.AUTO if auto_mode else ModeCommand.MANUAL
        packet = bytearray([
            ProtocolConstants.HEADER,    # 0x81
            ProtocolConstants.BYTE1,     # 0xFF
            ProtocolConstants.BYTE2,     # 0x00
            ProtocolConstants.CMD_GROUP, # 0x82
            ProtocolConstants.BYTE4,     # 0x00
            PacketType.ALARM,            # 0x01 (same type as alarm commands)
            mode_cmd,                    # 0x10=auto, 0x11=manual
            ProtocolConstants.FOOTER,    # 0x83
        ])
        checksum = cls.calculate_checksum(packet)
        packet.append(checksum)
        return bytes(packet)

    @classmethod
    def set_manual_mode(cls) -> bytes:
        """Build command to switch to manual mode."""
        return cls.build_mode_command(auto_mode=False)

    @classmethod
    def set_auto_mode(cls) -> bytes:
        """Build command to switch to automatic mode."""
        return cls.build_mode_command(auto_mode=True)

    @classmethod
    def build_clear_alarms(cls) -> bytes:
        """
        Build a clear alarms command packet.

        Clears all active alarms on the tracker.

        Returns:
            9-byte command packet
        """
        # Alarm packet uses type 0x01 in byte 5
        packet = bytearray([
            ProtocolConstants.HEADER,    # 0x81
            ProtocolConstants.BYTE1,     # 0xFF
            ProtocolConstants.BYTE2,     # 0x00
            ProtocolConstants.CMD_GROUP, # 0x82
            ProtocolConstants.BYTE4,     # 0x00
            PacketType.ALARM,            # 0x01
            CommandType.CLEAR_ALARMS,    # 0x40 '@'
            ProtocolConstants.FOOTER,    # 0x83
        ])
        checksum = cls.calculate_checksum(packet)
        packet.append(checksum)
        return bytes(packet)

    @classmethod
    def build_status_request(cls) -> bytes:
        """
        Build a status request command packet.

        Requests current status from the tracker.

        Returns:
            9-byte command packet
        """
        # Status packet uses type 0x08 in byte 5
        packet = bytearray([
            ProtocolConstants.HEADER,    # 0x81
            ProtocolConstants.BYTE1,     # 0xFF
            ProtocolConstants.BYTE2,     # 0x00
            ProtocolConstants.CMD_GROUP, # 0x82
            ProtocolConstants.BYTE4,     # 0x00
            PacketType.STATUS,           # 0x08
            CommandType.STATUS_REQUEST,  # 0x30 '0'
            ProtocolConstants.FOOTER,    # 0x83
        ])
        checksum = cls.calculate_checksum(packet)
        packet.append(checksum)
        return bytes(packet)

    @classmethod
    def move_up(cls, start: bool = True) -> bytes:
        """Build move up command."""
        return cls.build_movement_command(Direction.UP, start)

    @classmethod
    def move_down(cls, start: bool = True) -> bytes:
        """Build move down command."""
        return cls.build_movement_command(Direction.DOWN, start)

    @classmethod
    def move_left(cls, start: bool = True) -> bytes:
        """Build move left (west) command."""
        return cls.build_movement_command(Direction.LEFT, start)

    @classmethod
    def move_right(cls, start: bool = True) -> bytes:
        """Build move right (east) command."""
        return cls.build_movement_command(Direction.RIGHT, start)

    @classmethod
    def clear_alarms(cls) -> bytes:
        """
        Clear all active alarms.

        Returns:
            9-byte command packet
        """
        return cls.build_clear_alarms()

    @classmethod
    def request_status(cls) -> bytes:
        """
        Request current tracker status.

        Returns:
            9-byte command packet
        """
        return cls.build_status_request()

    @classmethod
    def set_max_wind(cls, threshold: int) -> Optional[bytes]:
        """
        Set maximum wind speed threshold.

        Args:
            threshold: Wind speed threshold (0-99)

        TODO: Reverse engineer this command.
        """
        return None

    @classmethod
    def set_limits(cls, east: int, west: int) -> Optional[bytes]:
        """
        Set east/west rotation limits.

        Args:
            east: East limit angle
            west: West limit angle

        TODO: Reverse engineer this command.
        """
        return None

    @classmethod
    def build_gps_location(cls, latitude: float, longitude: float) -> bytes:
        """
        Build a GPS location setting command packet.

        Discovered from COM port capture - Type 0x09 Command 0x33.
        Sets the tracker's location for sun position calculations.

        Packet format (16 bytes):
        81 FF 00 82 00 09 33 [LAT_4bytes_LE] [LON_4bytes_LE] 83 [CHECKSUM]

        Args:
            latitude: Latitude in decimal degrees (e.g., 40.5440 for Portugal)
            longitude: Longitude in decimal degrees (e.g., -8.6988 for Portugal)

        Returns:
            16-byte command packet
        """
        packet = bytearray([
            ProtocolConstants.HEADER,    # 0x81
            ProtocolConstants.BYTE1,     # 0xFF
            ProtocolConstants.BYTE2,     # 0x00
            ProtocolConstants.CMD_GROUP, # 0x82
            ProtocolConstants.BYTE4,     # 0x00
            PacketType.SETTINGS,         # 0x09
            0x33,                         # GPS location command
        ])
        # Add latitude and longitude as little-endian floats
        packet.extend(struct.pack('<f', latitude))
        packet.extend(struct.pack('<f', longitude))
        packet.append(ProtocolConstants.FOOTER)  # 0x83
        checksum = cls.calculate_checksum(packet)
        packet.append(checksum)
        return bytes(packet)

    @classmethod
    def set_gps_location(cls, latitude: float, longitude: float) -> bytes:
        """Set tracker GPS location for sun position calculations."""
        return cls.build_gps_location(latitude, longitude)

    @classmethod
    def build_query_command(cls, query_cmd: int) -> bytes:
        """
        Build a query command packet (Type 0x01).

        Args:
            query_cmd: Query command code (0x31=alarms, 0x32, 0x35, 0x36)

        Returns:
            9-byte command packet
        """
        packet = bytearray([
            ProtocolConstants.HEADER,    # 0x81
            ProtocolConstants.BYTE1,     # 0xFF
            ProtocolConstants.BYTE2,     # 0x00
            ProtocolConstants.CMD_GROUP, # 0x82
            ProtocolConstants.BYTE4,     # 0x00
            PacketType.ALARM,            # 0x01
            query_cmd,                   # Query command
            ProtocolConstants.FOOTER,    # 0x83
        ])
        checksum = cls.calculate_checksum(packet)
        packet.append(checksum)
        return bytes(packet)

    @classmethod
    def query_alarms(cls) -> bytes:
        """Query current alarm status (returns detailed alarm bitmask)."""
        return cls.build_query_command(QueryCommand.ALARM_QUERY)

    @classmethod
    def build_diagnostic_command(cls, diag_cmd: int, sub_cmd: int = 0x00) -> bytes:
        """
        Build a diagnostic command packet (Type 0x01, Cmd 0xF0-0xF2).

        Discovered from firmware analysis - used for debug/diagnostic modes.

        Packet format (10 bytes):
        81 FF 00 82 00 01 [CMD] [SUB] 83 [CHECKSUM]

        Args:
            diag_cmd: Diagnostic command (0xF0, 0xF1, 0xF2)
            sub_cmd: Sub-command byte (e.g., 0x0D for debug mode)

        Returns:
            10-byte command packet
        """
        packet = bytearray([
            ProtocolConstants.HEADER,    # 0x81
            ProtocolConstants.BYTE1,     # 0xFF
            ProtocolConstants.BYTE2,     # 0x00
            ProtocolConstants.CMD_GROUP, # 0x82
            ProtocolConstants.BYTE4,     # 0x00
            PacketType.ALARM,            # 0x01
            diag_cmd,                    # Diagnostic command
            sub_cmd,                     # Sub-command
            ProtocolConstants.FOOTER,    # 0x83
        ])
        checksum = cls.calculate_checksum(packet)
        packet.append(checksum)
        return bytes(packet)

    @classmethod
    def enter_debug_mode(cls) -> bytes:
        """
        Enter debug/diagnostic mode (CAUTION: use with care).

        Discovered from firmware - sends 0xF0 with sub-command 0x0D.
        """
        return cls.build_diagnostic_command(DiagnosticCommand.DIAG_DEBUG, 0x0D)

    @classmethod
    def query_firmware_info(cls) -> bytes:
        """Query firmware information (diagnostic command 0xF1)."""
        return cls.build_diagnostic_command(DiagnosticCommand.DIAG_FIRMWARE)

    @classmethod
    def build_extended_command(cls, ext_cmd: int, sub_cmd: int = 0x00) -> bytes:
        """
        Build an extended control command (0x41, 0x42).

        Discovered from firmware - used for advanced calibration and GPS operations.

        Args:
            ext_cmd: Extended command (0x41 or 0x42)
            sub_cmd: Sub-command byte

        Returns:
            10-byte command packet
        """
        packet = bytearray([
            ProtocolConstants.HEADER,    # 0x81
            ProtocolConstants.BYTE1,     # 0xFF
            ProtocolConstants.BYTE2,     # 0x00
            ProtocolConstants.CMD_GROUP, # 0x82
            ProtocolConstants.BYTE4,     # 0x00
            PacketType.ALARM,            # 0x01
            ext_cmd,                     # Extended command
            sub_cmd,                     # Sub-command
            ProtocolConstants.FOOTER,    # 0x83
        ])
        checksum = cls.calculate_checksum(packet)
        packet.append(checksum)
        return bytes(packet)

    @classmethod
    def query_gps_data(cls) -> bytes:
        """
        Query GPS/position data (extended command 0x42, sub-cmd 0x07).

        Discovered from firmware - accesses GPS/position data.
        """
        return cls.build_extended_command(QueryCommand.EXTENDED_CTRL_B, 0x07)

    @classmethod
    def build_config_command(cls, config_cmd: int, param1: int = 0, param2: int = 0) -> bytes:
        """
        Build a configuration command packet (Type 0x03).

        Discovered from COM capture - used for panel reset/zero operations.

        Packet format (11 bytes):
        81 FF 00 82 00 03 [CMD] [P1] [P2] 83 [CHECKSUM]

        Args:
            config_cmd: Configuration command (0x34 = reset/zero)
            param1: First parameter byte
            param2: Second parameter byte

        Returns:
            11-byte command packet
        """
        packet = bytearray([
            ProtocolConstants.HEADER,    # 0x81
            ProtocolConstants.BYTE1,     # 0xFF
            ProtocolConstants.BYTE2,     # 0x00
            ProtocolConstants.CMD_GROUP, # 0x82
            ProtocolConstants.BYTE4,     # 0x00
            PacketType.CONFIG,           # 0x03
            config_cmd,                  # Config command
            param1,                      # Parameter 1
            param2,                      # Parameter 2
            ProtocolConstants.FOOTER,    # 0x83
        ])
        checksum = cls.calculate_checksum(packet)
        packet.append(checksum)
        return bytes(packet)

    @classmethod
    def zero_panel(cls) -> bytes:
        """
        Zero/reset panel position (ZERAR PAINEL command).

        Resets the panel position counters to zero.
        """
        return cls.build_config_command(0x34, 0x00, 0x00)

    @classmethod
    def go_to_position(cls, position: int) -> bytes:
        """
        Move to a preset position (discovered from firmware analysis).

        Positions found in STS.2A_V2.31 firmware:
        - 1 (0x25): Unknown preset (firmware loads direction 4)
        - 2 (0x26): Possibly HOME position (firmware loads direction 5)
        - 3 (0x27): Possibly STOW position (firmware loads direction 6)

        Args:
            position: Preset position number (1, 2, or 3)

        Returns:
            10-byte movement command packet
        """
        position_map = {
            1: MovementCommand.GO_POSITION_1,  # 0x25
            2: MovementCommand.GO_POSITION_2,  # 0x26
            3: MovementCommand.GO_POSITION_3,  # 0x27
        }
        if position not in position_map:
            raise ValueError(f"Invalid position {position}. Must be 1, 2, or 3.")
        return cls.build_movement_command_v2(position_map[position])

    @classmethod
    def go_home(cls) -> bytes:
        """Move panel to HOME position (preset 2 - needs verification)."""
        return cls.go_to_position(2)

    @classmethod
    def go_stow(cls) -> bytes:
        """Move panel to STOW position (preset 3 - needs verification)."""
        return cls.go_to_position(3)

    @classmethod
    def build_datetime_command(cls, year: int, month: int, day: int,
                                hour: int, minute: int, second: int) -> bytes:
        """
        Build a date/time setting command packet.

        Discovered from HCS12 firmware analysis - RTC memory at 0x12CD-0x12D3.
        Uses Type 0x09 (SETTINGS), Command 0x32.

        Packet format (16 bytes):
        81 FF 00 82 00 09 32 [YEAR-2000] [MONTH] [DAY] [HOUR] [MIN] [SEC] 00 83 [CHECKSUM]

        Args:
            year: Full year (e.g., 2026)
            month: Month (1-12)
            day: Day of month (1-31)
            hour: Hour (0-23)
            minute: Minute (0-59)
            second: Second (0-59)

        Returns:
            16-byte command packet
        """
        # Validate inputs
        if not (2000 <= year <= 2255):
            raise ValueError(f"Year must be 2000-2255, got {year}")
        if not (1 <= month <= 12):
            raise ValueError(f"Month must be 1-12, got {month}")
        if not (1 <= day <= 31):
            raise ValueError(f"Day must be 1-31, got {day}")
        if not (0 <= hour <= 23):
            raise ValueError(f"Hour must be 0-23, got {hour}")
        if not (0 <= minute <= 59):
            raise ValueError(f"Minute must be 0-59, got {minute}")
        if not (0 <= second <= 59):
            raise ValueError(f"Second must be 0-59, got {second}")

        packet = bytearray([
            ProtocolConstants.HEADER,    # 0x81
            ProtocolConstants.BYTE1,     # 0xFF
            ProtocolConstants.BYTE2,     # 0x00
            ProtocolConstants.CMD_GROUP, # 0x82
            ProtocolConstants.BYTE4,     # 0x00
            PacketType.SETTINGS,         # 0x09
            0x32,                         # Date/time command (discovered from firmware)
            year - 2000,                 # Year offset from 2000
            month,                       # Month 1-12
            day,                         # Day 1-31
            hour,                        # Hour 0-23
            minute,                      # Minute 0-59
            second,                      # Second 0-59
            0x00,                        # Reserved
            ProtocolConstants.FOOTER,    # 0x83
        ])
        checksum = cls.calculate_checksum(packet)
        packet.append(checksum)
        return bytes(packet)

    @classmethod
    def set_datetime(cls, year: int, month: int, day: int,
                     hour: int, minute: int, second: int) -> bytes:
        """
        Set the tracker's internal clock.

        Args:
            year: Full year (e.g., 2026)
            month: Month (1-12)
            day: Day of month (1-31)
            hour: Hour (0-23)
            minute: Minute (0-59)
            second: Second (0-59)

        Returns:
            16-byte command packet
        """
        return cls.build_datetime_command(year, month, day, hour, minute, second)

    # =========================================================================
    # Response Parsing
    # =========================================================================

    # Response header for status packets
    RESPONSE_HEADER = bytes([0x81, 0x00, 0x01, 0x82, 0x00, 0x7c, 0x50])

    @classmethod
    def parse_response(cls, data: bytes) -> Optional[dict]:
        """
        Parse a response from the tracker.

        Response packet structure (discovered through reverse engineering):
        - Bytes 0-6: Header (81 00 01 82 00 7c 50)
        - Byte 8: Day
        - Byte 9: Month
        - Byte 10: Year (20xx)
        - Byte 11: Hour
        - Byte 12: Minute
        - Byte 13: Second
        - Bytes 19-22: Float 1 (big-endian) - possibly related to tracking
        - Bytes 25-28: Float 2 (big-endian) - horizontal angle
        - Bytes 29-32: Float 3 (big-endian) - vertical angle

        Args:
            data: Raw bytes received

        Returns:
            Parsed data dictionary, or None if parsing failed
        """
        if not data:
            return None

        result = {
            "raw": data.hex(),
            "length": len(data),
        }

        # Check for version string anywhere in the packet
        # Note: The tracker sometimes sends "Versio\x00n" with a null byte
        version_marker = b'Version '
        version_marker_alt = b'Versio\x00n '  # Alternative with null byte

        version_idx = -1
        if version_marker in data:
            version_idx = data.index(version_marker)
        elif version_marker_alt in data:
            version_idx = data.index(version_marker_alt)

        if version_idx >= 0:
            # Extract version (e.g., "2.31") - look for footer byte 0x83
            version_end = data.find(0x83, version_idx)
            if version_end > version_idx:
                version_str = data[version_idx:version_end].decode('ascii', errors='ignore')
            else:
                # No footer found, take next ~15 chars
                version_str = data[version_idx:version_idx+15].decode('ascii', errors='ignore').strip()
            # Clean up the version string (remove null bytes, normalize)
            version_str = version_str.replace('\x00', '').strip()
            result["version"] = version_str

        # Check for status response header
        OFF = ResponseOffsets  # Alias for readability
        if len(data) >= OFF.MIN_PACKET_SIZE and data[:OFF.HEADER_LENGTH] == cls.RESPONSE_HEADER:
            try:
                # Parse date/time
                result["date"] = {
                    "day": data[OFF.DAY],
                    "month": data[OFF.MONTH],
                    "year": 2000 + data[OFF.YEAR],
                    "second": data[OFF.SECOND],
                    "minute": data[OFF.MINUTE] if len(data) > OFF.MINUTE else 0,
                    "hour": data[OFF.HOUR] if len(data) > OFF.HOUR else 0,
                }

                # Parse float values (all little-endian)
                if len(data) >= OFF.ALARM_BYTE:
                    # Sun position
                    sun_azimuth = struct.unpack('<f', data[OFF.SUN_AZIMUTH:OFF.SUN_AZIMUTH + 4])[0]
                    sun_altitude = struct.unpack('<f', data[OFF.SUN_ALTITUDE:OFF.SUN_ALTITUDE + 4])[0]

                    result["sun_position"] = {
                        "azimuth": round(sun_azimuth, 2) if 0 <= sun_azimuth <= 360 else None,
                        "altitude": round(sun_altitude, 2) if -90 <= sun_altitude <= 90 else None,
                    }

                    # Panel position
                    panel_horizontal = struct.unpack('<f', data[OFF.PANEL_HORIZONTAL:OFF.PANEL_HORIZONTAL + 4])[0]
                    panel_vertical = struct.unpack('<f', data[OFF.PANEL_VERTICAL:OFF.PANEL_VERTICAL + 4])[0]

                    result["position"] = {
                        "horizontal": round(panel_horizontal, 2) if 0 <= panel_horizontal <= 360 else None,
                        "vertical": round(panel_vertical, 2) if 0 <= panel_vertical <= 90 else None,
                    }

                # Parse mode from byte [7]
                # 0x00 = AUTO (default tracking mode), 0x01 = MANUAL (override)
                # In practice, byte 7 is 0x00 when tracker is auto-tracking the sun
                mode_byte = data[OFF.MODE_BYTE]
                is_auto_mode = (mode_byte != 0x01)

                # Also read status flags at byte [20] for additional state info
                status_flags = data[OFF.STATUS_FLAGS] if len(data) > OFF.STATUS_FLAGS else 0

                result["status_flags"] = {
                    "raw": status_flags,
                    "mode_byte": mode_byte,
                    "is_auto_mode": is_auto_mode,
                    "is_error_state": (status_flags & 0xC0) == 0xC0,  # High bits indicate error
                }

                # Parse alarm bitmask
                if len(data) > OFF.ALARM_BYTE:
                    alarm_byte = data[OFF.ALARM_BYTE]
                    alarm_list = []

                    # Ignore corrupt packets (all bits set = garbage data)
                    if alarm_byte >= 0xF0:
                        alarm_byte = 0

                    # Decode alarm bits
                    # Mappings based on STcontrol V4.0.4.0 alarm messages
                    # "fim de curso" = end of travel / limit switch
                    if alarm_byte & 0x01:  # Bit 0 - Vertical limit
                        alarm_list.append("vertical_limit")
                    if alarm_byte & 0x02:  # Bit 1 - Unknown (previously thought tilt limit)
                        alarm_list.append("unknown_alarm_1")
                    if alarm_byte & 0x04:  # Bit 2 - West limit
                        alarm_list.append("west_limit")
                    if alarm_byte & 0x08:  # Bit 3 - Tilt limit / panel flat (stow position)
                        alarm_list.append("tilt_limit_flat")
                    if alarm_byte & 0x10:  # Bit 4 - Actuator motor current
                        alarm_list.append("actuator_current")
                    if alarm_byte & 0x20:  # Bit 5 - Rotation motor current
                        alarm_list.append("rotation_current")
                    if alarm_byte & 0x40:  # Bit 6 - Unknown (previously thought to be horizontal limit)
                        alarm_list.append("unknown_alarm_6")
                    if alarm_byte & 0x80:  # Bit 7 - Encoder error
                        alarm_list.append("encoder_error")

                    result["alarms"] = {
                        "active": alarm_byte != 0,
                        "code": alarm_byte,
                        "list": alarm_list,
                    }

            except Exception as e:
                result["parse_error"] = str(e)

        return result

    @classmethod
    def validate_packet(cls, data: bytes) -> bool:
        """
        Validate a received packet's checksum.

        Args:
            data: Complete packet including checksum

        Returns:
            True if checksum is valid
        """
        if len(data) < 2:
            return False

        expected_checksum = cls.calculate_checksum(data[:-1])
        actual_checksum = data[-1]

        return expected_checksum == actual_checksum


# Convenience functions
def build_command(direction: str, start: bool = True) -> bytes:
    """
    Build a movement command from direction string.

    Args:
        direction: 'up', 'down', 'left', 'right', or 'stop'
        start: True for start, False for stop

    Returns:
        Command packet bytes
    """
    direction_map = {
        'up': Direction.UP,
        'down': Direction.DOWN,
        'left': Direction.LEFT,
        'right': Direction.RIGHT,
        'stop': Direction.STOP,
    }

    dir_code = direction_map.get(direction.lower(), Direction.STOP)
    return SolarTrackerProtocol.build_movement_command(dir_code, start)
