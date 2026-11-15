"""Serial communication handler for the Solar Tracker."""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Callable, Awaitable
from contextlib import asynccontextmanager

import serial
from serial.tools import list_ports

from .config import settings
from . import protocol
from .protocol import Cmd
from .models import ConnectionStatus, Direction, PresetPosition

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
                self._set_rts(False)  # receive state
                self._connected = True
                logger.info(f"Connected to {port} at {baudrate} baud")

                # Start background read task
                self._read_task = asyncio.create_task(self._read_loop())

                return True

            except (OSError, serial.SerialException) as e:
                logger.error(f"Failed to connect to {port}: {e}")
                self._serial = None
                self._connected = False
                return False

    async def disconnect(self) -> bool:
        """Disconnect from the serial port."""
        async with self._lock:
            return await self._disconnect_internal()

    async def _disconnect_internal(self) -> bool:
        """Internal disconnect (must hold lock)."""
        if self._read_task and self._read_task is not asyncio.current_task():
            self._read_task.cancel()
            try:
                await self._read_task
            except (asyncio.CancelledError, Exception):
                pass
            self._read_task = None

        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("Disconnected from serial port")

        self._serial = None
        self._connected = False
        return True

    def _set_rts(self, level: bool):
        """Drive RTS for half-duplex adapters; ports without modem lines are fine."""
        try:
            self._serial.rts = level
        except OSError:
            pass

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
                self._set_rts(True)
                await asyncio.sleep(0.002)  # Small delay for line to settle

                self._serial.write(data)
                self._serial.flush()

                # Wait for transmission to complete
                # At 9600 baud, each byte takes ~1.04ms (10 bits/byte)
                tx_time = len(data) * 10 / 9600 + 0.01
                await asyncio.sleep(tx_time)

                # RS-485: Set RTS low for receive mode
                self._set_rts(False)

                self._last_tx = datetime.now()
                logger.info(f"TX [{len(data)} bytes]: {data.hex()}")
                return True
        except (OSError, serial.SerialException) as e:
            logger.error(f"Send failed: {e}")
            return False

    async def move(self, direction: Direction, start: bool = True) -> bool:
        """Start moving in a direction, or stop. Only acted on in manual mode."""
        cmd = {
            Direction.UP: Cmd.MOVE_UP,
            Direction.DOWN: Cmd.MOVE_DOWN,
            Direction.LEFT: Cmd.MOVE_WEST,
            Direction.RIGHT: Cmd.MOVE_EAST,
        }[direction] if start else Cmd.MOVE_STOP
        return await self.send(protocol.move(cmd))

    async def stop(self) -> bool:
        """Stop all movement."""
        return await self.send(protocol.stop())

    async def set_mode(self, automatic: bool) -> bool:
        """Set operating mode (rewrites the tracker's flash)."""
        return await self.send(protocol.set_mode(automatic))

    async def clear_alarms(self) -> bool:
        """Clear alarms and the tracker's alarm log."""
        return await self.send(protocol.clear_alarms())

    async def read_wind_settings(self) -> bool:
        return await self.send(protocol.read_wind_settings())

    async def write_wind_settings(self, trip: int, release: int, hold_minutes: int, count: int) -> bool:
        return await self.send(protocol.write_wind_settings(trip, release, hold_minutes, count))

    async def set_gps_location(self, latitude: float, longitude: float) -> bool:
        return await self.send(protocol.set_location(latitude, longitude))

    async def set_datetime(self, when: datetime) -> bool:
        """Set the tracker clock (UTC)."""
        return await self.send(protocol.set_clock(when))

    async def go_to_position(self, position: PresetPosition) -> bool:
        """Drive to a stored position. Only acted on in manual mode."""
        cmd = {
            PresetPosition.MAINTENANCE: Cmd.GOTO_MAINTENANCE,
            PresetPosition.HORIZONTAL: Cmd.GOTO_HORIZONTAL,
            PresetPosition.VERTICAL: Cmd.GOTO_VERTICAL,
        }[position]
        return await self.send(protocol.goto(cmd))

    async def zero_panel(self) -> bool:
        """ZERAR PAINEL: start the homing routine. The tracker will move."""
        return await self.send(protocol.zero_panel())

    async def _read_loop(self):
        """Background task: read bytes and hand them to the callback."""
        logger.info("Starting serial read loop")
        ser = self._serial
        while self._connected and ser is not None and ser.is_open:
            try:
                waiting = ser.in_waiting
                if waiting:
                    data = ser.read(waiting)
                    self._last_rx = datetime.now()
                    if self._on_data_received:
                        try:
                            await self._on_data_received(data)
                        except Exception:
                            logger.exception("Error in serial data callback")
                await asyncio.sleep(0.02)
            except asyncio.CancelledError:
                logger.info("Serial read loop cancelled")
                raise
            except (OSError, serial.SerialException) as e:
                # Device unplugged or re-enumerated: drop the port so the
                # housekeeping loop can reconnect instead of spinning here.
                logger.error(f"Serial port lost: {e}")
                self._connected = False
                try:
                    ser.close()
                except Exception:
                    pass
                self._serial = None
                break
        logger.info("Serial read loop ended")


# Global serial handler instance
serial_handler = SerialHandler()
