# Metalogalva Solar Tracker Serial Protocol

## Overview

This document describes the serial protocol used by the Metalogalva solar tracker (STS.2A firmware V2.31).

**Reverse engineering sources:**
- STcontrol V4.0.4.0.exe (Windows control application)
- Direct COM port capture with Device Monitoring Studio (February 2026)
- HCS12 firmware disassembly (STS.2A_V2.31.abs.s19)

## Connection Settings

| Parameter | Value |
|-----------|-------|
| Baud Rate | 9600 (default, configurable) |
| Data Bits | 8 |
| Parity | None |
| Stop Bits | 1 |
| Flow Control | None |

## Packet Structure

The protocol uses variable-length packets with different structures based on the packet type (byte 5).

### Movement Commands (10 bytes, type 0x02)

```
+------+------+------+------+------+------+------+------+------+----------+
| 0x81 | 0xFF | 0x00 | 0x82 | 0x00 | 0x02 | CMD  | DIR  | 0x83 | CHECKSUM |
+------+------+------+------+------+------+------+------+------+----------+
  [0]    [1]    [2]    [3]    [4]    [5]    [6]    [7]    [8]      [9]
```

### Clear Alarms Command (9 bytes, type 0x01)

```
+------+------+------+------+------+------+------+------+----------+
| 0x81 | 0xFF | 0x00 | 0x82 | 0x00 | 0x01 | 0x40 | 0x83 | CHECKSUM |
+------+------+------+------+------+------+------+------+----------+
  [0]    [1]    [2]    [3]    [4]    [5]    [6]    [7]      [8]
```

### Status Request (9 bytes, type 0x08)

```
+------+------+------+------+------+------+------+------+----------+
| 0x81 | 0xFF | 0x00 | 0x82 | 0x00 | 0x08 | 0x30 | 0x83 | CHECKSUM |
+------+------+------+------+------+------+------+------+----------+
  [0]    [1]    [2]    [3]    [4]    [5]    [6]    [7]      [8]
```

### Byte Descriptions

| Byte | Value | Description |
|------|-------|-------------|
| 0 | 0x81 | Header / Device address |
| 1 | 0xFF | Broadcast/Unknown (constant) |
| 2 | 0x00 | Reserved (constant) |
| 3 | 0x82 | Command group identifier |
| 4 | 0x00 | Reserved (constant) |
| 5 | TYPE | Packet type: 0x01=alarm, 0x02=movement, 0x08=status |
| 6 | CMD | Command type (see below) |
| 7 | DIR/FOOTER | Direction (for movement) or Footer (0x83 for others) |
| 8 | 0x83/CHECKSUM | Footer marker (movement) or Checksum (others) |
| 9 | CHECKSUM | Checksum (movement only) |

## Packet Types (Byte 5)

| Type | Size | Description |
|------|------|-------------|
| 0x01 | 9 | Mode/Query/Alarm commands |
| 0x02 | 10 | Movement commands |
| 0x03 | 11 | Configuration commands |
| 0x08 | 9 | Status request |
| 0x09 | 16 | Settings commands (GPS location) |

## Command Reference (Byte 6)

### Movement Commands (Type 0x02) - CORRECTED Feb 2026

**Format:** `81 FF 00 82 00 02 [CMD] 01 83 [CHECKSUM]`

| Cmd | Hex | Description | Full Packet |
|-----|-----|-------------|-------------|
| RIGHT | 0x20 | Rotate East | `81 FF 00 82 00 02 20 01 83 A8` |
| LEFT | 0x21 | Rotate West | `81 FF 00 82 00 02 21 01 83 A9` |
| UP | 0x22 | Tilt up | `81 FF 00 82 00 02 22 01 83 AA` |
| DOWN | 0x23 | Tilt down | `81 FF 00 82 00 02 23 01 83 AB` |
| STOP | 0x24 | Stop all | `81 FF 00 82 00 02 24 01 83 AC` |
| POS_1 | 0x25 | Preset position 1 (from firmware) | `81 FF 00 82 00 02 25 01 83 AD` |
| POS_2 | 0x26 | Preset position 2 - HOME? (from firmware) | `81 FF 00 82 00 02 26 01 83 AE` |
| POS_3 | 0x27 | Preset position 3 - STOW? (from firmware) | `81 FF 00 82 00 02 27 01 83 AF` |

**Note:** Byte 7 is always 0x01 for movement commands.

### Mode Commands (Type 0x01) - CONFIRMED Feb 2026

**Format:** `81 FF 00 82 00 01 [CMD] 83 [CHECKSUM]`

| Cmd | Hex | Description | Full Packet |
|-----|-----|-------------|-------------|
| MANUAL | 0x10 | Switch to manual mode | `81 FF 00 82 00 01 10 83 96` |
| AUTO | 0x11 | Switch to automatic mode | `81 FF 00 82 00 01 11 83 97` |

### Query Commands (Type 0x01)

| Cmd | Hex | Description | Full Packet |
|-----|-----|-------------|-------------|
| ALARM_QUERY | 0x31 | Query alarm status | `81 FF 00 82 00 01 31 83 B7` |
| QUERY_32 | 0x32 | Unknown query | `81 FF 00 82 00 01 32 83 B8` |
| QUERY_35 | 0x35 | Unknown query | `81 FF 00 82 00 01 35 83 BB` |
| QUERY_36 | 0x36 | Unknown query | `81 FF 00 82 00 01 36 83 BC` |
| CLEAR_ALARMS | 0x40 | Clear all alarms | `81 FF 00 82 00 01 40 83 C6` |

### Configuration Commands (Type 0x03) - NEW Feb 2026

**Format:** `81 FF 00 82 00 03 [CMD] [P1] [P2] 83 [CHECKSUM]`

| Cmd | Hex | Description | Full Packet |
|-----|-----|-------------|-------------|
| ZERO_PANEL | 0x34 | Reset panel position (ZERAR PAINEL) | `81 FF 00 82 00 03 34 00 00 83 BC` |

### Status Commands (Type 0x08)

| Cmd | Hex | Description | Full Packet |
|-----|-----|-------------|-------------|
| STATUS | 0x30 | Request current status | `81 FF 00 82 00 08 30 83 BD` |

### Settings Commands (Type 0x09) - NEW Feb 2026

**Format:** `81 FF 00 82 00 09 [CMD] [DATA...] 83 [CHECKSUM]`

| Cmd | Hex | Description | Data Format |
|-----|-----|-------------|-------------|
| DATE_TIME | 0x32 | Set tracker date/time | 7 bytes: YEAR MONTH DAY HOUR MIN SEC 00 |
| GPS_LOCATION | 0x33 | Set tracker GPS location | 8 bytes: LAT (float32 LE) + LON (float32 LE) |

**Example Date/Time command (16 bytes):**
```
81 FF 00 82 00 09 32 1A 02 0E 0A 1E 00 00 83 XX
                    [Y][M][D][H][M][S][R]
Year:   26 (0x1A) = 2026
Month:  2  (0x02) = February
Day:    14 (0x0E) = 14th
Hour:   10 (0x0A) = 10:00
Minute: 30 (0x1E) = :30
Second: 0  (0x00) = :00
Reserved: 0x00
```

**Example GPS command (16 bytes):**
```
81 FF 00 82 00 09 33 06 2D 22 42 39 2E 0B C1 83 8B
                    └──LAT──┘ └──LON──┘
Latitude:  40.5440° N (bytes 06 2D 22 42 as little-endian float)
Longitude: -8.6988° W (bytes 39 2E 0B C1 as little-endian float)
Location: Portugal (Coimbra/Aveiro region)
```

## Legacy Direction Codes (Deprecated)

These were the old interpretation before direct serial capture:

| Value | Direction |
|-------|-----------|
| 0x00 | Stop |
| 0x01 | Down (Tilt down) |
| 0x02 | Up (Tilt up) |
| 0x03 | Left (Rotate West) |
| 0x04 | Right (Rotate East) |

**Note:** The actual protocol uses command codes 0x20-0x27 directly, not direction bytes.

## Checksum Calculation

The checksum is calculated as the sum of bytes 0-8, modulo 256:

```python
def calculate_checksum(data: bytes) -> int:
    """Calculate checksum for a 9-byte packet."""
    return sum(data[:9]) & 0xFF
```

## Example Commands

### Movement Commands (Corrected Feb 2026)

```
Move Down:  81 FF 00 82 00 02 23 01 83 AB  (Cmd 0x23 = DOWN)
Move Up:    81 FF 00 82 00 02 22 01 83 AA  (Cmd 0x22 = UP)
Move Left:  81 FF 00 82 00 02 21 01 83 A9  (Cmd 0x21 = LEFT/West)
Move Right: 81 FF 00 82 00 02 20 01 83 A8  (Cmd 0x20 = RIGHT/East)
Stop All:   81 FF 00 82 00 02 24 01 83 AC  (Cmd 0x24 = STOP)
```

### Mode Commands

```
Manual Mode: 81 FF 00 82 00 01 10 83 96
Auto Mode:   81 FF 00 82 00 01 11 83 97
```

## Firmware-Discovered Commands (from STS.2A_V2.31)

Complete analysis of HCS12 firmware revealed 23 total commands:

### Preset Position Commands (Type 0x02)

| Cmd | Hex | Description | Status |
|-----|-----|-------------|--------|
| POS_1 | 0x25 | Preset position 1 | Implemented (untested) |
| POS_2 | 0x26 | Preset position 2 (HOME?) | Implemented (untested) |
| POS_3 | 0x27 | Preset position 3 (STOW?) | Implemented (untested) |

### Extended Control Commands (Type 0x01)

| Cmd | Hex | Sub-cmds | Description | Status |
|-----|-----|----------|-------------|--------|
| EXTENDED_CTRL_A | 0x41 | 0x02, 0x03, 0x0A | Advanced calibration | Implemented (untested) |
| EXTENDED_CTRL_B | 0x42 | 0x03, 0x07 | GPS/Position data operations | Implemented (untested) |

**Example: Query GPS Data**
```
81 FF 00 82 00 01 42 07 83 [CHECKSUM]
```

### Diagnostic Commands (Type 0x01) - USE WITH CAUTION

| Cmd | Hex | Sub-cmd | Description | Status |
|-----|-----|---------|-------------|--------|
| DIAG_DEBUG | 0xF0 | 0x0D | Enter debug/diagnostic mode | Implemented (untested) |
| DIAG_FIRMWARE | 0xF1 | - | Firmware information | Implemented (untested) |
| DIAG_EXTENDED | 0xF2 | - | Extended diagnostics | Implemented (untested) |

**Warning:** Diagnostic commands may put the tracker in unexpected states. Use only for debugging.

### Memory Locations (HCS12 Firmware)

| Address | Purpose |
|---------|---------|
| 0x1854 | Movement direction register |
| 0x1859 | Movement enable flag |
| 0x185A | Secondary movement flag |
| 0x12CD-0x12D3 | RTC memory (date/time) |
| 0x12CE-0x12D2 | GPS/position data |
| 0x15B0-0x15B2 | Secondary position data |
| 0x1501 | Debug mode flag |

### Default Calibration Constants (from 0x30BE00)

| Value | Purpose |
|-------|---------|
| 41.25° | Default Latitude (northern Portugal) |
| -8.30° | Default Longitude (northern Portugal) |
| 85.0° | Maximum elevation angle |
| 270.0° | Azimuth reference (West) |
| 5.0 m/s | Wind speed threshold |

### Date/Time Validation Ranges

| Field | Range | Hex Max |
|-------|-------|---------|
| Month | 1-12 | 0x0C |
| Day | 1-31 | 0x1F |
| Hour | 0-23 | 0x17 |
| Minute | 0-59 | 0x3B |
| Second | 0-59 | 0x3B |

### Stop Moving Up

```
81 FF 00 82 00 02 24 02 83 AD
```

### Start Moving Left (West)

```
81 FF 00 82 00 02 23 03 83 AD
```

### Start Moving Right (East)

```
81 FF 00 82 00 02 23 04 83 AE
```

### Clear All Alarms

```
81 FF 00 82 00 01 40 83 C6
```
- Packet Type: 0x01 (Alarm)
- Command: 0x40 ('@' - Clear alarms)
- Checksum: 0xC6 (sum of bytes 0-7)

### Request Status

```
81 FF 00 82 00 08 30 83 BD
```
- Packet Type: 0x08 (Status)
- Command: 0x30 ('0' - Request status)
- Checksum: 0xBD (sum of bytes 0-7)

## Python Implementation

```python
def build_movement_command(direction: int, start: bool = True) -> bytes:
    """
    Build a movement command packet.

    Args:
        direction: 0=stop, 1=down, 2=up, 3=left, 4=right
        start: True for start command, False for stop

    Returns:
        10-byte command packet
    """
    cmd = 0x23 if start else 0x24
    packet = bytes([0x81, 0xFF, 0x00, 0x82, 0x00, 0x02, cmd, direction, 0x83])
    checksum = sum(packet) & 0xFF
    return packet + bytes([checksum])
```

## Notes

- Commands are sent when mouse button is pressed (start) and released (stop)
- The tracker moves continuously while the command is active
- A stop command should always be sent when releasing the control

## Discovered Commands Summary

| Command | Byte 5 | Byte 6 | Size | Status |
|---------|--------|--------|------|--------|
| Movement Start | 0x02 | 0x23 | 10 | Implemented |
| Movement Stop | 0x02 | 0x24 | 10 | Implemented |
| Clear Alarms | 0x01 | 0x40 | 9 | Implemented |
| Request Status | 0x08 | 0x30 | 9 | Implemented |

## Status Response Format

The tracker responds to status requests with packets of 38+ bytes. Extended packets (134+ bytes) include firmware version string.

### Response Header

```
81 00 01 82 00 7c 50
```

Note: The 0x7c (124) byte may indicate expected payload length.

### Response Packet Structure (38 bytes minimum)

```
┌────────┬────────┬─────────────┬────────────────────────────────┐
│ Offset │ Length │ Type        │ Description                    │
├────────┼────────┼─────────────┼────────────────────────────────┤
│ 0-6    │ 7      │ bytes       │ Header: 81 00 01 82 00 7c 50   │
│ 7      │ 1      │ byte        │ Reserved/Unknown               │
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
│ 34-35  │ 2      │ bytes       │ Reserved/Padding               │
│ 36     │ 1      │ uint8       │ Alarm bitmask                  │
│ 37     │ 1      │ bytes       │ Reserved/Padding               │
└────────┴────────┴─────────────┴────────────────────────────────┘
```

### Float Values

All float values are IEEE 754 single-precision (32-bit) in **little-endian** byte order.

### Alarm Bitmask (Byte 36)

| Bit | Mask | Alarm Type | Portuguese | Description |
|-----|------|------------|------------|-------------|
| 0 | 0x01 | Vertical limit | fim de curso vertical | Rotation limit reached |
| 1 | 0x02 | Tilt limit (flat) | fim de curso horizontal | Panel is flat/horizontal (stow position) |
| 2 | 0x04 | West limit | - | TBD |
| 3 | 0x08 | Wind speed exceeded | limite de vento excedido | Wind threshold exceeded |
| 4 | 0x10 | Actuator motor current | - | Tilt motor overcurrent |
| 5 | 0x20 | Rotation motor current | - | Rotation motor overcurrent |
| 6 | 0x40 | Unknown | - | TBD |
| 7 | 0x80 | Encoder error | erro no encoder do motor actuador | Encoder/limit sensor malfunction - BLOCKS ALL MOVEMENT until cleared |

**Note:** The "tilt limit flat" alarm (bit 1) is **normal when stowed** - it indicates the panel is tilted to its maximum flat position for wind protection. The Portuguese "fim de curso horizontal" refers to the panel surface being horizontal, not the rotation axis.

### Extended Response (134+ bytes)

Extended packets include firmware version string near the end:
- Marker: `Version ` (or `Versio\x00n ` with null byte)
- Followed by version number (e.g., `2.31`)
- Terminated by footer byte `0x83`

### Example Response Parsing (Python)

```python
import struct

def parse_response(data: bytes) -> dict:
    if len(data) < 38:
        return None

    return {
        "date": {
            "day": data[8],
            "month": data[9],
            "year": 2000 + data[10],
            "second": data[11],
            "minute": data[12],
            "hour": data[13],
        },
        "panel_vertical": struct.unpack('<f', data[16:20])[0],
        "panel_horizontal": struct.unpack('<f', data[22:26])[0],
        "sun_altitude": struct.unpack('<f', data[26:30])[0],
        "sun_azimuth": struct.unpack('<f', data[30:34])[0],
        "alarm_byte": data[34],
    }
```

## Status/Mode Flags (Byte 20)

Byte 20 contains status and mode flags.

### Observed Values

| Value | Binary | State |
|-------|--------|-------|
| 0xCF | 11001111 | **Error/Alarm state** - Tracker not functioning |
| 0x0E | 00001110 | **Active tracking** - Auto mode, following sun |

### Bit Analysis (tentative)

- Bits 6-7 (0xC0): When set, indicate error state
- Bits 1-3 (0x0E): Active when tracking normally
- Bit 0: Unknown

### Important Discovery

When the tracker shows status 0xCF:
- The **Clear Alarms command (0x40)** must be sent
- This changes status to 0x0E and enables tracking
- The tracker then automatically moves to track the sun

**Note:** Previously this byte was incorrectly documented as the alarm bitmask. The actual alarm byte is at offset 34.

## Known Issues

### Clear Alarms Required on Startup

When the tracker shows status byte 0xCF (error state), send the **Clear Alarms command**:
```
81 FF 00 82 00 01 40 83 C6
```
This clears the error state and enables automatic sun tracking.

### Encoder Error / Motor Actuator Error ("Erro no encoder do motor actuador")

**Critical Issue:** When the tilt axis encoder fails to detect the end-of-travel position, the actuator motor continues past its intended limit, potentially tilting the panel in the wrong direction.

**Symptoms:**
- Panel tilts past horizontal (>90° vertical reading)
- `tilt_limit_flat` alarm (0x02) active but movement doesn't stop
- After stopping, all movement commands are blocked in both directions

**Behavior when encoder error is active:**
- The tracker will NOT respond to any movement commands (up, down, left, right)
- Manual mode commands are ignored
- Auto tracking is disabled

**Recovery procedure:**
1. **Clear alarms** - This re-enables movement commands
2. **Manually reposition** - Move the panel back to a safe position
3. **Inspect hardware** - The encoder/limit sensor needs physical inspection

**Root cause:** The encoder or limit switch on the tilt actuator is not detecting the end-of-travel position. This is a hardware issue requiring physical repair - typically:
- Faulty limit switch
- Damaged encoder
- Wiring issue
- Mechanical obstruction preventing sensor activation

**Warning:** After clearing alarms, if you command movement toward the faulty limit, the panel will overshoot again. Only move in the opposite direction until the sensor is repaired.

### Rotation Encoder Reading in Auto Mode

**Note:** When in auto tracking mode (byte[7]=0x00), the horizontal position at bytes [20-24] may read as 0.00°. This does NOT necessarily indicate an encoder failure.

In auto mode:
- The actual panel horizontal position is at bytes [30-34]
- This value tracks the sun azimuth (within ~0.2°)
- The tracker is functioning correctly even if [20-24] shows 0.00°

**True encoder failure symptoms:**
- Panel physically doesn't rotate when sun moves
- STcontrol shows "encoder error" alarm
- Alarm byte includes 0x80 (encoder_error bit)
- Manual rotation commands have no effect AND [30-34] doesn't track sun

### Alarm Query Command (DISCOVERED February 2026)

**IMPORTANT:** The full alarm bitmask is NOT in the standard status response (byte 37). Instead, use the **Type 0x01, Command 0x31** query to get accurate alarm information.

#### Alarm Query Command (9 bytes)

```
+------+------+------+------+------+------+------+------+----------+
| 0x81 | 0xFF | 0x00 | 0x82 | 0x00 | 0x01 | 0x31 | 0x83 | CHECKSUM |
+------+------+------+------+------+------+------+------+----------+
  [0]    [1]    [2]    [3]    [4]    [5]    [6]    [7]      [8]
```

Checksum: `0xB9` (sum of bytes 0-7)

Full command: `81 FF 00 82 00 01 31 83 B9`

#### Alarm Query Response

The response includes a **short packet** containing the alarm bitmask:

```
+------+------+------+------+------+------+-------+------+----------+
| 0x81 | 0x00 | 0x01 | 0x82 | 0x00 | 0x01 | ALARM | 0x83 | CHECKSUM |
+------+------+------+------+------+------+-------+------+----------+
  [0]    [1]    [2]    [3]    [4]    [5]    [6]     [7]      [8]
```

**Byte [6] contains the actual alarm bitmask.**

#### Alarm Bitmask (from Query Response)

| Bit | Mask | Alarm Type | Description |
|-----|------|------------|-------------|
| 0 | 0x01 | Vertical limit | Tilt axis vertical limit |
| 1 | 0x02 | Tilt limit (flat) | Panel at flat/stow position |
| 2 | 0x04 | East/West limit | Rotation axis limit reached |
| 3 | 0x08 | Wind speed | Wind threshold exceeded |
| 4 | 0x10 | Actuator current | Tilt motor overcurrent |
| 5 | 0x20 | Rotation current | Rotation motor overcurrent |
| 6 | 0x40 | Unknown | TBD |
| 7 | 0x80 | Encoder error | Motor actuator encoder fault - BLOCKS ALL MOVEMENT |

#### Example

Query: `81 FF 00 82 00 01 31 83 B9`

Response includes: `81 00 01 82 00 01 86 83 0E`

Alarm byte: **0x86** = 10000110
- Bit 7 (0x80): Encoder error ✓
- Bit 2 (0x04): East/West limit ✓
- Bit 1 (0x02): Tilt limit flat ✓

#### Why Byte [37] in Status Response Differs

The standard status response (Type 0x08) only shows a **subset** of alarms in byte [37]. This appears to be position-related status flags only (e.g., tilt_limit_flat). For the **complete alarm state**, always use the Type 0x01 Command 0x31 query.

#### Important: Short Packet Appearance is Conditional

**NOTE:** The short alarm packet may not always appear in the response. During testing, it was observed to:
- Appear reliably when multiple alarms are active (encoder error + limit)
- Stop appearing after alarms are cleared or tracker state changes
- Possibly only appear when there are NEW or ACTIVE alarms to report

If the short packet is not present, fall back to reading byte [37] from the standard status response, understanding it may only show a subset of alarms.

**Recommended approach:**
1. Send Type 0x01 Command 0x31
2. Search response for short packet pattern `81 00 01 82 00 01 XX 83`
3. If found, XX is the full alarm bitmask
4. If not found, use byte [37] from standard status as fallback

### Packet Mode Byte [7] - Two Response Formats

The response packet has two different structures depending on byte [7]:

#### Mode 0x01 (Manual Mode / Detailed Status)
```
Byte [7]  = 0x01
Byte [8]  = Day
Byte [9]  = Month
Byte [10] = Year (offset from 2000)
Byte [11] = Second
Byte [12] = Minute
Byte [13] = Hour
Bytes [16-19] = Panel Vertical/Tilt (float, degrees)
Bytes [22-25] = Panel Horizontal (float, degrees)
Bytes [26-29] = Sun Altitude (float, degrees)
Bytes [30-33] = Sun Azimuth (float, degrees)
Byte [37] = Alarm/status flags
```

#### Mode 0x00 (Auto Tracking Mode)
```
Byte [7]  = 0x00
Bytes [8-15] = Date/time (different format)
Bytes [16-19] = Panel Tilt (float, degrees from vertical)
Bytes [22-25] = Sun Azimuth (float, degrees)
Bytes [26-29] = Sun Altitude (float, degrees)
Bytes [30-33] = Panel Horizontal / Target (float, degrees - tracks sun azimuth)
Byte [37] = 0x00
```

**Key Discovery (February 2026):**
- **Mode 0x00 = AUTO TRACKING MODE** (not an error state!)
- When byte[7]=0x00, the tracker is actively following the sun
- [30:34] closely matches sun azimuth (within 0.2°) and changes as sun moves
- Panel tilt [16:20] shows current tilt angle from vertical
- Verified by physical observation: panel orientation matches reported values

**Observations:**
- Mode 0x01: Used during manual control, provides detailed position data
- Mode 0x00: Active during automatic sun tracking
- The horizontal encoder reading may show 0.00° but [30:34] shows actual tracking position

### Additional Status Bytes Discovered (February 2026)

During testing, these bytes were found to contain dynamic data:

| Byte | Observed Values | Likely Purpose |
|------|-----------------|----------------|
| [14] | 0x0A-0xE4 (varies rapidly) | Movement counter, encoder position, or ADC value |
| [15] | 0x01-0x08 (increments) | Movement duration counter - increments during active movement |
| [37] | 0x02 (constant) | Tilt position indicator (not clearable alarm) |

**Key observations:**
- Byte [37] = 0x02 (tilt_limit_flat) remains set even when panel is at 62° (not flat), suggesting it's a latched status or has different meaning
- Bytes [14-15] appear to be movement/encoder related counters, not alarm flags
- The encoder error (0x80) and horizontal/rotation limit alarms shown in STcontrol are NOT visible in bytes [36-37]
- Rotation movement commands are blocked while tilt commands work - suggesting separate alarm handling per axis

### Manual Movement Commands Not Working in Auto Mode

Movement commands (type 0x02) are correctly formatted and acknowledged, but **no physical movement occurs when in AUTO mode** (status 0x0E). The tracker prioritizes sun tracking over manual commands.

To enable manual control, a **mode switch command** is needed (not yet discovered). Likely candidates:
- Packet type 0x03 with specific parameters
- Or a completely different command structure

### Recommended Next Steps for Manual Mode

1. **Capture real traffic** - Run STcontrol.exe on a Windows machine with a serial sniffer to capture:
   - The exact command sent when clicking "CONTROLO MANUAL" button
   - The mode switch sequence
2. **Check physical controls** - Some trackers have a physical Auto/Manual switch
3. **Contact manufacturer** - Request protocol documentation from Metalogalva

## TODO: Additional Commands

The following commands still need further investigation:

- [x] **Set Auto/Manual mode** - IMPLEMENTED (Type 0x01, Cmd 0x10=manual, 0x11=auto)
- [x] **Time synchronization** - IMPLEMENTED (Type 0x09, Cmd 0x32 - from firmware analysis)
- [ ] Set East/West limits (uses 16-byte packets with float values)
- [ ] Set max wind threshold

---

*Protocol reverse-engineered from STcontrol V4.0.4.0.exe using radare2*
*Response format discovered through empirical analysis (January 2026)*
