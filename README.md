# Solar Tracker API

A REST API and MQTT bridge for remote control of Metalogalva solar tracking systems, designed for Home Assistant integration.

This project replaces the need for a Windows laptop + USB-to-serial adapter by providing a Raspberry Pi-based solution that exposes the solar tracker control via HTTP API and MQTT.

## Features

- **REST API** - Full HTTP API for all tracker operations
- **MQTT Integration** - Native Home Assistant auto-discovery support
- **Web UI** - Mobile-first control panel with scene visualization (animated sky, weather, sun/moon, panel), half-compass and altitude gauges, weather data from Open-Meteo API
- **WebSocket** - Real-time status updates
- **Docker** - Pre-built arm64 image from GHCR, CI/CD via GitHub Actions
- **Persistent Logging** - State change logging with rotating file handler (5x20MB)

## Architecture

```
┌─────────────┐     ┌───────────────────────────────────────┐     ┌──────────────┐
│   Solar     │     │         Raspberry Pi (Docker)         │     │    Home      │
│   Tracker   │────►│  ┌────────────────────────────────┐   │────►│   Assistant  │
│  (RS232)    │     │  │   Solar Tracker API Service    │   │     │              │
└─────────────┘     │  │  ┌────────┐ ┌──────┐ ┌──────┐  │   │     │  - MQTT      │
     USB            │  │  │Serial  │►│ REST │►│ MQTT │  │   │     │  - Lovelace  │
                    │  │  │Handler │ │ API  │ │Bridge│  │   │     │    Dashboard │
                    │  │  └────────┘ └──────┘ └──────┘  │   │     └──────────────┘
                    │  └────────────────────────────────┘   │
                    │  ┌────────────────────────────────┐   │
                    │  │         Mosquitto MQTT         │   │
                    │  └────────────────────────────────┘   │
                    └───────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Raspberry Pi (or any Linux arm64 device) with Docker installed
- USB-to-Serial adapter connected to the solar tracker
- Network access from Home Assistant

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/luis15pt/metalogalva-solartracker-api.git
   cd metalogalva-solartracker-api
   ```

2. **Configure environment (optional):**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Start with Docker Compose:**
   ```bash
   docker-compose up -d
   ```

   This pulls the pre-built arm64 image from `ghcr.io/luis15pt/metalogalva-solartracker-api:latest`. No local build required.

4. **Access the Web UI:**
   Open `http://raspberry-pi-ip:8000` in your browser

### Docker / CI/CD

The project uses GitHub Actions (`.github/workflows/docker-build.yml`) to automatically build and push an arm64 Docker image to GHCR on every push to `main`. The `docker-compose.yml` pulls this pre-built image instead of building locally, which avoids slow arm64 builds on the Pi.

A `./data` volume is mounted at `/app/data` inside the container for persistent storage (state change logs, observed position limits).

### Configuration

Environment variables (can be set in `.env` or `docker-compose.yml`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SERIAL_PORT` | `/dev/ttyUSB0` | Serial port device |
| `SERIAL_BAUDRATE` | `9600` | Baud rate |
| `MQTT_BROKER` | `mosquitto` | MQTT broker host |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_TOPIC_PREFIX` | `solartracker` | MQTT topic prefix |
| `LOG_LEVEL` | `INFO` | Logging level |

## Web UI

The built-in web interface is a mobile-first single-page application featuring:

- **Scene visualization** - Animated sky gradient with sun/moon position, weather effects (rain, clouds), and a solar panel that reflects the tracker's real orientation
- **Half-compass gauge** - Shows panel horizontal (azimuth) angle
- **Altitude gauge** - Shows panel vertical (tilt) angle
- **Weather data** - Pulled from Open-Meteo API: sunrise/sunset times, temperature, wind speed, and weather conditions with animated overlays
- **D-pad controls** - Directional movement buttons with a HOME center button
- **Mode toggle** - Switch between automatic and manual mode
- **Collapsible sections** - Alarms, alarm history, connection info, and settings are organized into expandable panels

## API Endpoints

### Connection
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/serial/ports` | List available serial ports |
| GET | `/serial/status` | Get connection status |
| POST | `/serial/connect` | Connect to serial port |
| POST | `/serial/disconnect` | Disconnect |

### Tracker Control
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/tracker/status` | Get full tracker status |
| POST | `/tracker/move` | Move tracker (with direction & duration) |
| POST | `/tracker/move/{direction}/start` | Start continuous movement |
| POST | `/tracker/move/{direction}/stop` | Stop movement |
| POST | `/tracker/stop` | Emergency stop |
| POST | `/tracker/mode/{mode}` | Set mode (manual/automatic) |
| POST | `/tracker/alarms/clear` | Clear all alarms |
| POST | `/tracker/alarms/clear-history` | Clear alarm history log |
| POST | `/tracker/alarms/query` | Query detailed alarm status |
| POST | `/tracker/wind` | Set max wind threshold |
| POST | `/tracker/gps` | Set GPS location (lat/lon) |
| POST | `/tracker/datetime` | Set tracker internal clock |
| POST | `/tracker/datetime/sync` | Sync clock with server UTC |
| POST | `/tracker/position/{1,2,3}` | Go to preset position |
| POST | `/tracker/home` | Go to HOME position |
| POST | `/tracker/stow` | Go to STOW position |
| POST | `/tracker/zero` | Zero/reset panel encoders |
| POST | `/tracker/limits/reset` | Reset observed position limits |
| GET | `/tracker/limits` | Get observed position limits |

### WebSocket
| Endpoint | Description |
|----------|-------------|
| `/ws` | Real-time status updates |

## MQTT Topics

### State Topics (published by API)
| Topic | Description |
|-------|-------------|
| `solartracker/availability` | Online/offline status |
| `solartracker/state/mode` | Current mode |
| `solartracker/state/connected` | Serial connection status |
| `solartracker/state/position/horizontal` | Horizontal angle |
| `solartracker/state/position/vertical` | Vertical angle |
| `solartracker/state/wind_speed` | Current wind speed |
| `solartracker/state/alarms` | Active alarms (JSON array) |

### Command Topics (subscribed by API)
| Topic | Payload | Description |
|-------|---------|-------------|
| `solartracker/command/move` | `{"direction": "up", "start": true}` | Movement control |
| `solartracker/command/mode` | `manual` or `automatic` | Set mode |
| `solartracker/command/clear_alarms` | any | Clear alarms |
| `solartracker/command/set_wind` | `0-99` | Set wind threshold |
| `solartracker/command/go_home` | any | Go to HOME position |
| `solartracker/command/go_stow` | any | Go to STOW (safe) position |
| `solartracker/command/set_gps` | `{"latitude": 40.54, "longitude": -8.70}` | Set GPS location |
| `solartracker/command/sync_datetime` | any | Sync tracker clock to server UTC |
| `solartracker/command/zero_panel` | any | Reset panel position encoders |

## Home Assistant Integration

The API publishes MQTT auto-discovery messages, so entities will automatically appear in Home Assistant.

### Manual Configuration

See [`homeassistant/configuration.yaml`](homeassistant/configuration.yaml) for example configuration.

### Lovelace Dashboard

See [`homeassistant/lovelace-card.yaml`](homeassistant/lovelace-card.yaml) for a ready-to-use dashboard card.

## Logging

State changes (alarm triggers, mode transitions, status flag changes, vertical position changes) are logged to a persistent rotating file at `/app/data/solartracker.log`. The log uses 5 rotating files of 20MB each (100MB max). Only state transitions are logged, not every poll cycle, keeping the log focused on diagnostic events.

## Protocol

The serial protocol has been reverse engineered from multiple sources:
- STcontrol V4.0.4.0.exe (radare2 disassembly)
- Direct COM port capture with Device Monitoring Studio (February 2026)
- HCS12 firmware disassembly (STS.2A_V2.31.abs.s19)

See [docs/protocol.md](docs/protocol.md) for full documentation.

### Key Protocol Details

Response packet structure (38+ bytes) with notable offsets:

| Offset | Description |
|--------|-------------|
| 7 | Mode byte: `0x00` = AUTO, `0x01` = MANUAL (inverted from what STcontrol implied) |
| 16-19 | Panel vertical/tilt (float32 LE) |
| 22-25 | Panel horizontal/azimuth (float32 LE) |
| 26-29 | Sun altitude (float32 LE) |
| 30-33 | Sun azimuth (float32 LE) |
| 37 | Alarm bitmask (corrected from offset 36) |

### Protocol Fixes Applied

- **Alarm byte offset**: Corrected to byte 37 (was incorrectly 36)
- **Mode detection**: `0x00` = AUTO, `0x01` = MANUAL (was inverted)
- **Corrupt packet filtering**: Alarm bytes >= `0xF0` are treated as garbage and ignored
- **Alarm bit 3**: Correctly mapped to `tilt_limit_flat` (panel in stow position)

### Alarm Bitmask (byte 37)

| Bit | Alarm |
|-----|-------|
| 0 | Vertical limit |
| 1 | Unknown |
| 2 | West limit |
| 3 | Tilt limit / panel flat (stow) |
| 4 | Actuator motor current |
| 5 | Rotation motor current |
| 6 | Unknown |
| 7 | Encoder error |

### Implemented Commands

| Command | Status | Description |
|---------|--------|-------------|
| Movement (0x20-0x24) | Implemented | Up, Down, Left, Right, Stop |
| Preset Positions (0x25-0x27) | Implemented | Go to HOME/STOW positions (needs testing) |
| Manual Mode (0x10) | Implemented | Switch to manual control |
| Auto Mode (0x11) | Implemented | Switch to automatic tracking |
| Clear Alarms (0x40) | Implemented | Clears all active alarms |
| Request Status (0x30) | Implemented | Polls current tracker status |
| Alarm Query (0x31) | Implemented | Query alarm bitmask |
| Date/Time (0x32) | Implemented | Set tracker internal clock |
| GPS Location (0x33) | Implemented | Set lat/lon for sun calculation |
| Zero Panel (0x34) | Implemented | Reset panel position counters |

### Discovered but Untested Commands

| Command | Type | Notes |
|---------|------|-------|
| Query 0x32, 0x35, 0x36 | 0x01 | Unknown queries - need testing |
| Preset positions 0x25-0x27 | 0x02 | Found in firmware - HOME/STOW? |
| Extended 0xF0-0xF2 | 0x01 | Found in firmware - unknown |

### Protocol Capture Tool

For debugging or capturing new commands:

```bash
# List available ports
python scripts/serial_sniffer.py --list

# Simple logging mode
python scripts/serial_sniffer.py --port /dev/ttyUSB0 --log capture.txt

# MITM mode (bridge between app and tracker)
python scripts/serial_sniffer.py --port-a COM10 --port-b COM11 --log capture.txt
```

## Deployment Notes

### WiFi Watchdog (Raspberry Pi)

If deploying on a Raspberry Pi over WiFi, a custom `wifi-watchdog.service` systemd unit is recommended to automatically reconnect if the WiFi link drops. This is not part of the application itself but is useful for headless Pi deployments where the tracker is in a remote location.

### TODO

| Feature | Status | Notes |
|---------|--------|-------|
| Date/Time Sync | Implemented | Type 0x09 Cmd 0x32 (from firmware analysis) |
| Set Wind Threshold | Investigating | Possibly Query 0x35 or 0x36 |
| Set East/West Limits | Investigating | Need more captures |

## Project Structure

```
metalogalva-solartracker-api/
├── .github/
│   └── workflows/
│       └── docker-build.yml  # CI/CD: build arm64 image, push to GHCR
├── docker-compose.yml      # Docker Compose (pulls pre-built GHCR image)
├── Dockerfile              # Docker build file
├── requirements.txt        # Python dependencies
├── src/
│   └── solartracker/
│       ├── main.py         # FastAPI app, state change logging, alarm history
│       ├── config.py       # Configuration settings
│       ├── models.py       # Pydantic models
│       ├── protocol.py     # Serial protocol (alarm/mode fixes, corrupt filtering)
│       ├── serial_handler.py   # Serial communication
│       └── mqtt_handler.py     # MQTT bridge
├── web/
│   ├── static/
│   │   ├── style.css       # Web UI styles
│   │   └── app.js          # Scene visualization, weather, gauges
│   └── templates/
│       └── index.html      # Mobile-first Web UI
├── data/                   # Persistent storage (mounted volume)
│   └── solartracker.log    # Rotating state change log
├── scripts/
│   └── serial_sniffer.py   # Protocol capture tool
├── homeassistant/
│   ├── configuration.yaml  # HA config example
│   └── lovelace-card.yaml  # Dashboard card
├── mosquitto/
│   └── config/
│       └── mosquitto.conf  # MQTT broker config
└── docs/
    └── protocol.md         # Full protocol documentation
```

## Development

### Running Locally (without Docker)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run the application
uvicorn src.solartracker.main:app --reload --host 0.0.0.0 --port 8000
```

### Running Tests

```bash
pytest
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Capture and document protocol commands
4. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file.

## Acknowledgments

- Original application: STcontrol V4.0.4.0
- Reverse engineering documentation: [docs/reverse-engineering.md](docs/reverse-engineering.md)
