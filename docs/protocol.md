# Metalogalva Solar Tracker Serial Protocol

## Overview

This document describes the serial protocol used by the Metalogalva solar tracker, reverse-engineered from STcontrol V4.0.4.0.exe.

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

## Command Types (Byte 6)

### Movement Commands (Type 0x02)

| Value | ASCII | Description |
|-------|-------|-------------|
| 0x23 | '#' | Start movement |
| 0x24 | '$' | Stop movement |

### Alarm Commands (Type 0x01)

| Value | ASCII | Description |
|-------|-------|-------------|
| 0x40 | '@' | Clear all alarms |

### Status Commands (Type 0x08)

| Value | ASCII | Description |
|-------|-------|-------------|
| 0x30 | '0' | Request current status |

## Direction Codes (Byte 7)

| Value | Direction |
|-------|-----------|
| 0x00 | Stop |
| 0x01 | Down (Tilt down) |
| 0x02 | Up (Tilt up) |
| 0x03 | Left (Rotate West) |
| 0x04 | Right (Rotate East) |

## Checksum Calculation

The checksum is calculated as the sum of bytes 0-8, modulo 256:

```python
def calculate_checksum(data: bytes) -> int:
    """Calculate checksum for a 9-byte packet."""
    return sum(data[:9]) & 0xFF
```

## Example Commands

### Start Moving Down

```
81 FF 00 82 00 02 23 01 83 AB
```
- Command: 0x23 (Start)
- Direction: 0x01 (Down)
- Checksum: 0xAB

### Stop Moving Down

```
81 FF 00 82 00 02 24 01 83 AC
```
- Command: 0x24 (Stop)
- Direction: 0x01 (Down)
- Checksum: 0xAC

### Start Moving Up

```
81 FF 00 82 00 02 23 02 83 AC
```
- Command: 0x23 (Start)
- Direction: 0x02 (Up)
- Checksum: 0xAC

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

- [ ] **Set Auto/Manual mode** (CRITICAL - likely packet type 0x03 with unknown parameters)
- [ ] Set East/West limits (uses 16-byte packets with float values)
- [ ] Set max wind threshold
- [ ] Time synchronization

---

*Protocol reverse-engineered from STcontrol V4.0.4.0.exe using radare2*
*Response format discovered through empirical analysis (January 2026)*
