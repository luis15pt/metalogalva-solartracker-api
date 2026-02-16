#!/usr/bin/env python3
"""
Control Agent - Sends commands to tracker and monitors for changes.

Reads status from monitor agent and sends commands based on state.
"""

import sys
import os
import time
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from solartracker.protocol import SolarTrackerProtocol, ModeCommand, MovementCommand
import serial

# Shared communication files
STATUS_FILE = "/tmp/tracker_monitor_status.json"
SIGNAL_FILE = "/tmp/tracker_control_signal.txt"

class ControlAgent:
    def __init__(self, port="/dev/ttyUSB0", baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.serial = None

    def connect(self):
        """Connect to serial port."""
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=8,
                parity='N',
                stopbits=1,
                timeout=1.0
            )
            print(f"[CONTROL] Connected to {self.port} at {self.baudrate} baud")
            return True
        except Exception as e:
            print(f"[CONTROL] Connection failed: {e}")
            return False

    def send_command(self, packet, description=""):
        """Send a command packet."""
        if not self.serial:
            print("[CONTROL] Not connected!")
            return False

        try:
            self.serial.write(packet)
            print(f"[CONTROL] TX: {packet.hex()} ({description})")
            return True
        except Exception as e:
            print(f"[CONTROL] Send failed: {e}")
            return False

    def set_automatic_mode(self):
        """Set tracker to automatic mode."""
        packet = SolarTrackerProtocol.set_auto_mode()
        return self.send_command(packet, "AUTO_MODE")

    def set_manual_mode(self):
        """Set tracker to manual mode."""
        packet = SolarTrackerProtocol.set_manual_mode()
        return self.send_command(packet, "MANUAL_MODE")

    def read_monitor_status(self):
        """Read status from monitor agent."""
        try:
            if os.path.exists(STATUS_FILE):
                with open(STATUS_FILE, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"[CONTROL] Failed to read status: {e}")
        return None

    def signal_monitor(self, message):
        """Send a signal to the monitor agent."""
        try:
            with open(SIGNAL_FILE, 'w') as f:
                f.write(message)
        except Exception as e:
            print(f"[CONTROL] Failed to signal monitor: {e}")

    def wait_for_monitor(self, timeout=10):
        """Wait for monitor agent to be running."""
        print(f"[CONTROL] Waiting for monitor agent...")
        start = time.time()
        while time.time() - start < timeout:
            status = self.read_monitor_status()
            if status and status.get("running"):
                print(f"[CONTROL] Monitor agent is running")
                return True
            time.sleep(0.5)
        print(f"[CONTROL] Monitor agent not detected within {timeout}s")
        return False

    def run_auto_mode_test(self):
        """Run test: set automatic mode and watch for movement."""
        if not self.connect():
            return False

        print("=" * 60)
        print("[CONTROL] AUTOMATIC MODE TEST")
        print("=" * 60)

        # Get initial position from monitor
        initial_status = self.read_monitor_status()
        if initial_status:
            pos = initial_status.get("position", {})
            print(f"[CONTROL] Initial position: H={pos.get('horizontal', 'N/A')} V={pos.get('vertical', 'N/A')}")

        # Signal monitor we're about to send command
        self.signal_monitor("SENDING_AUTO_MODE")

        print(f"\n[CONTROL] Sending AUTO_MODE command...")
        time.sleep(1)

        # Send automatic mode command
        success = self.set_automatic_mode()
        if not success:
            print("[CONTROL] Failed to send command!")
            return False

        print(f"[CONTROL] Command sent. Monitoring for movement...")
        print("-" * 60)

        # Monitor for position changes
        start_time = time.time()
        check_count = 0
        initial_h = None
        initial_v = None
        movement_detected = False

        while time.time() - start_time < 30:  # Monitor for 30 seconds
            check_count += 1
            status = self.read_monitor_status()

            if status:
                pos = status.get("position", {})
                h = pos.get("horizontal")
                v = pos.get("vertical")

                if h is not None:
                    if initial_h is None:
                        initial_h = h
                        initial_v = v

                    h_diff = abs(h - initial_h) if initial_h else 0
                    v_diff = abs(v - initial_v) if initial_v else 0

                    if h_diff > 0.5 or v_diff > 0.5:
                        movement_detected = True
                        print(f"[CONTROL] *** MOVEMENT CONFIRMED! ***")
                        print(f"         H: {initial_h:.2f} -> {h:.2f} (diff: {h_diff:.2f})")
                        print(f"         V: {initial_v:.2f} -> {v:.2f} (diff: {v_diff:.2f})")

                    print(f"[CONTROL] Check #{check_count}: H={h:.2f} V={v:.2f} | H_diff={h_diff:.2f} V_diff={v_diff:.2f}")

                if status.get("movement_detected"):
                    print("[CONTROL] Monitor agent reports movement!")
                    movement_detected = True

            time.sleep(2)

        print("-" * 60)
        print(f"[CONTROL] Test complete after {check_count} checks")
        print(f"[CONTROL] Movement detected: {movement_detected}")

        # Clean up signal file
        if os.path.exists(SIGNAL_FILE):
            os.remove(SIGNAL_FILE)

        if self.serial:
            self.serial.close()

        return movement_detected


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Solar Tracker Control Agent")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port")
    parser.add_argument("--baud", type=int, default=9600, help="Baud rate")
    parser.add_argument("--wait-monitor", action="store_true", help="Wait for monitor agent first")
    args = parser.parse_args()

    agent = ControlAgent(port=args.port, baudrate=args.baud)

    if args.wait_monitor:
        if not agent.wait_for_monitor():
            print("[CONTROL] Proceeding without monitor agent")

    agent.run_auto_mode_test()


if __name__ == "__main__":
    main()
