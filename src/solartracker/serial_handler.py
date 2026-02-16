"""Serial communication handler for the Solar Tracker."""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Callable, Awaitable
from contextlib import asynccontextmanager

import serial
from serial.tools import list_ports

from .config import settings
from .protocol import SolarTrackerProtocol, Direction as ProtoDirection
from .models import ConnectionStatus, TrackerStatus, Direction

logger = logging.getLogger(__name__)


class SerialHandler:
    """Handles serial communication with the solar tracker."""

    def __init__(self):
        self._serial: Optional[serial.Serial] = None
        self._connected = False
        self._last_rx: Optional[datetime] = None
        self._last_tx: Optional[datetime] = None
        self._read_task: Optional[asyncio.Task] = None
        self._on_data_received: Optional[Callable[[bytes], Awaitable[None]]] = None
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Check if serial port is connected."""
        return self._connected and self._serial is not None and self._serial.is_open

    def get_status(self) -> ConnectionStatus:
        """Get current connection status."""
        return ConnectionStatus(
            connected=self.is_connected,
            port=settings.serial_port if self.is_connected else "",
            baudrate=settings.serial_baudrate if self.is_connected else 0,
            last_rx=self._last_rx,
            last_tx=self._last_tx,
        )

    @staticmethod
    def list_ports() -> list[dict]:
        """List available serial ports."""
        ports = []
        for port in list_ports.comports():
            ports.append({
                "device": port.device,
                "description": port.description,
                "hwid": port.hwid,
            })
        return ports

    async def connect(
        self,
        port: Optional[str] = None,
        baudrate: Optional[int] = None,
    ) -> bool:
        """
        Connect to the serial port.

        Args:
            port: Serial port device (default from settings)
            baudrate: Baud rate (default from settings)

        Returns:
            True if connection successful
        """
        async with self._lock:
            if self.is_connected:
                logger.warning("Already connected, disconnecting first")
                await self._disconnect_internal()

            port = port or settings.serial_port
            baudrate = baudrate or settings.serial_baudrate

            try:
                self._serial = serial.Serial(
                    port=port,
                    baudrate=baudrate,
                    bytesize=settings.serial_bytesize,
                    parity=settings.serial_parity,
                    stopbits=settings.serial_stopbits,
                    timeout=settings.serial_timeout,
                )
                self._connected = True
                logger.info(f"Connected to {port} at {baudrate} baud")

                # Start background read task
                self._read_task = asyncio.create_task(self._read_loop())

                return True

            except serial.SerialException as e:
                logger.error(f"Failed to connect to {port}: {e}")
                self._connected = False
                return False

    async def disconnect(self) -> bool:
        """Disconnect from the serial port."""
        async with self._lock:
            return await self._disconnect_internal()

    async def _disconnect_internal(self) -> bool:
        """Internal disconnect (must hold lock)."""
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
            self._read_task = None

        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("Disconnected from serial port")

        self._serial = None
        self._connected = False
        return True

    def set_data_callback(self, callback: Callable[[bytes], Awaitable[None]]):
        """Set callback for received data."""
        self._on_data_received = callback

    async def send(self, data: bytes) -> bool:
        """
        Send raw bytes to the serial port with RS-485 RTS toggling.

        The tracker uses RS-485 half-duplex protocol which requires:
        - RTS HIGH during transmit
        - RTS LOW during receive

        Args:
            data: Bytes to send

        Returns:
            True if send successful
        """
        if not self.is_connected:
            logger.error("Cannot send: not connected")
            return False

        try:
            async with self._lock:
                # RS-485: Set RTS high for transmit mode
                self._serial.rts = True
                await asyncio.sleep(0.002)  # Small delay for line to settle

                self._serial.write(data)
                self._serial.flush()

                # Wait for transmission to complete
                # At 9600 baud, each byte takes ~1.04ms (10 bits/byte)
                tx_time = len(data) * 10 / 9600 + 0.01
                await asyncio.sleep(tx_time)

                # RS-485: Set RTS low for receive mode
                self._serial.rts = False

                self._last_tx = datetime.now()
                logger.debug(f"TX: {data.hex()}")
                return True
        except serial.SerialException as e:
            logger.error(f"Send failed: {e}")
            return False

    async def move(self, direction: Direction, start: bool = True) -> bool:
        """
        Start or stop movement in a direction.

        Args:
            direction: Direction to move
            start: True to start moving, False to stop

        Returns:
            True if command sent successfully
        """
        direction_map = {
            Direction.UP: ProtoDirection.UP,
            Direction.DOWN: ProtoDirection.DOWN,
            Direction.LEFT: ProtoDirection.LEFT,
            Direction.RIGHT: ProtoDirection.RIGHT,
        }
        proto_dir = direction_map.get(direction, ProtoDirection.STOP)
        packet = SolarTrackerProtocol.build_movement_command(proto_dir, start)
        return await self.send(packet)

    async def stop(self) -> bool:
        """Stop all movement."""
        packet = SolarTrackerProtocol.build_stop_command()
        return await self.send(packet)

    async def set_mode(self, automatic: bool) -> bool:
        """Set operating mode."""
        # TODO: Not yet reverse-engineered
        packet = SolarTrackerProtocol.set_auto_mode() if automatic else SolarTrackerProtocol.set_manual_mode()
        if packet is None:
            logger.warning("Set mode command not yet implemented in protocol")
            return False
        return await self.send(packet)

    async def clear_alarms(self) -> bool:
        """Clear all alarms."""
        packet = SolarTrackerProtocol.build_clear_alarms()
        return await self.send(packet)

    async def request_status(self) -> bool:
        """Request status update from tracker."""
        packet = SolarTrackerProtocol.build_status_request()
        return await self.send(packet)

    async def set_max_wind(self, value: int) -> bool:
        """Set maximum wind threshold."""
        # TODO: Not yet reverse-engineered
        packet = SolarTrackerProtocol.set_max_wind(value)
        if packet is None:
            logger.warning("Set max wind command not yet implemented in protocol")
            return False
        return await self.send(packet)

    async def set_gps_location(self, latitude: float, longitude: float) -> bool:
        """
        Set tracker GPS location for sun position calculations.

        Args:
            latitude: Latitude in decimal degrees (e.g., 40.5440)
            longitude: Longitude in decimal degrees (e.g., -8.6988)

        Returns:
            True if command sent successfully
        """
        packet = SolarTrackerProtocol.set_gps_location(latitude, longitude)
        return await self.send(packet)

    async def set_datetime(self, year: int, month: int, day: int,
                           hour: int, minute: int, second: int) -> bool:
        """
        Set tracker internal clock.

        Args:
            year: Full year (2000-2255)
            month: Month (1-12)
            day: Day (1-31)
            hour: Hour (0-23)
            minute: Minute (0-59)
            second: Second (0-59)

        Returns:
            True if command sent successfully
        """
        try:
            packet = SolarTrackerProtocol.set_datetime(year, month, day, hour, minute, second)
            return await self.send(packet)
        except ValueError as e:
            logger.error(f"Invalid datetime: {e}")
            return False

    async def go_to_position(self, position: int) -> bool:
        """
        Go to a preset position.

        Args:
            position: Preset number (1, 2, or 3)
                - 1: Unknown preset
                - 2: Possibly HOME position
                - 3: Possibly STOW position

        Returns:
            True if command sent successfully
        """
        try:
            packet = SolarTrackerProtocol.go_to_position(position)
            return await self.send(packet)
        except ValueError as e:
            logger.error(f"Invalid position: {e}")
            return False

    async def go_home(self) -> bool:
        """Move panel to HOME position (preset 2)."""
        return await self.go_to_position(2)

    async def go_stow(self) -> bool:
        """Move panel to STOW position (preset 3)."""
        return await self.go_to_position(3)

    async def zero_panel(self) -> bool:
        """Reset panel position encoders to zero."""
        packet = SolarTrackerProtocol.zero_panel()
        return await self.send(packet)

    async def query_alarms(self) -> bool:
        """Query detailed alarm status."""
        packet = SolarTrackerProtocol.query_alarms()
        return await self.send(packet)

    async def _read_loop(self):
        """Background task to read serial data."""
        logger.info("Starting serial read loop")
        buffer = bytearray()

        while self.is_connected:
            try:
                if self._serial.in_waiting > 0:
                    data = self._serial.read(self._serial.in_waiting)
                    self._last_rx = datetime.now()
                    buffer.extend(data)
                    logger.debug(f"RX: {data.hex()}")

                    # Process complete messages from buffer
                    # TODO: Implement proper message framing based on protocol
                    if buffer:
                        if self._on_data_received:
                            await self._on_data_received(bytes(buffer))
                        buffer.clear()

                await asyncio.sleep(0.01)  # Small delay to prevent busy loop

            except serial.SerialException as e:
                logger.error(f"Serial read error: {e}")
                break
            except asyncio.CancelledError:
                logger.info("Serial read loop cancelled")
                break

        logger.info("Serial read loop ended")


# Global serial handler instance
serial_handler = SerialHandler()
