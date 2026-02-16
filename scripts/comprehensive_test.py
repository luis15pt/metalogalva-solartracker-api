#!/usr/bin/env python3
"""
Comprehensive test of all Solar Tracker API functions.
Run this directly on the serial port (stop Docker first).
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from solartracker.protocol import SolarTrackerProtocol, MovementCommand, ModeCommand
import serial

HEADER = bytes([0x81, 0x00, 0x01, 0x82, 0x00, 0x7c, 0x50])


class TrackerTester:
    def __init__(self, port="/dev/ttyUSB0", baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.ser = None

    def connect(self):
        """Connect to serial port."""
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=2
        )
        time.sleep(1)  # Let connection settle
        self.ser.reset_input_buffer()
        print(f"Connected to {self.port} at {self.baudrate} baud")
        return True

    def disconnect(self):
        """Disconnect from serial port."""
        if self.ser:
            self.ser.close()
            self.ser = None

    def send_command(self, packet, description=""):
        """Send a command packet with RS-485 RTS toggling (twice, like Windows app)."""
        self.ser.reset_input_buffer()
        for _ in range(2):
            # RS-485: RTS high for transmit
            self.ser.rts = True
            time.sleep(0.002)
            self.ser.write(packet)
            self.ser.flush()
            # Wait for transmission (10 bits/byte at 9600 baud)
            time.sleep(len(packet) * 10 / 9600 + 0.01)
            # RS-485: RTS low for receive
            self.ser.rts = False
            time.sleep(0.05)
        print(f"  TX: {packet.hex()} ({description})")

    def get_status(self):
        """Get and parse status from tracker with RS-485 RTS toggling."""
        self.ser.reset_input_buffer()
        packet = SolarTrackerProtocol.build_status_request()
        # RS-485: RTS high for transmit
        self.ser.rts = True
        time.sleep(0.002)
        self.ser.write(packet)
        self.ser.flush()
        time.sleep(len(packet) * 10 / 9600 + 0.01)
        # RS-485: RTS low for receive
        self.ser.rts = False
        time.sleep(0.8)
        data = self.ser.read(300)

        idx = data.find(HEADER)
        if idx < 0 or idx + 35 > len(data):
            return None

        import struct

        # Extract data relative to header
        d = data[idx:]

        status = {
            'status_byte': d[20],
            'is_auto': bool(d[20] & 0x01),
            'panel_v': struct.unpack('<f', d[16:20])[0],
            'panel_h': struct.unpack('<f', d[22:26])[0],
            'sun_alt': struct.unpack('<f', d[26:30])[0],
            'sun_azi': struct.unpack('<f', d[30:34])[0],
            'alarm_byte': d[34],
        }
        return status

    def print_status(self, label="Status"):
        """Print current status."""
        s = self.get_status()
        if s:
            mode = "AUTO" if s['is_auto'] else "MANUAL"
            print(f"  {label}:")
            print(f"    Mode: {mode} (byte=0x{s['status_byte']:02x})")
            print(f"    Panel: H={s['panel_h']:.2f}° V={s['panel_v']:.2f}°")
            print(f"    Sun:   Az={s['sun_azi']:.2f}° Alt={s['sun_alt']:.2f}°")
            print(f"    Alarms: 0x{s['alarm_byte']:02x}")
            return s
        else:
            print(f"  {label}: No response")
            return None

    def test_auto_mode(self):
        """Test AUTO mode command."""
        print("\n" + "="*60)
        print("TEST: AUTO MODE")
        print("="*60)

        self.print_status("Before")

        print("\nSending AUTO_MODE command...")
        self.send_command(SolarTrackerProtocol.set_auto_mode(), "AUTO_MODE")
        time.sleep(2)

        s = self.print_status("After")

        if s and s['is_auto']:
            print("\n✓ AUTO mode confirmed")
            return True
        else:
            print("\n✗ AUTO mode NOT confirmed")
            return False

    def test_manual_mode(self):
        """Test MANUAL mode command."""
        print("\n" + "="*60)
        print("TEST: MANUAL MODE")
        print("="*60)

        self.print_status("Before")

        print("\nSending MANUAL_MODE command...")
        self.send_command(SolarTrackerProtocol.set_manual_mode(), "MANUAL_MODE")
        time.sleep(2)

        s = self.print_status("After")

        if s and not s['is_auto']:
            print("\n✓ MANUAL mode confirmed")
            return True
        else:
            print("\n✗ MANUAL mode NOT confirmed")
            return False

    def test_movement(self, direction, duration=2):
        """Test a movement command."""
        dir_name = direction.name
        print("\n" + "="*60)
        print(f"TEST: MOVE {dir_name}")
        print("="*60)

        before = self.get_status()
        if before:
            print(f"  Before: H={before['panel_h']:.2f}° V={before['panel_v']:.2f}°")

        print(f"\nSending MOVE_{dir_name} command...")
        self.send_command(
            SolarTrackerProtocol.build_movement_command_v2(direction),
            f"MOVE_{dir_name}"
        )

        print(f"Moving for {duration} seconds...")
        time.sleep(duration)

        print("Sending STOP command...")
        self.send_command(
            SolarTrackerProtocol.build_movement_command_v2(MovementCommand.STOP),
            "STOP"
        )
        time.sleep(1)

        after = self.get_status()
        if after:
            print(f"  After: H={after['panel_h']:.2f}° V={after['panel_v']:.2f}°")

        if before and after:
            h_diff = abs(after['panel_h'] - before['panel_h'])
            v_diff = abs(after['panel_v'] - before['panel_v'])

            if h_diff > 0.1 or v_diff > 0.1:
                print(f"\n✓ Movement detected: H={h_diff:.2f}° V={v_diff:.2f}°")
                return True
            else:
                print(f"\n? No significant movement (H={h_diff:.2f}° V={v_diff:.2f}°)")
                return False
        return False

    def run_all_tests(self):
        """Run all tests."""
        print("\n" + "#"*60)
        print("# SOLAR TRACKER COMPREHENSIVE TEST")
        print("#"*60)

        if not self.connect():
            return

        results = {}

        try:
            # Initial status
            print("\n" + "="*60)
            print("INITIAL STATUS")
            print("="*60)
            self.print_status("Current")

            # Test AUTO mode
            results['AUTO_MODE'] = self.test_auto_mode()

            # Test MANUAL mode
            results['MANUAL_MODE'] = self.test_manual_mode()

            # If in manual mode, test movements
            s = self.get_status()
            if s and not s['is_auto']:
                print("\n" + "-"*60)
                print("In MANUAL mode - testing movements")
                print("-"*60)

                results['MOVE_LEFT'] = self.test_movement(MovementCommand.LEFT, duration=2)
                results['MOVE_RIGHT'] = self.test_movement(MovementCommand.RIGHT, duration=2)
                # results['MOVE_UP'] = self.test_movement(MovementCommand.UP, duration=2)
                # results['MOVE_DOWN'] = self.test_movement(MovementCommand.DOWN, duration=2)
            else:
                print("\nSkipping movement tests (not in MANUAL mode)")
                results['MOVE_LEFT'] = None
                results['MOVE_RIGHT'] = None

            # Return to AUTO mode
            print("\n" + "="*60)
            print("RETURNING TO AUTO MODE")
            print("="*60)
            self.send_command(SolarTrackerProtocol.set_auto_mode(), "AUTO_MODE")
            time.sleep(2)
            self.print_status("Final")

        finally:
            self.disconnect()

        # Summary
        print("\n" + "#"*60)
        print("# TEST SUMMARY")
        print("#"*60)
        for test, result in results.items():
            if result is True:
                status = "✓ PASS"
            elif result is False:
                status = "✗ FAIL"
            else:
                status = "- SKIP"
            print(f"  {test}: {status}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Solar Tracker Comprehensive Test")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port")
    parser.add_argument("--baud", type=int, default=9600, help="Baud rate")
    args = parser.parse_args()

    tester = TrackerTester(port=args.port, baudrate=args.baud)
    tester.run_all_tests()


if __name__ == "__main__":
    main()
