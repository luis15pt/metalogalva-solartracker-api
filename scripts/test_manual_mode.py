#!/usr/bin/env python3
"""
Test manual mode and movement commands - replicating Windows app behavior.

Key insight from capture analysis: Windows app sends ZERO status requests
during manual control. It just sends commands and trusts they work.

This script measures success by POSITION CHANGE, not status byte.
"""

import serial
import struct
import time
import argparse

# Command packets (verified identical to Windows app capture)
MANUAL_MODE = bytes.fromhex('81ff00820001108396')
AUTO_MODE = bytes.fromhex('81ff00820001118397')
MOVE_LEFT = bytes.fromhex('81ff00820002210183a9')
MOVE_RIGHT = bytes.fromhex('81ff00820002200183a8')
MOVE_UP = bytes.fromhex('81ff00820002220183aa')
MOVE_DOWN = bytes.fromhex('81ff00820002230183ab')
STOP = bytes.fromhex('81ff00820002240183ac')
STATUS_REQUEST = bytes.fromhex('81ff00820008308330')

# Response header
RESPONSE_HEADER = bytes([0x81, 0x00, 0x01, 0x82, 0x00, 0x7c, 0x50])


def send_command(ser, packet, description=""):
    """Send command with RS-485 RTS toggling (twice with 50ms gap)."""
    for _ in range(2):
        # RS-485: RTS high for transmit
        ser.rts = True
        time.sleep(0.002)
        ser.write(packet)
        ser.flush()
        # Wait for transmission (10 bits/byte at 9600 baud)
        time.sleep(len(packet) * 10 / 9600 + 0.01)
        # RS-485: RTS low for receive
        ser.rts = False
        time.sleep(0.05)
    print(f"  TX: {packet.hex()} ({description})")


def get_position(ser):
    """Get current panel position from tracker with RS-485 RTS toggling."""
    ser.reset_input_buffer()

    # RS-485: RTS high for transmit
    ser.rts = True
    time.sleep(0.002)
    ser.write(STATUS_REQUEST)
    ser.flush()
    time.sleep(len(STATUS_REQUEST) * 10 / 9600 + 0.01)
    # RS-485: RTS low for receive
    ser.rts = False

    time.sleep(0.8)
    data = ser.read(300)

    idx = data.find(RESPONSE_HEADER)
    if idx < 0 or idx + 35 > len(data):
        return None, None, None

    d = data[idx:]
    panel_v = struct.unpack('<f', d[16:20])[0]
    panel_h = struct.unpack('<f', d[22:26])[0]
    status_byte = d[20]

    return panel_h, panel_v, status_byte


def main():
    parser = argparse.ArgumentParser(description="Test manual mode movement")
    parser.add_argument("--port", default="/dev/ttyUSB1", help="Serial port")
    parser.add_argument("--direction", default="left",
                        choices=["left", "right", "up", "down"],
                        help="Movement direction to test")
    parser.add_argument("--duration", type=float, default=3.0,
                        help="Movement duration in seconds")
    args = parser.parse_args()

    direction_map = {
        "left": (MOVE_LEFT, "MOVE_LEFT"),
        "right": (MOVE_RIGHT, "MOVE_RIGHT"),
        "up": (MOVE_UP, "MOVE_UP"),
        "down": (MOVE_DOWN, "MOVE_DOWN"),
    }
    move_cmd, move_name = direction_map[args.direction]

    print(f"Connecting to {args.port}...")
    ser = serial.Serial(
        port=args.port,
        baudrate=9600,
        bytesize=8,
        parity='N',
        stopbits=1,
        timeout=2
    )
    time.sleep(1)

    try:
        # Get initial position
        h1, v1, status1 = get_position(ser)
        if h1 is None:
            print("ERROR: Could not get initial position")
            return
        print(f"Initial position: H={h1:.2f}° V={v1:.2f}° (status=0x{status1:02x})")

        print()
        print("Sending MANUAL_MODE (twice)...")
        send_command(ser, MANUAL_MODE, "MANUAL_MODE")
        time.sleep(0.5)

        print(f"Sending {move_name} (twice)...")
        send_command(ser, move_cmd, move_name)

        print(f"Waiting {args.duration} seconds for movement...")
        time.sleep(args.duration)

        print("Sending STOP (twice)...")
        send_command(ser, STOP, "STOP")
        time.sleep(0.5)

        # Get final position
        h2, v2, status2 = get_position(ser)
        if h2 is None:
            print("ERROR: Could not get final position")
            return
        print()
        print(f"Final position: H={h2:.2f}° V={v2:.2f}° (status=0x{status2:02x})")

        h_diff = h2 - h1
        v_diff = v2 - v1
        print(f"Position change: H={h_diff:+.2f}° V={v_diff:+.2f}°")

        print()
        if abs(h_diff) > 0.1 or abs(v_diff) > 0.1:
            print("*** SUCCESS: Panel moved! ***")
        else:
            print("*** NO MOVEMENT DETECTED ***")

        print()
        print("Returning to AUTO_MODE...")
        send_command(ser, AUTO_MODE, "AUTO_MODE")
        time.sleep(1)

        # Verify auto mode
        h3, v3, status3 = get_position(ser)
        if h3 is not None:
            print(f"Final status: 0x{status3:02x}")

        print("Done.")

    finally:
        ser.close()


if __name__ == "__main__":
    main()
