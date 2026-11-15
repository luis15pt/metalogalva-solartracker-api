# Metalogalva Solar Tracker Serial Protocol (STS.2A firmware V2.31)

Re-derived in November 2026 from two independent sources that agree with each other:

- **Firmware** `STS.2A_V2.31.abs.s19` (Freescale HCS12), disassembled: SCI0 receive ISR `0xF3DD`,
  frame validator `0xF158`, command dispatcher `0x56E0`, frame transmitter `0xF1B1`,
  status builder `0x609B`, alarm latch `0x67EF`.
- **STcontrol V4.0.4.0.exe** (Delphi): every command builder, and the receive parser
  `ComPort1RxChar` at `0x48626C`.

Confidence markers used below: **[FW]** read from firmware, **[APP]** read from the Windows app,
**[LIVE]** seen on the real tracker. On 2026-11-15 live status frames were captured and decoded
with valid checksums (132 bytes, one per second), confirming the frame format and status layout.
No command has been re-tested by transmitting to the tracker.

This replaces the earlier document, which had several errors. See "Corrections" at the end.

## Link

9600 baud, 8N1, no flow control. The tracker is address `0x01`; the PC uses `0x00`.

## Frame format [FW][APP]

```
81  DST  SRC  82  LEN_HI  LEN_LO  CMD  DATA[LEN-1]  83  CHK
```

| Field | Meaning |
|-------|---------|
| `81` | Start of frame. The receiver ignores everything until it sees `0x81`. |
| DST | Destination address. The tracker accepts `0x01` or `0xFF` (broadcast). |
| SRC | Sender address. Replies are sent back to it. STcontrol uses `0x00`. |
| `82` | Fixed. |
| LEN | 16-bit big-endian count of CMD + DATA bytes. |
| CMD | Command code. |
| DATA | LEN-1 bytes. |
| `83` | End marker, at offset LEN+6. |
| CHK | Sum of every preceding byte, modulo 256. |

Total frame size is LEN + 8. There are no "packet types": what the old document called
type `0x01`/`0x02`/`0x03`/`0x08`/`0x09` is simply LEN.

The tracker ends a received frame on an inter-byte timeout, then checks length, `82`, `83`,
address and checksum. A frame that fails any check is dropped silently. Receive buffer is 300 bytes.

## Tracker → PC

### Status broadcast, CMD `0x50` (unsolicited) [FW][APP]

The tracker sends this by itself, once per second [LIVE], to DST `0x00`.
**There is no status-request command.** It stops only while the tracker is in firmware-update mode.

LEN is `0x7C` (132-byte frame) on V2.31. STcontrol also accepts LEN `0x70` (older firmware
without the version string).

| Offset | Size | Type | Field |
|--------|------|------|-------|
| 0–6 | 7 | | Header `81 00 01 82 00 7C 50` |
| 7 | 1 | u8 | Mode: `0` = automatic, `1` = manual (stored in flash) |
| 8 | 1 | u8 | Day |
| 9 | 1 | u8 | Month |
| 10 | 1 | u8 | Year − 2000 |
| 11 | 1 | u8 | Second |
| 12 | 1 | u8 | Minute |
| 13 | 1 | u8 | Hour (the clock is UTC) |
| 14–15 | 2 | i16 LE | Actuator (tilt) encoder pulse counter, low 16 bits |
| 16–19 | 4 | f32 LE | Panel altitude, degrees (90 = flat, lower = more upright) |
| 20–21 | 2 | i16 LE | Rotation encoder pulse counter, low 16 bits |
| 22–25 | 4 | f32 LE | Panel azimuth, degrees |
| 26–29 | 4 | f32 LE | Sun altitude, degrees |
| 30–33 | 4 | f32 LE | Sun azimuth, degrees |
| 34–35 | 2 | i16 LE | Wind speed, km/h |
| 36–37 | 2 | u16 LE | Alarm word (16 bits, see below) |
| 38–117 | 80 | 16 × 5 | Alarm log: one entry per alarm bit |
| 118–129 | 12 | ASCII | `Version 2.31` |
| 130 | 1 | | `83` |
| 131 | 1 | | Checksum |

The layout is the same in automatic and manual mode.

Alarm log entry *i* (for alarm bit *i*) is at offset 38 + 5·*i*: year, month, day, hour, minute
of the last time that bit became active. STcontrol prints it as `YY/MM/DD - HH:MM => message`.

### Alarm word (offsets 36–37, little-endian) [FW][APP]

| Bit | Mask | STcontrol message | Meaning | Cleared by `0x40` |
|-----|------|-------------------|---------|-------------------|
| 0 | 0x0001 | Erro no encoder do motor rotação | Rotation motor encoder error | yes |
| 1 | 0x0002 | Erro no encoder do motor atuador | Actuator motor encoder error | yes |
| 2 | 0x0004 | Erro no sentido de movimento de rotação | Rotation moving in the wrong direction | yes |
| 3 | 0x0008 | Erro no sentido de movimento do atuador | Actuator moving in the wrong direction | yes |
| 4 | 0x0010 | Fim de curso ESTE fora da posição | East limit switch out of position | yes, saved in flash |
| 5 | 0x0020 | Fim de curso OESTE fora da posição | West limit switch out of position | yes, saved in flash |
| 6 | 0x0040 | Fim de curso HORIZONTAL fora da posição | Horizontal limit switch out of position | yes, saved in flash |
| 7 | 0x0080 | Fim de curso VERTICAL fora da posição | Vertical limit switch out of position | yes, saved in flash |
| 8 | 0x0100 | Sem configuração Inicial | No initial configuration | no (live state) |
| 9 | 0x0200 | Detetado fim de curso ESTE | East limit switch active | no (live state) |
| 10 | 0x0400 | Detetado fim de curso OESTE | West limit switch active | no (live state) |
| 11 | 0x0800 | Detetado fim de curso HORIZONTAL | Horizontal limit switch active (normal when stowed flat) | no (live state) |
| 12 | 0x1000 | Detetado fim de curso VERTICAL | Vertical limit switch active | no (live state) |
| 13 | 0x2000 | Corrente do motor rotação excedido | Rotation motor overcurrent | yes |
| 14 | 0x4000 | Corrente do motor atuador excedido | Actuator motor overcurrent | yes |
| 15 | 0x8000 | Limite de vento excedido | Wind limit exceeded | yes |

Bits 4–7 survive a power cycle until cleared.

[LIVE] Captured 2026-11-15 13:11 UTC after a power cycle: mode auto, panel altitude 90.0, azimuth 53.7,
sun altitude 29.2, azimuth 194.2, wind 0, alarm word `0x0801`, both encoder counters 0, log entry for
bit 0 = `1A 0B 0F 0D 0A` (2026-11-15 13:10). Bytes received right after opening the port can contain
stray `00` bytes (one frame arrived as `Versio\x00n`); the checksum rejects those frames.

[LIVE] Earlier, the last frame logged by the Pi on 2026-11-15 11:05 had bytes 34–37 = `00 00 01 08`:
wind 0 km/h, alarm word `0x0801` = rotation encoder error + horizontal limit switch active,
with the panel at azimuth 53.7° while the sun was at 160.5°.

### Acknowledge, CMD `0x86` [FW]

`81 <src> 01 82 00 01 86 83 CHK`, for example `81 00 01 82 00 01 86 83 0E`. Sent after commands
that change settings or start a routine. It carries no data. `0x86` is the command code, not an alarm byte.

### Other replies [FW]

| CMD | Meaning |
|-----|---------|
| `0x51` | Reply to read-parameter `0x41` (see below) |
| `0x95`, `0x96` | Negative replies from the firmware-update commands |

## PC → tracker

DST `FF`, SRC `00` in all examples.

### Mode [FW][APP]

| CMD | Frame | Effect |
|-----|-------|--------|
| `0x10` | `81 FF 00 82 00 01 10 83 96` | Manual mode |
| `0x11` | `81 FF 00 82 00 01 11 83 97` | Automatic mode |

Each mode change erases and rewrites the configuration block in flash. Do not send these repeatedly.

### Manual movement [FW][APP]

Only acted on in manual mode. STcontrol sends one data byte `01`; the firmware ignores it.

| CMD | Frame | Effect |
|-----|-------|--------|
| `0x20` | `81 FF 00 82 00 02 20 01 83 A8` | Rotate east |
| `0x21` | `81 FF 00 82 00 02 21 01 83 A9` | Rotate west |
| `0x22` | `81 FF 00 82 00 02 22 01 83 AA` | Tilt up |
| `0x23` | `81 FF 00 82 00 02 23 01 83 AB` | Tilt down |
| `0x24` | `81 FF 00 82 00 02 24 01 83 AC` | Stop |

### Go to position [FW][APP]

| CMD | Frame | Effect |
|-----|-------|--------|
| `0x25` | `81 FF 00 82 00 01 25 83 AB` | Go to the stored maintenance position (default altitude 25°, azimuth 180°) |
| `0x26` | `81 FF 00 82 00 01 26 83 AC` | Go to horizontal position ("POSICAO HORIZONTAL") |
| `0x27` | `81 FF 00 82 00 01 27 83 AD` | Go to vertical position, altitude 25° ("POSICAO VERTICAL") |

### Commissioning (these change calibration) [FW][APP]

| CMD | LEN | Data | STcontrol name | Effect |
|-----|-----|------|----------------|--------|
| `0x30` | 8 | sec, min, hour, weekday, day, month, year (2 digits) | Actualizar | Set the clock (UTC). 16-byte frame. |
| `0x31` | 1 | – | ZERAR PAINEL | Start the zero/homing routine |
| `0x32` | 1 | – | Painel orientado ao sol | Confirm the panel is aimed at the sun (azimuth calibration) |
| `0x33` | 9 | latitude f32 LE, longitude f32 LE | Coordenadas GPS | Store location in flash |
| `0x34` | 3 | sunrise byte, sunset byte | CONFIRMAR (limites) | Store minimum sun altitude at sunrise and sunset, degrees (default 2, 2) |
| `0x35` | 1 | – | CONFIRMAR POSIÇÃO DE MANUTENÇÃO | Store the current position as the maintenance position |
| `0x36` | 1 | – | Limite vertical detetado | Store the current tilt as the vertical limit |
| `0x40` | 1 | – | APAGAR ALARMES | Clear alarms and the alarm log |

Clock example, 2026-02-14 10:30:00, Saturday: `81 FF 00 82 00 08 30 00 1E 0A 06 0E 02 1A 83 15`.

### Parameters [FW][APP]

| CMD | Data | Effect |
|-----|------|--------|
| `0x41` | `03` | Read wind settings. Reply `0x51`: `03`, hold time u16 LE, count, release threshold, trip threshold |
| `0x41` | `0A` | Read maximum wind record. Reply `0x51`: `0A`, wind u16 LE, year, month, day, hour, minute |
| `0x42` | `03`, hold u16 LE, count, release, trip | Write wind settings (LEN 7). Defaults: hold 10, count 1, release 30, trip 40 km/h |
| `0x42` | `0A`, wind u16 LE, 5 date bytes | Overwrite the maximum wind record (LEN 9) |

Read examples: `81 FF 00 82 00 02 41 03 83 CB`, `81 FF 00 82 00 02 41 0A 83 D2`.
STcontrol's "Enviar" sends `81 FF 00 82 00 07 42 03 0A 00 01 <release> <trip> 83 CHK`.

### Firmware update — never send [FW]

| CMD | Effect |
|-----|--------|
| `0xF0` (13 data bytes) | Enter update mode. Status broadcasts stop. |
| `0xF1` | Update data |
| `0xF2` | Jump to the flash-programming routine in RAM |

These are the bootloader path used by MicroLoader/TConfig, not diagnostics.

## Corrections to the earlier document

| Earlier claim | What the firmware and app show |
|---------------|-------------------------------|
| "Packet type" in byte 5 | Bytes 4–5 are the payload length |
| Status request `81 FF 00 82 00 08 30 83 BD` | No such command. This is a truncated set-clock frame; the tracker drops it. Status is broadcast unprompted. |
| Status response is 38 bytes | It is 132 bytes; 38 was a partial read |
| Alarm is one byte at offset 37 | Alarm is 16 bits at offsets 36–37. Offset 36 (encoder, direction and limit-position errors) was ignored. |
| Alarm bit `0x80` of byte 37 = encoder error | It is the wind limit. Encoder errors are bits 0–1 of byte 36. |
| Alarm bit `0x01` of byte 37 = vertical limit | It is "no initial configuration" |
| Byte 20 = "status flags", byte 21 unknown, bytes 14–15 "counters" | Bytes 20–21 and 14–15 are the two encoder pulse counters |
| Bytes 34–36 reserved | Bytes 34–35 are wind speed in km/h |
| Fields swap between auto and manual mode | The layout never changes |
| `0x31` = alarm query, reply contains alarm byte `0x86` | `0x31` starts ZERAR PAINEL (homing). `0x86` is the generic acknowledge. |
| `0x32`, `0x35`, `0x36` = unknown queries | Calibration commands (see above) |
| `0x34 00 00` = zero panel | Sets both sun-altitude limits to 0 |
| `0x09`/`0x32` = set date/time | Set clock is CMD `0x30` with LEN 8 |
| `0xF0`–`0xF2` = diagnostics | Firmware-update entry points |
| Alarm bytes ≥ `0xF0` are corrupt | No such rule exists; those readings came from parsing misaligned frames without checking the checksum |
| RAM `0x12CD–0x12D3` = RTC memory | It is the receive buffer payload |
