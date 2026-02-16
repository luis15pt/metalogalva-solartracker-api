# Solar Tracker API - Testing Status

Last Updated: 2026-02-01 01:30 UTC

## CRITICAL: RS-485 RTS Toggling Required

**The tracker uses RS-485 half-duplex protocol.** Commands MUST use RTS toggling:
- Set RTS HIGH before transmitting
- Wait for transmission to complete
- Set RTS LOW to receive response

Without RTS toggling, commands are transmitted but the tracker ignores them.

## Protocol Commands

### Confirmed Working
- [x] **MANUAL_MODE** (`81ff00820001108396`) - Sets manual mode, enables movement
- [x] **MOVE_RIGHT** (`81ff00820002200183a8`) - Confirmed working (moved 6.14° in test)
- [x] **MOVE_LEFT** (`81ff00820002210183a9`) - Confirmed working (moved 6.14° in test)
- [x] **MOVE_UP** (`81ff00820002220183aa`) - Confirmed working
- [x] **MOVE_DOWN** (`81ff00820002230183ab`) - Confirmed working (moved 5.88° in test)
- [x] **STOP** (`81ff00820002240183ac`) - Stops movement
- [x] **STATUS_REQUEST** (`81ff00820008308330`) - Working (used in monitoring)
- [x] **Status Response Parsing**

### Needs Investigation
- [ ] **AUTO_MODE** (`81ff00820001118397`) - Command sent but panel doesn't return to stow at night
  - [x] Date/Time - Correctly parsed from response
  - [x] Firmware Version - "Version 2.31" extracted
  - [x] Panel Position (Horizontal/Azimuth) - Float values correct
  - [x] Panel Position (Vertical/Tilt) - Float values correct
  - [x] Sun Position (Azimuth) - Float values correct
  - [x] Sun Position (Altitude) - Float values correct

### Needs Testing
- [ ] **MOVE_UP** (`81ff00820002220183aa`) - May be at upper limit (V=80.90°)
- [ ] **MOVE_DOWN** (`81ff00820002230183ab`) - Needs testing when not at limit
- [ ] **CLEAR_ALARMS** (`81ff008200014083c6`) - Checksum corrected, needs testing

### Not Yet Implemented/Tested
- [x] **Alarm Parsing** - Byte 36 confirmed as alarm byte (was incorrectly at 34, now working)
- [ ] **Status Byte Decoding** - Byte 20 observed values: 0x93, 0xCF (meaning TBD)
- [ ] **Set Wind Threshold** - Not yet reverse engineered
- [ ] **Set Limits** - Not yet reverse engineered

## API Endpoints

### Confirmed Working
- [x] `GET /health` - Health check
- [x] `GET /tracker/status` - Returns parsed tracker data
- [x] `POST /tracker/mode/automatic` - Sets auto mode, persists correctly
- [x] `WebSocket /ws` - Real-time updates

### Needs Testing
- [ ] `POST /tracker/mode/manual` - Set manual mode
- [ ] `POST /tracker/move` - Movement commands
- [ ] `POST /tracker/move/{direction}/start` - Start continuous movement
- [ ] `POST /tracker/move/{direction}/stop` - Stop movement
- [ ] `POST /tracker/stop` - Stop all movement
- [ ] `POST /tracker/alarms/clear` - Clear alarms
- [ ] `POST /serial/connect` - Manual serial connection
- [ ] `POST /serial/disconnect` - Disconnect serial

## Known Issues / Notes

### Status Byte (Byte 20)
- Observed values: 0x93, 0xCF
- Meaning not fully decoded
- Cannot reliably determine auto/manual mode from this byte yet

### Mode Tracking
- Mode is tracked based on API commands sent, NOT from response parsing
- This is because the status byte meaning is unknown
- At night, tracker stows regardless of mode, so position-based detection doesn't work

### Alarms
- Alarm byte is at offset 36 in response (was incorrectly 34)
- Confirmed working: stowed panel shows tilt_limit_flat alarm (0x02)
- This is normal at night - "Detectado fim do curso Horizontal" means panel is flat/horizontal (stow position)
- The Portuguese "horizontal" refers to the panel SURFACE being horizontal, not the rotation axis
- Alarm bits: 0=vertical_limit, 1=tilt_limit_flat, 2=west?, 3=wind, 4=actuator, 5=rotation, 6=unknown, 7=encoder

## Test Log

### 2026-02-01
- **BREAKTHROUGH: Discovered RS-485 RTS toggling requirement**
  - Packets were correct but tracker ignored them without RTS control
  - Solution: Toggle RTS HIGH for transmit, LOW for receive
  - Same USB adapter worked on Windows because Windows FTDI driver handles RS-485 automatically
- Confirmed MANUAL_MODE + movement commands work with RTS toggling
- Panel successfully moved +3.75° horizontally with MOVE_RIGHT command
- Updated `serial_handler.py` to include RTS toggling in `send()` method
- Updated test scripts to use RTS toggling

### 2026-01-31
- Captured packets from STcontrol Windows app via serial sniffer
- Verified all command packets match our protocol implementation
- Confirmed AUTO_MODE works - tracker moved 26° horizontally, 24° vertically to track sun
- Response parsing confirmed working for position, time, firmware version
- Fixed: Mode was being overwritten by faulty position-based detection
- Fixed: Web UI colors now clearly show connected (green) vs disconnected (red)
- Fixed: Mode buttons show "(ACTIVE)" suffix and green color for active mode
