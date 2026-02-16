#!/usr/bin/env python3
"""
Dual Agent Test - Monitor and Control running together.

Simulates two agents:
- MONITOR: Continuously polls tracker status and reports position changes
- CONTROL: Sends commands and waits for confirmation via monitor

Since both need serial port access, this runs them in a coordinated way.
"""

import sys
import os
import time
import json
import threading
from datetime import datetime
from queue import Queue

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from solartracker.protocol import SolarTrackerProtocol, ResponseOffsets
import serial


class DualAgentTest:
    def __init__(self, port="/dev/ttyUSB0", baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.running = False

        # State tracking
        self.position_history = []
        self.last_position = {"horizontal": None, "vertical": None}
        self.command_queue = Queue()
        self.movement_events = []

    def log_monitor(self, msg):
        """Log message from monitor agent perspective."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] [MONITOR] {msg}")

    def log_control(self, msg):
        """Log message from control agent perspective."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] [CONTROL] {msg}")

    def connect(self):
        """Connect to serial port."""
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=8,
                parity='N',
                stopbits=1,
                timeout=0.5
            )
            self.log_monitor(f"Connected to {self.port} at {self.baudrate} baud")
            return True
        except Exception as e:
            self.log_monitor(f"Connection failed: {e}")
            return False

    def send_packet(self, packet, description=""):
        """Send a packet to the tracker."""
        if not self.serial:
            return False
        try:
            self.serial.write(packet)
            self.log_control(f"TX: {packet.hex()} ({description})")
            return True
        except Exception as e:
            self.log_control(f"Send failed: {e}")
            return False

    def read_response(self, timeout=1.0):
        """Read response from tracker."""
        start = time.time()
        buffer = bytearray()

        while time.time() - start < timeout:
            if self.serial.in_waiting > 0:
                data = self.serial.read(self.serial.in_waiting)
                buffer.extend(data)

                # Look for enough data for a valid response
                if len(buffer) >= 30:
                    break

            time.sleep(0.01)

        if buffer:
            return bytes(buffer)
        return None

    def parse_position(self, data):
        """Extract position from response data."""
        parsed = SolarTrackerProtocol.parse_response(data)
        if parsed:
            return parsed.get("position", {}), parsed.get("sun_position", {})
        return {}, {}

    def detect_movement(self, new_h, new_v):
        """Check if position changed significantly."""
        if self.last_position["horizontal"] is None:
            return False

        old_h = self.last_position["horizontal"] or 0
        old_v = self.last_position["vertical"] or 0
        new_h = new_h or 0
        new_v = new_v or 0

        h_diff = abs(new_h - old_h)
        v_diff = abs(new_v - old_v)

        return h_diff > 0.1 or v_diff > 0.1

    def monitor_poll(self, poll_num):
        """Single monitor poll cycle."""
        # Request status
        packet = SolarTrackerProtocol.build_status_request()
        self.serial.write(packet)

        # Read response
        time.sleep(0.1)
        data = self.read_response(timeout=0.8)

        if data:
            pos, sun = self.parse_position(data)
            h = pos.get("horizontal")
            v = pos.get("vertical")

            if h is not None:
                moving = self.detect_movement(h, v)

                if moving:
                    old_h = self.last_position["horizontal"] or 0
                    old_v = self.last_position["vertical"] or 0
                    h_diff = abs(h - old_h)
                    v_diff = abs(v - old_v)

                    self.log_monitor("*** MOVEMENT DETECTED! ***")
                    self.log_monitor(f"    Old: H={old_h:.2f}° V={old_v:.2f}°")
                    self.log_monitor(f"    New: H={h:.2f}° V={v:.2f}°")
                    self.log_monitor(f"    Diff: H={h_diff:.2f}° V={v_diff:.2f}°")

                    self.movement_events.append({
                        "time": datetime.now().isoformat(),
                        "old_h": old_h, "old_v": old_v,
                        "new_h": h, "new_v": v
                    })

                self.last_position = {"horizontal": h, "vertical": v}
                self.position_history.append({
                    "poll": poll_num,
                    "time": datetime.now().isoformat(),
                    "h": h, "v": v,
                    "moving": moving
                })

                status = "MOVING" if moving else "stable"
                self.log_monitor(f"Poll #{poll_num}: H={h:.2f}° V={v:.2f}° [{status}]")
                return h, v, moving

            self.log_monitor(f"Poll #{poll_num}: Position data invalid")
        else:
            self.log_monitor(f"Poll #{poll_num}: No response")

        return None, None, False

    def run_test(self, test_type="auto_mode"):
        """
        Run the dual agent test.

        Test types:
        - auto_mode: Set to automatic mode and watch for sun tracking movement
        """
        if not self.connect():
            return False

        print("=" * 70)
        print(f"DUAL AGENT TEST: {test_type.upper()}")
        print("=" * 70)
        print()

        if test_type == "auto_mode":
            return self._test_auto_mode()
        else:
            self.log_control(f"Unknown test type: {test_type}")
            return False

    def _test_auto_mode(self):
        """Test setting automatic mode and monitoring for movement."""

        # Phase 1: Initial monitoring to establish baseline
        print("-" * 70)
        self.log_monitor("PHASE 1: Establishing baseline position")
        print("-" * 70)

        for i in range(5):
            self.monitor_poll(i + 1)
            time.sleep(1)

        if self.last_position["horizontal"] is None:
            self.log_monitor("ERROR: Could not read tracker position!")
            return False

        baseline_h = self.last_position["horizontal"]
        baseline_v = self.last_position["vertical"]
        self.log_monitor(f"Baseline established: H={baseline_h:.2f}° V={baseline_v:.2f}°")
        print()

        # Phase 2: Control agent sends AUTO_MODE command
        print("-" * 70)
        self.log_control("PHASE 2: Sending AUTO_MODE command")
        print("-" * 70)

        # Clear movement events
        self.movement_events = []

        packet = SolarTrackerProtocol.set_auto_mode()
        self.log_control(f"Sending AUTO_MODE packet: {packet.hex()}")

        if not self.send_packet(packet, "AUTO_MODE"):
            self.log_control("ERROR: Failed to send command!")
            return False

        self.log_control("Command sent. Notifying monitor agent to watch for movement...")
        self.log_monitor("Received notification from CONTROL. Starting movement detection...")
        print()

        # Phase 3: Monitor for movement
        print("-" * 70)
        self.log_monitor("PHASE 3: Monitoring for sun tracking movement")
        print("-" * 70)

        movement_confirmed = False
        max_polls = 30  # Monitor for ~30 seconds

        for i in range(max_polls):
            h, v, moving = self.monitor_poll(i + 6)  # Continue poll numbering

            if h is not None:
                # Calculate total movement from baseline
                total_h_diff = abs(h - baseline_h)
                total_v_diff = abs(v - baseline_v)

                if total_h_diff > 1.0 or total_v_diff > 1.0:
                    movement_confirmed = True
                    self.log_control(f">>> CONTROL received movement confirmation from MONITOR")
                    self.log_control(f"    Total movement: H={total_h_diff:.2f}° V={total_v_diff:.2f}°")

            if self.movement_events:
                # Report to control agent
                event = self.movement_events[-1]
                self.log_control(f">>> CONTROL received movement event from MONITOR")

            time.sleep(1)

        print()

        # Phase 4: Summary
        print("=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)

        final_h = self.last_position["horizontal"] or 0
        final_v = self.last_position["vertical"] or 0
        total_h_change = abs(final_h - baseline_h)
        total_v_change = abs(final_v - baseline_v)

        print(f"Baseline position:    H={baseline_h:.2f}° V={baseline_v:.2f}°")
        print(f"Final position:       H={final_h:.2f}° V={final_v:.2f}°")
        print(f"Total position change: H={total_h_change:.2f}° V={total_v_change:.2f}°")
        print(f"Movement events detected: {len(self.movement_events)}")
        print(f"Movement confirmed: {movement_confirmed}")
        print()

        if movement_confirmed:
            print("RESULT: Tracker IS responding to AUTO_MODE - sun tracking active!")
        elif len(self.movement_events) > 0:
            print("RESULT: Some movement detected, tracker may be responding")
        else:
            print("RESULT: No significant movement - tracker may already be at target or not responding")

        print("=" * 70)

        # Close connection
        if self.serial:
            self.serial.close()

        return movement_confirmed


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Dual Agent Test for Solar Tracker")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port")
    parser.add_argument("--baud", type=int, default=9600, help="Baud rate")
    parser.add_argument("--test", default="auto_mode", choices=["auto_mode"], help="Test type")
    args = parser.parse_args()

    test = DualAgentTest(port=args.port, baudrate=args.baud)
    success = test.run_test(args.test)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
