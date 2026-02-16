#!/usr/bin/env python3
"""
Serial Sniffer for Solar Tracker Protocol Capture.

This script helps capture the serial communication between the original
STcontrol application and the solar tracker to reverse engineer the protocol.

Usage:
    1. Set up a virtual serial port pair (com0com on Windows, socat on Linux)
    2. Connect the original app to one virtual port
    3. Run this sniffer on the physical port
    4. The sniffer bridges traffic while logging all data

On Linux with socat:
    socat -d -d pty,raw,echo=0,link=/tmp/vserial0 pty,raw,echo=0,link=/tmp/vserial1

On Windows with com0com:
    Create a pair like COM10 <-> COM11
    Original app connects to COM10
    This sniffer connects to COM11 and the real tracker port
"""

import argparse
import datetime
import os
import sys
import threading
import time
from typing import Optional

import serial
from serial.tools import list_ports


class SerialSniffer:
    """Sniffs serial traffic between two ports."""

    def __init__(
        self,
        port_a: str,
        port_b: str,
        baudrate: int = 9600,
        log_file: Optional[str] = None,
    ):
        self.port_a_name = port_a
        self.port_b_name = port_b
        self.baudrate = baudrate
        self.log_file = log_file

        self.port_a: Optional[serial.Serial] = None
        self.port_b: Optional[serial.Serial] = None

        self.running = False
        self._log_handle = None

    def start(self):
        """Start the sniffer."""
        print(f"Opening {self.port_a_name} (App) at {self.baudrate} baud...")
        self.port_a = serial.Serial(
            self.port_a_name,
            self.baudrate,
            timeout=0.1,
        )

        print(f"Opening {self.port_b_name} (Tracker) at {self.baudrate} baud...")
        self.port_b = serial.Serial(
            self.port_b_name,
            self.baudrate,
            timeout=0.1,
        )

        if self.log_file:
            self._log_handle = open(self.log_file, 'a')
            self._log(f"\n{'='*60}")
            self._log(f"Session started: {datetime.datetime.now()}")
            self._log(f"Port A (App): {self.port_a_name}")
            self._log(f"Port B (Tracker): {self.port_b_name}")
            self._log(f"Baud rate: {self.baudrate}")
            self._log(f"{'='*60}\n")

        self.running = True

        # Start forwarding threads
        thread_a = threading.Thread(target=self._forward, args=(self.port_a, self.port_b, "TX (App->Tracker)"))
        thread_b = threading.Thread(target=self._forward, args=(self.port_b, self.port_a, "RX (Tracker->App)"))

        thread_a.daemon = True
        thread_b.daemon = True

        thread_a.start()
        thread_b.start()

        print("\nSniffer running. Press Ctrl+C to stop.\n")
        print("-" * 60)

        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nStopping sniffer...")
            self.stop()

    def stop(self):
        """Stop the sniffer."""
        self.running = False

        if self.port_a:
            self.port_a.close()
        if self.port_b:
            self.port_b.close()
        if self._log_handle:
            self._log_handle.close()

    def _forward(self, source: serial.Serial, dest: serial.Serial, direction: str):
        """Forward data from source to destination while logging."""
        while self.running:
            try:
                if source.in_waiting > 0:
                    data = source.read(source.in_waiting)
                    if data:
                        # Forward the data
                        dest.write(data)

                        # Log the data
                        self._log_data(direction, data)

                time.sleep(0.001)  # Small delay to prevent CPU spinning

            except serial.SerialException as e:
                print(f"Serial error: {e}")
                self.running = False
                break

    def _log_data(self, direction: str, data: bytes):
        """Log captured data."""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        hex_data = data.hex(' ').upper()
        ascii_data = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)

        log_line = f"[{timestamp}] {direction}:\n"
        log_line += f"  HEX: {hex_data}\n"
        log_line += f"  ASC: {ascii_data}\n"
        log_line += f"  LEN: {len(data)} bytes\n"

        print(log_line)

        if self._log_handle:
            self._log_handle.write(log_line)
            self._log_handle.flush()

    def _log(self, message: str):
        """Write a message to the log file."""
        if self._log_handle:
            self._log_handle.write(message + "\n")
            self._log_handle.flush()


class SimpleLogger:
    """Simple logger that just captures data from a single port."""

    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        log_file: Optional[str] = None,
    ):
        self.port_name = port
        self.baudrate = baudrate
        self.log_file = log_file

        self.serial_port: Optional[serial.Serial] = None
        self.running = False
        self._log_handle = None

    def start(self):
        """Start logging."""
        print(f"Opening {self.port_name} at {self.baudrate} baud...")
        self.serial_port = serial.Serial(
            self.port_name,
            self.baudrate,
            timeout=0.1,
        )

        if self.log_file:
            self._log_handle = open(self.log_file, 'a')
            self._log(f"\n{'='*60}")
            self._log(f"Session started: {datetime.datetime.now()}")
            self._log(f"Port: {self.port_name}")
            self._log(f"Baud rate: {self.baudrate}")
            self._log(f"{'='*60}\n")

        self.running = True
        print("\nLogging started. Press Ctrl+C to stop.\n")
        print("-" * 60)

        try:
            while self.running:
                if self.serial_port.in_waiting > 0:
                    data = self.serial_port.read(self.serial_port.in_waiting)
                    if data:
                        self._log_data(data)
                time.sleep(0.001)

        except KeyboardInterrupt:
            print("\nStopping logger...")
        finally:
            self.stop()

    def stop(self):
        """Stop logging."""
        self.running = False

        if self.serial_port:
            self.serial_port.close()
        if self._log_handle:
            self._log_handle.close()

    def _log_data(self, data: bytes):
        """Log captured data."""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        hex_data = data.hex(' ').upper()
        ascii_data = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)

        log_line = f"[{timestamp}] Received:\n"
        log_line += f"  HEX: {hex_data}\n"
        log_line += f"  ASC: {ascii_data}\n"
        log_line += f"  LEN: {len(data)} bytes\n"

        print(log_line)

        if self._log_handle:
            self._log_handle.write(log_line)
            self._log_handle.flush()

    def _log(self, message: str):
        """Write a message to the log file."""
        if self._log_handle:
            self._log_handle.write(message + "\n")
            self._log_handle.flush()


def list_serial_ports():
    """List available serial ports."""
    print("\nAvailable serial ports:")
    print("-" * 40)

    ports = list_ports.comports()
    if not ports:
        print("No serial ports found.")
        return

    for port in ports:
        print(f"  {port.device}")
        print(f"    Description: {port.description}")
        print(f"    HWID: {port.hwid}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Serial sniffer for protocol capture",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  List available ports:
    python serial_sniffer.py --list

  Simple logging (just watch one port):
    python serial_sniffer.py --port /dev/ttyUSB0 --log capture.txt

  MITM sniffing (bridge between app and tracker):
    python serial_sniffer.py --port-a /dev/ttyUSB0 --port-b /dev/ttyUSB1 --log capture.txt

  Windows example:
    python serial_sniffer.py --port COM3 --baudrate 9600 --log capture.txt
        """
    )

    parser.add_argument('--list', '-l', action='store_true',
                        help='List available serial ports')
    parser.add_argument('--port', '-p', type=str,
                        help='Serial port for simple logging mode')
    parser.add_argument('--port-a', type=str,
                        help='First serial port (connects to app) for MITM mode')
    parser.add_argument('--port-b', type=str,
                        help='Second serial port (connects to tracker) for MITM mode')
    parser.add_argument('--baudrate', '-b', type=int, default=9600,
                        help='Baud rate (default: 9600)')
    parser.add_argument('--log', '-o', type=str,
                        help='Output log file')

    args = parser.parse_args()

    if args.list:
        list_serial_ports()
        return

    if args.port_a and args.port_b:
        # MITM sniffer mode
        sniffer = SerialSniffer(
            args.port_a,
            args.port_b,
            args.baudrate,
            args.log,
        )
        sniffer.start()

    elif args.port:
        # Simple logging mode
        logger = SimpleLogger(
            args.port,
            args.baudrate,
            args.log,
        )
        logger.start()

    else:
        parser.print_help()
        print("\nError: Specify --port for simple logging or --port-a and --port-b for MITM mode")
        sys.exit(1)


if __name__ == '__main__':
    main()
