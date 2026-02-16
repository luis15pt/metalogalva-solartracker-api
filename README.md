# Solar Tracker API

A REST API and MQTT bridge for remote control of solar tracking systems, designed for Home Assistant integration.

This project replaces the need for a Windows laptop + USB-to-serial adapter by providing a Raspberry Pi-based solution that exposes the solar tracker control via HTTP API and MQTT.

## Features

- **REST API** - Full HTTP API for all tracker operations
- **MQTT Integration** - Native Home Assistant auto-discovery support
- **Web UI** - Built-in control panel accessible via browser
- **WebSocket** - Real-time status updates
- **Docker** - Easy deployment with Docker Compose

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

- Raspberry Pi (or any Linux device) with Docker installed
- USB-to-Serial adapter connected to the solar tracker
- Network access from Home Assistant

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/SolarTracker_API.git
   cd SolarTracker_API
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

4. **Access the Web UI:**
   Open `http://raspberry-pi-ip:8000` in your browser

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
| POST | `/tracker/alarms/query` | Query detailed alarm status |
| POST | `/tracker/wind` | Set max wind threshold |
| POST | `/tracker/gps` | Set GPS location (lat/lon) |
| POST | `/tracker/datetime` | Set tracker internal clock |
| POST | `/tracker/datetime/sync` | Sync clock with server UTC |
| POST | `/tracker/position/{1,2,3}` | Go to preset position |
| POST | `/tracker/home` | Go to HOME position |
| POST | `/tracker/stow` | Go to STOW position |
| POST | `/tracker/zero` | Zero/reset panel encoders |

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

## Protocol Status

The serial protocol has been reverse engineered from multiple sources:
- STcontrol V4.0.4.0.exe (radare2 disassembly)
- Direct COM port capture with Device Monitoring Studio (February 2026)
- HCS12 firmware disassembly (STS.2A_V2.31.abs.s19)

See [docs/protocol.md](docs/protocol.md) for full documentation.

### Implemented Commands

| Command | Status | Description |
|---------|--------|-------------|
| Movement (0x20-0x24) | ✅ Implemented | Up, Down, Left, Right, Stop |
| Preset Positions (0x25-0x27) | ✅ Implemented | Go to HOME/STOW positions (needs testing) |
| Manual Mode (0x10) | ✅ Implemented | Switch to manual control |
| Auto Mode (0x11) | ✅ Implemented | Switch to automatic tracking |
| Clear Alarms (0x40) | ✅ Implemented | Clears all active alarms |
| Request Status (0x30) | ✅ Implemented | Polls current tracker status |
| Alarm Query (0x31) | ✅ Implemented | Query alarm bitmask |
| Date/Time (0x32) | ✅ Implemented | Set tracker internal clock |
| GPS Location (0x33) | ✅ Implemented | Set lat/lon for sun calculation |
| Zero Panel (0x34) | ✅ Implemented | Reset panel position counters |

### Discovered but Untested Commands

| Command | Type | Notes |
|---------|------|-------|
| Query 0x32, 0x35, 0x36 | 0x01 | Unknown queries - need testing |
| Preset positions 0x25-0x27 | 0x02 | Found in firmware - HOME/STOW? |
| Extended 0xF0-0xF2 | 0x01 | Found in firmware - unknown |

### TODO

| Feature | Status | Notes |
|---------|--------|-------|
| Date/Time Sync | ✅ Implemented | Type 0x09 Cmd 0x32 (from firmware analysis) |
| Set Wind Threshold | 🔍 Investigating | Possibly Query 0x35 or 0x36 |
| Set East/West Limits | 🔍 Investigating | Need more captures |

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

## Project Structure

```
SolarTracker_API/
├── docker-compose.yml      # Docker Compose configuration
├── Dockerfile              # Docker build file
├── requirements.txt        # Python dependencies
├── src/
│   └── solartracker/
│       ├── main.py         # FastAPI application
│       ├── config.py       # Configuration settings
│       ├── models.py       # Pydantic models
│       ├── protocol.py     # Serial protocol definition
│       ├── serial_handler.py   # Serial communication
│       └── mqtt_handler.py     # MQTT bridge
├── web/
│   ├── static/
│   │   ├── style.css       # Web UI styles
│   │   └── app.js          # Web UI JavaScript
│   └── templates/
│       └── index.html      # Web UI template
├── scripts/
│   └── serial_sniffer.py   # Protocol capture tool
├── homeassistant/
│   ├── configuration.yaml  # HA config example
│   └── lovelace-card.yaml  # Dashboard card
├── mosquitto/
│   └── config/
│       └── mosquitto.conf  # MQTT broker config
└── docs/
    └── reverse-engineering.md  # Original app analysis
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
