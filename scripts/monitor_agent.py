#!/usr/bin/env python3
"""
Monitor Agent - Watches tracker position and reports movement.

Writes status updates to a shared log file for the control agent to read.
"""

import sys
import os
import time
import json
import threading
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from solartracker.protocol import SolarTrackerProtocol, ResponseOffsets
from solartracker.config import settings
import serial

# Shared communication file
STATUS_FILE = "/tmp/tracker_monitor_status.json"
SIGNAL_FILE = "/tmp/tracker_control_signal.txt"

class MonitorAgent:
    def __init__(self, port="/dev/ttyUSB0", baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.running = False
        self.last_position = {"horizontal": None, "vertical": None}
        self.movement_detected = False
        self.position_history = []

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
            print(f"[MONITOR] Connected to {self.port} at {self.baudrate} baud")
            return True
        except Exception as e:
            print(f"[MONITOR] Connection failed: {e}")
            return False

    def request_status(self):
        """Send status request to tracker."""
        packet = SolarTrackerProtocol.build_status_request()
        self.serial.write(packet)
        print(f"[MONITOR] TX: {packet.hex()}")

    def read_response(self, timeout=2.0):
        """Read and parse response from tracker."""
        start = time.time()
        buffer = bytearray()

        while time.time() - start < timeout:
            if self.serial.in_waiting > 0:
                data = self.serial.read(self.serial.in_waiting)
                buffer.extend(data)

                # Check for complete response (look for version string)
                if b'Version' in buffer and len(buffer) >= ResponseOffsets.MIN_PACKET_SIZE:
                    print(f"[MONITOR] RX: {buffer.hex()}")
                    return self.parse_response(bytes(buffer))

            time.sleep(0.01)

        if buffer:
            print(f"[MONITOR] RX (incomplete): {buffer.hex()}")
            return self.parse_response(bytes(buffer))
        return None

    def parse_response(self, data):
        """Parse tracker response."""
        parsed = SolarTrackerProtocol.parse_response(data)
        return parsed

    def detect_movement(self, new_pos):
        """Detect if tracker is moving."""
        if self.last_position["horizontal"] is None:
            return False

        h_diff = abs((new_pos.get("horizontal") or 0) - (self.last_position["horizontal"] or 0))
        v_diff = abs((new_pos.get("vertical") or 0) - (self.last_position["vertical"] or 0))

        # Movement threshold: 0.1 degrees
        return h_diff > 0.1 or v_diff > 0.1

    def write_status(self, status):
        """Write status to shared file."""
        try:
            with open(STATUS_FILE, 'w') as f:
                json.dump(status, f, indent=2, default=str)
        except Exception as e:
            print(f"[MONITOR] Failed to write status: {e}")

    def check_control_signal(self):
        """Check if control agent wants to send a command."""
        try:
            if os.path.exists(SIGNAL_FILE):
                with open(SIGNAL_FILE, 'r') as f:
                    return f.read().strip()
        except:
            pass
        return None

    def run(self, duration=60):
        """Run the monitor loop."""
        if not self.connect():
            return

        self.running = True
        start_time = time.time()
        poll_count = 0

        print(f"[MONITOR] Starting monitor for {duration} seconds...")
        print(f"[MONITOR] Writing status to {STATUS_FILE}")
        print("-" * 60)

        try:
            while self.running and (time.time() - start_time) < duration:
                poll_count += 1

                # Request status
                self.request_status()
                time.sleep(0.1)  # Brief delay for response

                # Read response
                response = self.read_response(timeout=1.0)

                if response:
                    position = response.get("position", {})
                    sun = response.get("sun_position", {})
                    version = response.get("version", "unknown")

                    # Detect movement
                    if position.get("horizontal") is not None:
                        moving = self.detect_movement(position)

                        if moving:
                            self.movement_detected = True
                            print(f"[MONITOR] *** MOVEMENT DETECTED! ***")
                            print(f"         Old: H={self.last_position['horizontal']:.2f} V={self.last_position['vertical']:.2f}")
                            print(f"         New: H={position.get('horizontal', 0):.2f} V={position.get('vertical', 0):.2f}")

                        self.last_position = {
                            "horizontal": position.get("horizontal"),
                            "vertical": position.get("vertical")
                        }

                        # Add to history
                        self.position_history.append({
                            "time": datetime.now().isoformat(),
                            "horizontal": position.get("horizontal"),
                            "vertical": position.get("vertical"),
                            "moving": moving
                        })

                        # Keep last 100 entries
                        self.position_history = self.position_history[-100:]

                    # Write status for control agent
                    status = {
                        "timestamp": datetime.now().isoformat(),
                        "poll_count": poll_count,
                        "position": position,
                        "sun_position": sun,
                        "version": version,
                        "movement_detected": self.movement_detected,
                        "last_position": self.last_position,
                        "running": True
                    }
                    self.write_status(status)

                    # Print summary
                    h = position.get("horizontal", 0) or 0
                    v = position.get("vertical", 0) or 0
                    print(f"[MONITOR] Poll #{poll_count}: Panel H={h:.2f}° V={v:.2f}° | Moving: {moving if position.get('horizontal') else 'N/A'}")

                else:
                    print(f"[MONITOR] Poll #{poll_count}: No response")

                # Check for control signal
                signal = self.check_control_signal()
                if signal:
                    print(f"[MONITOR] Received control signal: {signal}")

                # Poll interval
                time.sleep(1.0)

        except KeyboardInterrupt:
            print("\n[MONITOR] Interrupted by user")
        finally:
            self.running = False
            self.write_status({"running": False, "final_position": self.last_position})

            if self.serial:
                self.serial.close()

            print("-" * 60)
            print(f"[MONITOR] Stopped after {poll_count} polls")
            print(f"[MONITOR] Movement detected: {self.movement_detected}")
            print(f"[MONITOR] Final position: H={self.last_position.get('horizontal', 'N/A')} V={self.last_position.get('vertical', 'N/A')}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Solar Tracker Monitor Agent")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port")
    parser.add_argument("--baud", type=int, default=9600, help="Baud rate")
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    args = parser.parse_args()

    agent = MonitorAgent(port=args.port, baudrate=args.baud)
    agent.run(duration=args.duration)
