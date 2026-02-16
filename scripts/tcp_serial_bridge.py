#!/usr/bin/env python3
"""
TCP-to-Serial Bridge with Traffic Logging.

This creates a TCP server that bridges to the serial port, allowing a Windows
machine to connect over the network and control the tracker while we capture
the traffic.

Usage:
    1. Stop the Docker container: docker stop solartracker-api
    2. Run this bridge: python3 tcp_serial_bridge.py
    3. On Windows, use a virtual COM port tool (e.g., com0com + com2tcp, or HW VSP)
       to create a virtual COM port that connects to this Pi's IP:4000
    4. Run STcontrol.exe and connect to the virtual COM port
    5. All traffic will be logged to tcp_serial_capture.log

Requirements:
    pip install pyserial
"""

import argparse
import asyncio
import datetime
import sys
from typing import Optional

import serial


class TCPSerialBridge:
    """Bridges TCP connections to a serial port with logging."""

    def __init__(
        self,
        serial_port: str,
        baudrate: int,
        tcp_port: int,
        log_file: str,
    ):
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.tcp_port = tcp_port
        self.log_file = log_file

        self.serial: Optional[serial.Serial] = None
        self.log_handle = None
        self.client_writer = None

    def log(self, direction: str, data: bytes):
        """Log data with timestamp."""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        hex_data = data.hex(' ').upper()
        ascii_repr = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)

        log_line = f"[{timestamp}] {direction} ({len(data)} bytes):\n"
        log_line += f"  HEX: {hex_data}\n"
        log_line += f"  ASC: {ascii_repr}\n"

        print(log_line, end='')

        if self.log_handle:
            self.log_handle.write(log_line)
            self.log_handle.flush()

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a TCP client connection."""
        addr = writer.get_extra_info('peername')
        print(f"\n{'='*60}")
        print(f"Client connected: {addr}")
        print(f"{'='*60}\n")

        if self.log_handle:
            self.log_handle.write(f"\n{'='*60}\n")
            self.log_handle.write(f"Session started: {datetime.datetime.now()}\n")
            self.log_handle.write(f"Client: {addr}\n")
            self.log_handle.write(f"{'='*60}\n\n")

        self.client_writer = writer

        try:
            # Start serial read task
            serial_task = asyncio.create_task(self.serial_to_tcp())

            # Read from TCP, write to serial
            while True:
                data = await reader.read(1024)
                if not data:
                    break

                self.log("TX (App->Tracker)", data)
                self.serial.write(data)

            serial_task.cancel()

        except Exception as e:
            print(f"Client error: {e}")
        finally:
            print(f"\nClient disconnected: {addr}")
            self.client_writer = None
            writer.close()
            await writer.wait_closed()

    async def serial_to_tcp(self):
        """Read from serial and send to TCP client."""
        loop = asyncio.get_event_loop()

        while True:
            try:
                # Check for serial data (non-blocking)
                if self.serial.in_waiting > 0:
                    data = await loop.run_in_executor(
                        None, self.serial.read, self.serial.in_waiting
                    )
                    if data and self.client_writer:
                        self.log("RX (Tracker->App)", data)
                        self.client_writer.write(data)
                        await self.client_writer.drain()

                await asyncio.sleep(0.01)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Serial read error: {e}")
                break

    async def run(self):
        """Run the bridge server."""
        # Open serial port
        print(f"Opening serial port {self.serial_port} at {self.baudrate} baud...")
        self.serial = serial.Serial(
            self.serial_port,
            self.baudrate,
            timeout=0.1,
        )
        print(f"Serial port opened.")

        # Open log file
        if self.log_file:
            self.log_handle = open(self.log_file, 'a')
            self.log_handle.write(f"\n{'#'*60}\n")
            self.log_handle.write(f"# TCP-Serial Bridge Started: {datetime.datetime.now()}\n")
            self.log_handle.write(f"# Serial: {self.serial_port} @ {self.baudrate}\n")
            self.log_handle.write(f"# TCP Port: {self.tcp_port}\n")
            self.log_handle.write(f"{'#'*60}\n\n")

        # Start TCP server
        server = await asyncio.start_server(
            self.handle_client,
            '0.0.0.0',
            self.tcp_port,
        )

        addr = server.sockets[0].getsockname()
        print(f"\n{'='*60}")
        print(f"TCP-Serial Bridge Running")
        print(f"{'='*60}")
        print(f"Serial Port: {self.serial_port}")
        print(f"TCP Server:  {addr[0]}:{addr[1]}")
        print(f"Log File:    {self.log_file}")
        print(f"{'='*60}")
        print(f"\nWaiting for connections...")
        print(f"On Windows, use a virtual COM port tool to connect to this IP:port")
        print(f"Then run STcontrol.exe and select the virtual COM port")
        print(f"\nPress Ctrl+C to stop.\n")

        try:
            async with server:
                await server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            if self.serial:
                self.serial.close()
            if self.log_handle:
                self.log_handle.close()


def main():
    parser = argparse.ArgumentParser(
        description="TCP-to-Serial Bridge with Traffic Logging",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
    python3 tcp_serial_bridge.py -p /dev/ttyUSB0 -t 4000 -l capture.log

On Windows:
    1. Install HW Virtual Serial Port (or similar)
    2. Create a virtual COM port connected to <Pi-IP>:4000
    3. Run STcontrol.exe and connect to the virtual COM port
        """
    )

    parser.add_argument('-p', '--port', default='/dev/ttyUSB0',
                        help='Serial port (default: /dev/ttyUSB0)')
    parser.add_argument('-b', '--baud', type=int, default=9600,
                        help='Baud rate (default: 9600)')
    parser.add_argument('-t', '--tcp-port', type=int, default=4000,
                        help='TCP port to listen on (default: 4000)')
    parser.add_argument('-l', '--log', default='tcp_serial_capture.log',
                        help='Log file (default: tcp_serial_capture.log)')

    args = parser.parse_args()

    bridge = TCPSerialBridge(
        serial_port=args.port,
        baudrate=args.baud,
        tcp_port=args.tcp_port,
        log_file=args.log,
    )

    asyncio.run(bridge.run())


if __name__ == '__main__':
    main()
