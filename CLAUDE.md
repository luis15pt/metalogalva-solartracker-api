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

- `src/solartracker/main.py` — FastAPI app, WebSocket, state change logging, serial data parsing
- `src/solartracker/protocol.py` — Serial protocol: packet building, response parsing, alarm/mode decoding
- `src/solartracker/serial_handler.py` — RS-485 serial communication with RTS toggling
- `src/solartracker/mqtt_handler.py` — MQTT publishing and HA auto-discovery
- `src/solartracker/inverter.py` — SMA inverter data from SBFspot SQLite DB (read-only)
- `src/solartracker/config.py` — Environment variable configuration
- `src/solartracker/models.py` — Pydantic models
- `web/templates/index.html` — Single page HTML with SVG scene visualization
- `web/static/app.js` — Frontend logic: gauges, scene animation, weather, WebSocket
- `web/static/style.css` — Mobile-first dark theme
- `docs/protocol.md` — Full serial protocol documentation

## Protocol Notes

- RS-485 half-duplex, 9600 baud, RTS toggling for TX/RX
- Packets: header `81 FF 00 82 00` + type + command + `83` + checksum
- Status response: 38 bytes (or 135 with firmware version)
- Alarm byte at **offset 37** (not 36)
- Mode byte 7: **0x00 = AUTO**, 0x01 = MANUAL (inverted from what you'd expect)
- Panel vertical: **90 = flat/stowed**, 0 = vertical — angle from vertical, not horizontal
- Status flags byte 20: changes rapidly during movement, motor/encoder related
- Alarm bytes >= 0xF0 are corrupt packets, ignore them

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

- `SERIAL_PORT` — Serial device (default: `/dev/ttyUSB0`)
- `SERIAL_BAUDRATE` — Baud rate (default: `9600`)
- `MQTT_BROKER` — MQTT host (default: `mosquitto`)
- `MQTT_PORT` — MQTT port (default: `1883`)
- `MQTT_TOPIC_PREFIX` — Topic prefix (default: `solartracker`)
- `SBFSPOT_DB` — Path to SBFspot SQLite DB (default: `/data/SBFspot.db`)
- `LOG_LEVEL` — Python log level (default: `INFO`)

## Common Issues

- **WebSocket disconnect kills serial**: Fixed — `broadcast_status()` catches `ValueError` on list removal race condition, `_read_loop` catches all exceptions to stay alive
- **False alarms (all bits set)**: Corrupt packets with alarm byte >= 0xF0 are filtered out
- **Tilt limit alarm at night**: Expected — panel is stowed flat, alarm is suppressed in the UI when sun is below horizon
- **WiFi drops on Pi Zero 2W**: WiFi watchdog service restarts wlan0/wpa_supplicant before rebooting. WPA3-only APs cause issues — use SAE-mixed mode
