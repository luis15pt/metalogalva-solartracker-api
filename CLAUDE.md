# CLAUDE.md

## Project Overview

Solar Tracker API — a REST API, MQTT bridge, and web UI for controlling a Metalogalva solar tracking system. Replaces the original Windows STcontrol application with a Raspberry Pi-based solution.

The system communicates with the tracker via RS-485 serial (FTDI USB adapter) and reads SMA inverter data from an SBFspot SQLite database.

## Architecture

- **Backend**: Python FastAPI app (`src/solartracker/`)
- **Frontend**: Vanilla JS/CSS/SVG single-page app (`web/`)
- **MQTT**: Mosquitto broker with HA auto-discovery, bridged to external HA broker
- **Deployment**: Docker on Raspberry Pi Zero 2W, arm64 images built by GitHub Actions and pushed to GHCR

## Key Files

- `src/solartracker/main.py` — FastAPI app, WebSocket, state change logging, link watchdog
- `src/solartracker/protocol.py` — Serial protocol: frame builder, validating decoder, status and alarm decoding
- `src/solartracker/serial_handler.py` — RS-485 serial communication with RTS toggling
- `src/solartracker/goto.py` — Go-to-angle controller: jogs the motors and stops on the status feedback
- `src/solartracker/mqtt_handler.py` — MQTT publishing and HA auto-discovery
- `src/solartracker/inverter.py` — SMA inverter data from SBFspot SQLite DB (read-only)
- `src/solartracker/config.py` — Environment variable configuration
- `src/solartracker/models.py` — Pydantic models
- `web/templates/index.html` — Single page HTML with SVG scene visualization
- `web/static/app.js` — Frontend logic: gauges, scene animation, weather, WebSocket
- `web/static/style.css` — Mobile-first dark theme
- `docs/protocol.md` — Full serial protocol documentation

## Protocol Notes

Full reference: `docs/protocol.md` (re-derived Nov 2026 from the firmware and STcontrol; it supersedes older notes).

- 9600 8N1, RTS toggled around transmit
- Frame: `81 DST SRC 82 LEN_HI LEN_LO CMD DATA 83 CHK` — LEN counts CMD+DATA, CHK is the sum of all preceding bytes
- The tracker **broadcasts** a 132-byte status frame (CMD `0x50`) once per second. There is no status request; never poll
- Alarms are a **16-bit word at offsets 36–37**. Bits 9–12 are limit switches (normal states), bit 15 is wind, bits 0–1 are encoder errors
- Mode byte 7: **0x00 = AUTO**, 0x01 = MANUAL. `0x10` sets manual, `0x11` sets auto; each switch rewrites the tracker's flash
- Panel altitude: **90 = flat**, lower = more upright. Wind is km/h at offsets 34–35. The tracker clock is UTC
- `0x31` is ZERAR PAINEL (homing, the tracker moves). `0x30`–`0x36` change calibration
- **Never send `0xF0`–`0xF2`**: they are the firmware-update path. `protocol.build_frame` refuses them
- Always decode through `protocol.FrameDecoder` (checksum-validated); do not parse raw byte offsets from the serial stream

## Development

```bash
# Run locally
pip install -r requirements.txt
uvicorn src.solartracker.main:app --reload --host 0.0.0.0 --port 8000

# Build Docker image
docker build -t solartracker-api .

# Deploy on Pi (pulls from GHCR)
docker compose up -d
```

## Docker Volumes

- `./data:/app/data` — Persistent logs and observed limits
- `/home/luis/smadata/SBFspot.db:/data/SBFspot.db:ro` — SBFspot inverter database (read-only)

## Environment Variables

- `SERIAL_PORT` — Serial device (default: `/dev/ttyUSB0`; compose maps the adapter's `/dev/serial/by-id/...` path to `/dev/tracker`)
- `SERIAL_BAUDRATE` — Baud rate (default: `9600`)
- `MQTT_BROKER` — MQTT host (default: `mosquitto`)
- `MQTT_PORT` — MQTT port (default: `1883`)
- `MQTT_TOPIC_PREFIX` — Topic prefix (default: `solartracker`)
- `SBFSPOT_DB` — Path to SBFspot SQLite DB (default: `/data/SBFspot.db`)
- `LOG_LEVEL` — Python log level (default: `INFO`)
- `DATA_DIR` — Logs and persisted state (default: `/app/data`)

## Serial Port Access

The container runs as non-root (`appuser`). To access `/dev/ttyUSB0`, the container needs the `dialout` group. The `group_add` in docker-compose must match the host's dialout GID:
```bash
stat -c '%g' /dev/ttyUSB0  # Check the GID on your system
```
Common values: `20` (Raspberry Pi OS), `46` (some Debian/Ubuntu). Update `group_add` in docker-compose.yml accordingly.

## Common Issues

- **Adapter re-plugged / re-enumerated**: the read loop drops the port on I/O error and the housekeeping loop reconnects every 10 s; compose uses the by-id path so the device name stays stable
- **"Tracker" badge grey / stale banner**: serial is open but no status frames are arriving — check the cable and tracker power
- **Flat limit shown at night**: expected — the panel is stowed flat on its horizontal limit switch; it is shown as a chip, not an alarm
- **WiFi drops on Pi Zero 2W**: WiFi watchdog service restarts wlan0/wpa_supplicant before rebooting. WPA3-only APs cause issues — use SAE-mixed mode
