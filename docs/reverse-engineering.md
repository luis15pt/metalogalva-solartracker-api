# STcontrol V4.0.4.0 - Reverse Engineering Documentation

This document contains the reverse engineering analysis of the original Windows application.

## Overview

**Application Name:** SOLAR TRACK CONTROLER
**Version:** 4.0.4.0
**File:** STcontrol V4.0.4.0.exe
**Size:** 745,984 bytes (~729 KB)
**Date:** July 20, 2021
**Type:** PE32 executable (GUI) Intel 80386, for MS Windows
**Framework:** Delphi/Object Pascal
**Language:** Portuguese

## Serial Communication

### Library
- **CPort** - Popular Delphi serial communication component

### Port Configuration

| Parameter | Options |
|-----------|---------|
| **Ports** | COM1, COM2 |
| **Baud Rates** | 1200, 2400, 4800, 9600, 14400, 19200, 38400, 56000, 57600, 115200, 128000, 256000 |
| **Data Bits** | Configurable |
| **Stop Bits** | Configurable |
| **Parity** | None, Even, Mark, Space |

### Status Indicators
- **ComLed1** - TX (Transmit) indicator
- **ComLed2** - RX (Receive) indicator
- **ComLed3** - Connection status indicator

## Application Features

### Operating Modes

| Mode | Portuguese | Description |
|------|------------|-------------|
| **Manual** | CONTROLO MANUAL / Modo Manual | Direct user control of tracker position |
| **Automatic** | CONTROLO AUTOM / Modo Autom | Automated solar tracking |

### Movement Controls

The application uses SpeedButtons for directional control:

| Control | Event Handlers | Description |
|---------|----------------|-------------|
| **Up** | `setaMovCimaMouseDown`, `setaMovCimaMouseUp` | Move tracker upward |
| **Down** | `setaMovBaixoMouseDown`, `setaMovBaixoMouseUp` | Move tracker downward |
| **Left** | `setaMovEsqMouseDown`, `setaMovEsqMouseUp` | Move tracker left (West) |
| **Right** | `setaMovDirMouseDown`, `setaMovDirMouseUp` | Move tracker right (East) |

### Position Controls

| Button | Caption | Function |
|--------|---------|----------|
| Button3 | POSICAO HORIZONTAL | Set horizontal position |
| Button5 | POSICAO VERTICAL | Set vertical position |
| Button12 | CONFIRMAR POSICAO | Confirm position |

### Limit Configuration

| Control | Description |
|---------|-------------|
| `MaskLimitNascente` | East limit setting (sunrise direction) |
| `MaskLimitPoente` | West limit setting (sunset direction) |
| `ConfirmarLimites` | Confirm limits button |
| `LimiteVerticalDetetado` | Vertical limit detection |

**Edit Mask:** `99;1;_` (2-digit numeric input)

### Solar Position Parameters

| Label | Description |
|-------|-------------|
| VALOR MINIMO ALTITUDE NASCER-DO-SOL | Minimum altitude value for sunrise |
| VALOR MINIMO ALTITUDE POR-DO-SOL | Minimum altitude value for sunset |

## Alarms System

### Alarm Window
- **Form:** Form3 (Alarmes/Parametros)
- **Clear Alarms:** Button15 - "Apagar Alarmes"
- **Alarm Display:** Memo component with vertical scrollbar

### Alarm Messages

| Portuguese | English Translation |
|------------|---------------------|
| Corrente do motor atuador excedido | Actuator motor current exceeded |
| Corrente do motor rota... | Rotation motor current issue |
| Erro no encoder do motor atuador | Actuator motor encoder error |
| Erro no encoder do motor rota... | Rotation motor encoder error |
| Limite de vento excedido | Wind limit exceeded |
| Alarme de Velocidade de vento excessivo | Excessive wind speed alarm |

## Parameters Panel

### Time Synchronization
| Control | Format | Description |
|---------|--------|-------------|
| `MaskEditDateUTC` | `0000/00/00` | UTC/GMT date display |
| `MaskEditTimeUTC` | `00/00/00` | UTC/GMT time display |
| Button1 | Actualizar | Update/refresh time |

### Wind Configuration
| Control | Description |
|---------|-------------|
| `MaskEditMaxWind` | Maximum wind speed threshold (2-digit, mask: `00`) |
| Button2 | Pedir (Request) - Request current value |
| Button3 | Enviar (Send) - Send new value |

## Configuration Wizard

The application includes a 6-step configuration wizard:

| Step | Description |
|------|-------------|
| 5/6 | LIMITES (Limits configuration) |
| 6/6 | Configurar Posicao de Manutencao (Configure maintenance position) |

### Navigation
- `MenuEsquerda` - Navigate left in menu
- `MenuDireita` - Navigate right in menu

## GUI Structure

### Main Forms

| Form | Class | Description |
|------|-------|-------------|
| Main | TForm | Main application window |
| Form3 | TForm3 | Alarms/Parameters window |
| ComSetupFrm | TComSetupFrm | Serial port configuration dialog |

### Main Panels

| Panel | Contents |
|-------|----------|
| PanelMenu4 | Movement SpeedButtons (1-4) |
| PanelMenu5 | Alarms section |
| PanelMenu316 | Step-by-step configuration |
| PortConfiguration | Serial port settings |

## Button Event Handlers

### Main Controls
| Handler | Description |
|---------|-------------|
| `Button1Click` | Update/Refresh |
| `Button2Click` | Request data |
| `Button3Click` | Send data / Horizontal position |
| `Button4Click` | Open COM port |
| `Button5Click` | Close COM port / Vertical position |
| `Button12Click` | Confirm position |
| `Button15Click` | Clear alarms |
| `ConfirmarLimitesClick` | Confirm limits |

### Movement Controls
| Handler | Description |
|---------|-------------|
| `SpeedButton1MouseDown/Up` | Direction 1 control |
| `SpeedButton2MouseDown/Up` | Direction 2 control |
| `SpeedButton3MouseDown/Up` | Direction 3 control |
| `SpeedButton4MouseDown/Up` | Direction 4 control |

## Timer

| Timer | Interval | Handler | Purpose |
|-------|----------|---------|---------|
| Timer1 | Configurable | `Timer1Timer` | Periodic updates (likely for auto-tracking) |

## Technical Notes

### Delphi Components Used
- TButton, TBitBtn, TSpeedButton - Button controls
- TPanel - Container panels
- TLabel - Text labels
- TComboBox - Dropdown selections
- TMaskEdit - Formatted input fields
- TMemo - Multi-line text display
- TTimer - Periodic timer
- TComLed - Serial port status LEDs (CPort component)
- TGroupBox - Grouped controls

### String Encoding
- Primary: ANSI/ASCII
- Font: MS Sans Serif, Arial

---

## TODO: Protocol Analysis

Further reverse engineering needed to document:
- [ ] Serial command format/structure
- [ ] Command bytes for each operation
- [ ] Response message parsing
- [ ] Checksum/CRC calculation (if any)
- [ ] Timing requirements between commands

---

*Document generated through static analysis of STcontrol V4.0.4.0.exe*
