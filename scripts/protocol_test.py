#!/usr/bin/env python3
"""
Solar Tracker Protocol Diagnostic Tool.

Interactive tool to test serial commands directly and debug why movement
commands aren't working while status requests work.

Usage:
    python3 protocol_test.py [--port /dev/ttyUSB0] [--baud 9600]
"""

import argparse
import struct
import time
import sys
from datetime import datetime

import serial


class ProtocolTester:
    """Interactive protocol testing tool."""

    # Known working packet headers
    COMMAND_HEADER = bytes([0x81, 0xFF, 0x00, 0x82, 0x00])
    RESPONSE_HEADER = bytes([0x81, 0x00, 0x01, 0x82, 0x00, 0x7c, 0x50])

    # Packet types
    TYPE_ALARM = 0x01
    TYPE_MOVEMENT = 0x02
    TYPE_STATUS = 0x08

    # Command codes
    CMD_START = 0x23  # '#'
    CMD_STOP = 0x24   # '$'
    CMD_CLEAR_ALARMS = 0x40  # '@'
    CMD_STATUS = 0x30  # '0'

    # Direction codes
    DIR_STOP = 0x00
    DIR_DOWN = 0x01
    DIR_UP = 0x02
    DIR_LEFT = 0x03
    DIR_RIGHT = 0x04

    FOOTER = 0x83

    def __init__(self, port: str, baudrate: int = 9600):
        self.port = port
        self.baudrate = baudrate
        self.serial: serial.Serial = None

    def connect(self) -> bool:
        """Connect to serial port."""
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=8,
                parity='N',
                stopbits=1,
                timeout=2.0,
            )
            print(f"Connected to {self.port} at {self.baudrate} baud")
            return True
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False

    def disconnect(self):
        """Disconnect from serial port."""
        if self.serial:
            self.serial.close()
            print("Disconnected")

    @staticmethod
    def checksum(data: bytes) -> int:
        """Calculate checksum (sum of bytes mod 256)."""
        return sum(data) & 0xFF

    def build_packet(self, packet_type: int, cmd: int, direction: int = None) -> bytes:
        """Build a command packet."""
        packet = bytearray(self.COMMAND_HEADER)
        packet.append(packet_type)
        packet.append(cmd)

        if direction is not None:
            packet.append(direction)

        packet.append(self.FOOTER)
        packet.append(self.checksum(packet))
        return bytes(packet)

    def send_and_receive(self, data: bytes, wait_time: float = 0.5) -> bytes:
        """Send data and wait for response."""
        # Clear any pending data
        self.serial.reset_input_buffer()

        # Send
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"\n[{timestamp}] TX ({len(data)} bytes):")
        print(f"  HEX: {data.hex(' ').upper()}")
        self.serial.write(data)

        # Wait for response
        time.sleep(wait_time)

        # Read response
        response = bytes()
        while self.serial.in_waiting > 0:
            response += self.serial.read(self.serial.in_waiting)
            time.sleep(0.05)

        if response:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{timestamp}] RX ({len(response)} bytes):")
            print(f"  HEX: {response.hex(' ').upper()}")
            self.parse_response(response)
        else:
            print("  (No response)")

        return response

    def parse_response(self, data: bytes):
        """Parse and display response details."""
        if len(data) < 7:
            return

        # Check if it's a status response
        if data[:7] == self.RESPONSE_HEADER and len(data) >= 38:
            print("  --- Parsed Status Response ---")
            try:
                # Date/time
                day = data[8]
                month = data[9]
                year = 2000 + data[10]
                second = data[11]
                minute = data[12]
                hour = data[13]
                print(f"  Date/Time: {year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}")

                # Panel position (little-endian floats)
                if len(data) >= 26:
                    panel_v = struct.unpack('<f', data[16:20])[0]
                    panel_h = struct.unpack('<f', data[22:26])[0]
                    print(f"  Panel Position: H={panel_h:.2f}° V={panel_v:.2f}°")

                # Sun position
                if len(data) >= 34:
                    sun_alt = struct.unpack('<f', data[26:30])[0]
                    sun_azi = struct.unpack('<f', data[30:34])[0]
                    print(f"  Sun Position: Azi={sun_azi:.2f}° Alt={sun_alt:.2f}°")

                # Alarm byte
                if len(data) > 20:
                    alarm_byte = data[20]
                    print(f"  Alarm Byte: 0x{alarm_byte:02X} (binary: {alarm_byte:08b})")
                    if alarm_byte:
                        alarms = []
                        if alarm_byte & 0x01: alarms.append("vertical_limit")
                        if alarm_byte & 0x02: alarms.append("east_limit")
                        if alarm_byte & 0x04: alarms.append("west_limit")
                        if alarm_byte & 0x08: alarms.append("wind_speed")
                        if alarm_byte & 0x10: alarms.append("actuator_current")
                        if alarm_byte & 0x20: alarms.append("rotation_current")
                        if alarm_byte & 0x40: alarms.append("horizontal_limit")
                        if alarm_byte & 0x80: alarms.append("encoder_error")
                        print(f"  Active Alarms: {', '.join(alarms)}")

                # Look for mode/status byte (investigating)
                print(f"  Byte 14: 0x{data[14]:02X}  Byte 15: 0x{data[15]:02X}  Byte 21: 0x{data[21]:02X}")

            except Exception as e:
                print(f"  Parse error: {e}")

        # Check for version string
        if b'Version' in data or b'Versio' in data:
            try:
                idx = data.find(b'Version')
                if idx == -1:
                    idx = data.find(b'Versio')
                version_str = data[idx:idx+15].decode('ascii', errors='ignore')
                version_str = version_str.replace('\x00', '')
                print(f"  Firmware: {version_str}")
            except:
                pass

    def test_status_request(self):
        """Test status request (known to work)."""
        print("\n" + "="*60)
        print("TEST: Status Request")
        print("="*60)
        packet = self.build_packet(self.TYPE_STATUS, self.CMD_STATUS)
        return self.send_and_receive(packet, wait_time=1.0)

    def test_movement(self, direction: int, start: bool = True):
        """Test movement command."""
        dir_names = {0: "STOP", 1: "DOWN", 2: "UP", 3: "LEFT", 4: "RIGHT"}
        cmd = self.CMD_START if start else self.CMD_STOP
        action = "START" if start else "STOP"

        print("\n" + "="*60)
        print(f"TEST: Movement {action} {dir_names.get(direction, '?')}")
        print("="*60)

        packet = self.build_packet(self.TYPE_MOVEMENT, cmd, direction)
        return self.send_and_receive(packet, wait_time=0.5)

    def test_movement_variations(self, direction: int):
        """Test different variations of movement command format."""
        dir_names = {0: "STOP", 1: "DOWN", 2: "UP", 3: "LEFT", 4: "RIGHT"}

        print("\n" + "="*60)
        print(f"TEST: Movement Variations for {dir_names.get(direction, '?')}")
        print("="*60)

        variations = [
            # Original format
            ("Original (81 FF 00 82 00 02...)",
             bytes([0x81, 0xFF, 0x00, 0x82, 0x00, 0x02, 0x23, direction, 0x83])),

            # Without broadcast (FF -> 00)
            ("No broadcast (81 00 00 82 00 02...)",
             bytes([0x81, 0x00, 0x00, 0x82, 0x00, 0x02, 0x23, direction, 0x83])),

            # Match response header style (81 00 01 82...)
            ("Response-style (81 00 01 82 00 02...)",
             bytes([0x81, 0x00, 0x01, 0x82, 0x00, 0x02, 0x23, direction, 0x83])),

            # Different byte 4 value
            ("Alt byte4 (81 FF 00 82 01 02...)",
             bytes([0x81, 0xFF, 0x00, 0x82, 0x01, 0x02, 0x23, direction, 0x83])),
        ]

        for name, packet_base in variations:
            checksum = self.checksum(packet_base)
            packet = packet_base + bytes([checksum])
            print(f"\n--- {name} ---")
            self.send_and_receive(packet, wait_time=0.3)
            time.sleep(0.2)

    def test_clear_alarms(self):
        """Test clear alarms command."""
        print("\n" + "="*60)
        print("TEST: Clear Alarms")
        print("="*60)
        packet = self.build_packet(self.TYPE_ALARM, self.CMD_CLEAR_ALARMS)
        return self.send_and_receive(packet, wait_time=0.5)

    def probe_unknown_commands(self):
        """Probe for unknown commands by trying different packet types."""
        print("\n" + "="*60)
        print("PROBE: Unknown Packet Types (searching for mode command)")
        print("="*60)

        # Try different packet types that might be mode-related
        test_types = [
            (0x03, 0x00, "Type 0x03, cmd 0x00"),
            (0x03, 0x01, "Type 0x03, cmd 0x01 (manual?)"),
            (0x03, 0x02, "Type 0x03, cmd 0x02 (auto?)"),
            (0x04, 0x00, "Type 0x04, cmd 0x00"),
            (0x04, 0x01, "Type 0x04, cmd 0x01"),
            (0x05, 0x00, "Type 0x05, cmd 0x00"),
            (0x06, 0x00, "Type 0x06, cmd 0x00"),
            (0x07, 0x00, "Type 0x07, cmd 0x00"),
            # Mode might use same type as alarm (0x01) with different cmd
            (0x01, 0x01, "Type 0x01, cmd 0x01 (mode?)"),
            (0x01, 0x02, "Type 0x01, cmd 0x02 (mode?)"),
            (0x01, 0x10, "Type 0x01, cmd 0x10"),
            (0x01, 0x20, "Type 0x01, cmd 0x20"),
            (0x01, 0x30, "Type 0x01, cmd 0x30"),
        ]

        for ptype, cmd, desc in test_types:
            packet_base = bytes([0x81, 0xFF, 0x00, 0x82, 0x00, ptype, cmd, 0x83])
            packet = packet_base + bytes([self.checksum(packet_base)])
            print(f"\n--- {desc} ---")
            resp = self.send_and_receive(packet, wait_time=0.3)
            time.sleep(0.1)

    def send_raw(self, hex_string: str):
        """Send raw hex bytes."""
        try:
            # Remove spaces and convert
            hex_clean = hex_string.replace(' ', '').replace('0x', '')
            data = bytes.fromhex(hex_clean)
            print(f"\nSending raw: {data.hex(' ').upper()}")
            return self.send_and_receive(data, wait_time=0.5)
        except Exception as e:
            print(f"Error: {e}")
            return None

    def interactive_mode(self):
        """Run interactive command prompt."""
        print("\n" + "="*60)
        print("Interactive Protocol Tester")
        print("="*60)
        print("""
Commands:
  s       - Send status request
  m <dir> - Start movement (dir: u/d/l/r for up/down/left/right)
  x <dir> - Stop movement
  c       - Clear alarms
  v <dir> - Test movement variations
  p       - Probe unknown commands (search for mode)
  raw <hex> - Send raw hex bytes (e.g., 'raw 81 ff 00 82 00 02 23 02 83 ac')
  q       - Quit
""")

        while True:
            try:
                cmd = input("\n> ").strip().lower()

                if not cmd:
                    continue
                elif cmd == 'q':
                    break
                elif cmd == 's':
                    self.test_status_request()
                elif cmd == 'c':
                    self.test_clear_alarms()
                elif cmd == 'p':
                    self.probe_unknown_commands()
                elif cmd.startswith('m '):
                    direction = {'u': 2, 'd': 1, 'l': 3, 'r': 4}.get(cmd[2:].strip(), 0)
                    self.test_movement(direction, start=True)
                elif cmd.startswith('x '):
                    direction = {'u': 2, 'd': 1, 'l': 3, 'r': 4}.get(cmd[2:].strip(), 0)
                    self.test_movement(direction, start=False)
                elif cmd.startswith('v '):
                    direction = {'u': 2, 'd': 1, 'l': 3, 'r': 4}.get(cmd[2:].strip(), 2)
                    self.test_movement_variations(direction)
                elif cmd.startswith('raw '):
                    self.send_raw(cmd[4:])
                else:
                    print("Unknown command. Type 'q' to quit.")

            except KeyboardInterrupt:
                print("\nInterrupted")
                break
            except EOFError:
                break

    def run_all_tests(self):
        """Run all diagnostic tests."""
        print("\n" + "#"*60)
        print("# RUNNING ALL DIAGNOSTIC TESTS")
        print("#"*60)

        # Test 1: Status request (should work)
        print("\n[1/5] Testing status request...")
        self.test_status_request()
        time.sleep(0.5)

        # Test 2: Movement commands
        print("\n[2/5] Testing movement UP (start)...")
        self.test_movement(self.DIR_UP, start=True)
        time.sleep(1.0)

        print("\n[3/5] Testing movement UP (stop)...")
        self.test_movement(self.DIR_UP, start=False)
        time.sleep(0.5)

        # Test 3: Movement variations
        print("\n[4/5] Testing movement variations...")
        self.test_movement_variations(self.DIR_UP)
        time.sleep(0.5)

        # Test 4: Probe for mode commands
        print("\n[5/5] Probing for unknown commands...")
        self.probe_unknown_commands()

        print("\n" + "#"*60)
        print("# TESTS COMPLETE")
        print("#"*60)


def main():
    parser = argparse.ArgumentParser(description="Solar Tracker Protocol Diagnostic Tool")
    parser.add_argument('--port', '-p', default='/dev/ttyUSB0', help='Serial port')
    parser.add_argument('--baud', '-b', type=int, default=9600, help='Baud rate')
    parser.add_argument('--interactive', '-i', action='store_true', help='Interactive mode')
    parser.add_argument('--all', '-a', action='store_true', help='Run all tests')

    args = parser.parse_args()

    tester = ProtocolTester(args.port, args.baud)

    if not tester.connect():
        sys.exit(1)

    try:
        if args.all:
            tester.run_all_tests()
        elif args.interactive:
            tester.interactive_mode()
        else:
            # Default: run basic tests then go interactive
            print("Running basic tests, then entering interactive mode...")
            tester.test_status_request()
            time.sleep(0.5)
            tester.test_movement(tester.DIR_UP, start=True)
            time.sleep(1.0)
            tester.test_movement(tester.DIR_UP, start=False)
            time.sleep(0.5)
            print("\nEntering interactive mode...")
            tester.interactive_mode()

    finally:
        tester.disconnect()


if __name__ == '__main__':
    main()
