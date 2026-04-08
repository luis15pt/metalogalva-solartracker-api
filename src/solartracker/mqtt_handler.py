"""MQTT handler for Home Assistant integration."""

import asyncio
import json
import logging
from typing import Optional, Callable, Awaitable
from datetime import datetime

import paho.mqtt.client as mqtt

from .config import settings
from .models import TrackerStatus, OperatingMode, Direction, AlarmType

logger = logging.getLogger(__name__)


class MQTTHandler:
    """Handles MQTT communication for Home Assistant integration."""

    def __init__(self):
        self._client: Optional[mqtt.Client] = None
        self._connected = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Callbacks for command handling
        self._on_move_command: Optional[Callable[[Direction, bool], Awaitable[None]]] = None
        self._on_mode_command: Optional[Callable[[bool], Awaitable[None]]] = None
        self._on_clear_alarms: Optional[Callable[[], Awaitable[None]]] = None
        self._on_set_wind: Optional[Callable[[int], Awaitable[None]]] = None
        self._on_go_home: Optional[Callable[[], Awaitable[None]]] = None
        self._on_go_stow: Optional[Callable[[], Awaitable[None]]] = None
        self._on_set_gps: Optional[Callable[[float, float], Awaitable[None]]] = None
        self._on_sync_datetime: Optional[Callable[[], Awaitable[None]]] = None
        self._on_zero_panel: Optional[Callable[[], Awaitable[None]]] = None

    @property
    def is_connected(self) -> bool:
        """Check if MQTT is connected."""
        return self._connected

    def _topic(self, suffix: str) -> str:
        """Build full topic path."""
        return f"{settings.mqtt_topic_prefix}/{suffix}"

    def _discovery_topic(self, component: str, object_id: str) -> str:
        """Build Home Assistant discovery topic."""
        return f"{settings.mqtt_discovery_prefix}/{component}/{settings.mqtt_topic_prefix}_{object_id}/config"

    async def connect(self) -> bool:
        """Connect to MQTT broker."""
        self._loop = asyncio.get_event_loop()

        try:
            self._client = mqtt.Client(
                client_id=settings.mqtt_client_id,
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            )

            if settings.mqtt_username:
                self._client.username_pw_set(
                    settings.mqtt_username,
                    settings.mqtt_password,
                )

            # Set up callbacks
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.on_message = self._on_message

            # Set last will (availability)
            self._client.will_set(
                self._topic("availability"),
                payload="offline",
                qos=1,
                retain=True,
            )

            # Connect
            self._client.connect_async(
                settings.mqtt_broker,
                settings.mqtt_port,
            )
            self._client.loop_start()

            # Wait for connection
            for _ in range(50):  # 5 second timeout
                if self._connected:
                    return True
                await asyncio.sleep(0.1)

            logger.error("MQTT connection timeout")
            return False

        except Exception as e:
            logger.error(f"MQTT connection failed: {e}")
            return False

    async def disconnect(self):
        """Disconnect from MQTT broker."""
        if self._client:
            # Publish offline status
            self._client.publish(
                self._topic("availability"),
                payload="offline",
                qos=1,
                retain=True,
            )
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """Handle MQTT connection."""
        if reason_code == 0:
            logger.info("Connected to MQTT broker")
            self._connected = True

            # Subscribe to command topics
            command_topics = [
                (self._topic("command/move"), 1),
                (self._topic("command/mode"), 1),
                (self._topic("command/clear_alarms"), 1),
                (self._topic("command/set_wind"), 1),
                (self._topic("command/go_home"), 1),
                (self._topic("command/go_stow"), 1),
                (self._topic("command/set_gps"), 1),
                (self._topic("command/sync_datetime"), 1),
                (self._topic("command/zero_panel"), 1),
            ]
            client.subscribe(command_topics)

            # Publish online status
            client.publish(
                self._topic("availability"),
                payload="online",
                qos=1,
                retain=True,
            )

            # Publish Home Assistant discovery
            asyncio.run_coroutine_threadsafe(
                self._publish_discovery(),
                self._loop,
            )
        else:
            logger.error(f"MQTT connection failed: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        """Handle MQTT disconnection."""
        logger.warning(f"Disconnected from MQTT broker: {reason_code}")
        self._connected = False

    def _on_message(self, client, userdata, message):
        """Handle incoming MQTT messages."""
        topic = message.topic
        payload = message.payload.decode("utf-8")

        logger.debug(f"MQTT received: {topic} = {payload}")

        # Handle commands asynchronously
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._handle_command(topic, payload),
                self._loop,
            )

    async def _handle_command(self, topic: str, payload: str):
        """Process incoming command."""
        try:
            if topic == self._topic("command/move"):
                data = json.loads(payload)
                direction = Direction(data.get("direction"))
                start = data.get("start", True)
                if self._on_move_command:
                    await self._on_move_command(direction, start)
        except Exception as e:
            logger.error(f"Error handling MQTT command on {topic}: {e}")

        try:
            if topic == self._topic("command/mode"):
                automatic = payload.lower() in ("auto", "automatic", "true", "1")
                if self._on_mode_command:
                    await self._on_mode_command(automatic)
        except Exception as e:
            logger.error(f"Error handling MQTT command on {topic}: {e}")

        try:
            if topic == self._topic("command/clear_alarms"):
                if self._on_clear_alarms:
                    await self._on_clear_alarms()
        except Exception as e:
            logger.error(f"Error handling MQTT command on {topic}: {e}")

        try:
            if topic == self._topic("command/set_wind"):
                value = int(payload)
                if self._on_set_wind:
                    await self._on_set_wind(value)
        except Exception as e:
            logger.error(f"Error handling MQTT command on {topic}: {e}")

        try:
            if topic == self._topic("command/go_home"):
                if self._on_go_home:
                    await self._on_go_home()
        except Exception as e:
            logger.error(f"Error handling MQTT command on {topic}: {e}")

        try:
            if topic == self._topic("command/go_stow"):
                if self._on_go_stow:
                    await self._on_go_stow()
        except Exception as e:
            logger.error(f"Error handling MQTT command on {topic}: {e}")

        try:
            if topic == self._topic("command/set_gps"):
                data = json.loads(payload)
                lat = float(data.get("latitude"))
                lon = float(data.get("longitude"))
                if self._on_set_gps:
                    await self._on_set_gps(lat, lon)
        except Exception as e:
            logger.error(f"Error handling MQTT command on {topic}: {e}")

        try:
            if topic == self._topic("command/sync_datetime"):
                if self._on_sync_datetime:
                    await self._on_sync_datetime()
        except Exception as e:
            logger.error(f"Error handling MQTT command on {topic}: {e}")

        try:
            if topic == self._topic("command/zero_panel"):
                if self._on_zero_panel:
                    await self._on_zero_panel()
        except Exception as e:
            logger.error(f"Error handling MQTT command on {topic}: {e}")

    def set_callbacks(
        self,
        on_move: Optional[Callable[[Direction, bool], Awaitable[None]]] = None,
        on_mode: Optional[Callable[[bool], Awaitable[None]]] = None,
        on_clear_alarms: Optional[Callable[[], Awaitable[None]]] = None,
        on_set_wind: Optional[Callable[[int], Awaitable[None]]] = None,
        on_go_home: Optional[Callable[[], Awaitable[None]]] = None,
        on_go_stow: Optional[Callable[[], Awaitable[None]]] = None,
        on_set_gps: Optional[Callable[[float, float], Awaitable[None]]] = None,
        on_sync_datetime: Optional[Callable[[], Awaitable[None]]] = None,
        on_zero_panel: Optional[Callable[[], Awaitable[None]]] = None,
    ):
        """Set command callbacks."""
        self._on_move_command = on_move
        self._on_mode_command = on_mode
        self._on_clear_alarms = on_clear_alarms
        self._on_set_wind = on_set_wind
        self._on_go_home = on_go_home
        self._on_go_stow = on_go_stow
        self._on_set_gps = on_set_gps
        self._on_sync_datetime = on_sync_datetime
        self._on_zero_panel = on_zero_panel

    async def publish_status(self, status: TrackerStatus):
        """Publish tracker status to MQTT."""
        if not self._connected:
            return

        # Publish individual state topics
        self._client.publish(
            self._topic("state/mode"),
            payload=status.mode.value,
            qos=0,
            retain=True,
        )

        self._client.publish(
            self._topic("state/connected"),
            payload="ON" if status.connection.connected else "OFF",
            qos=0,
            retain=True,
        )

        if status.position.horizontal is not None:
            self._client.publish(
                self._topic("state/position/horizontal"),
                payload=str(status.position.horizontal),
                qos=0,
                retain=True,
            )

        if status.position.vertical is not None:
            self._client.publish(
                self._topic("state/position/vertical"),
                payload=str(status.position.vertical),
                qos=0,
                retain=True,
            )

        if status.wind_speed is not None:
            self._client.publish(
                self._topic("state/wind_speed"),
                payload=str(status.wind_speed),
                qos=0,
                retain=True,
            )

        if status.max_wind_threshold is not None:
            self._client.publish(
                self._topic("state/max_wind"),
                payload=str(status.max_wind_threshold),
                qos=0,
                retain=True,
            )

        # Publish alarms as JSON array
        # Handle both AlarmType enums and raw strings
        alarms = []
        for alarm in status.alarms:
            if hasattr(alarm, 'value'):
                alarms.append(alarm.value)
            else:
                alarms.append(str(alarm))
        self._client.publish(
            self._topic("state/alarms"),
            payload=json.dumps(alarms),
            qos=0,
            retain=True,
        )

        # Publish alarm active as binary
        self._client.publish(
            self._topic("state/alarm_active"),
            payload="ON" if status.alarms else "OFF",
            qos=0,
            retain=True,
        )

        # Full status as JSON
        self._client.publish(
            self._topic("state/full"),
            payload=status.model_dump_json(),
            qos=0,
            retain=True,
        )

    async def _publish_discovery(self):
        """Publish Home Assistant MQTT discovery messages."""
        if not self._connected:
            return

        device_info = {
            "identifiers": ["solartracker_01"],
            "name": "Solar Tracker",
            "model": "STcontrol V4",
            "manufacturer": "Solar Tracker",
            "sw_version": "0.1.0",
        }

        availability = {
            "topic": self._topic("availability"),
            "payload_available": "online",
            "payload_not_available": "offline",
        }

        # Binary sensor: Connected
        self._publish_discovery_config("binary_sensor", "connected", {
            "name": "Connected",
            "device_class": "connectivity",
            "state_topic": self._topic("state/connected"),
            "payload_on": "ON",
            "payload_off": "OFF",
            "device": device_info,
            "availability": availability,
            "unique_id": "solartracker_connected",
        })

        # Binary sensor: Alarm Active
        self._publish_discovery_config("binary_sensor", "alarm", {
            "name": "Alarm Active",
            "device_class": "problem",
            "state_topic": self._topic("state/alarm_active"),
            "payload_on": "ON",
            "payload_off": "OFF",
            "device": device_info,
            "availability": availability,
            "unique_id": "solartracker_alarm",
        })

        # Sensor: Mode
        self._publish_discovery_config("sensor", "mode", {
            "name": "Operating Mode",
            "state_topic": self._topic("state/mode"),
            "device": device_info,
            "availability": availability,
            "unique_id": "solartracker_mode",
            "icon": "mdi:auto-fix",
        })

        # Sensor: Horizontal Position
        self._publish_discovery_config("sensor", "position_h", {
            "name": "Horizontal Position",
            "state_topic": self._topic("state/position/horizontal"),
            "unit_of_measurement": "\u00b0",
            "device": device_info,
            "availability": availability,
            "unique_id": "solartracker_position_h",
            "icon": "mdi:compass",
        })

        # Sensor: Vertical Position
        self._publish_discovery_config("sensor", "position_v", {
            "name": "Vertical Position",
            "state_topic": self._topic("state/position/vertical"),
            "unit_of_measurement": "\u00b0",
            "device": device_info,
            "availability": availability,
            "unique_id": "solartracker_position_v",
            "icon": "mdi:angle-acute",
        })

        # Sensor: Wind Speed
        self._publish_discovery_config("sensor", "wind", {
            "name": "Wind Speed",
            "state_topic": self._topic("state/wind_speed"),
            "unit_of_measurement": "km/h",
            "device_class": "wind_speed",
            "device": device_info,
            "availability": availability,
            "unique_id": "solartracker_wind",
        })

        # Number: Max Wind Threshold
        self._publish_discovery_config("number", "max_wind", {
            "name": "Max Wind Threshold",
            "state_topic": self._topic("state/max_wind"),
            "command_topic": self._topic("command/set_wind"),
            "min": 0,
            "max": 99,
            "step": 1,
            "unit_of_measurement": "km/h",
            "device": device_info,
            "availability": availability,
            "unique_id": "solartracker_max_wind",
            "icon": "mdi:weather-windy",
        })

        # Select: Mode
        self._publish_discovery_config("select", "mode_select", {
            "name": "Mode",
            "state_topic": self._topic("state/mode"),
            "command_topic": self._topic("command/mode"),
            "options": ["manual", "automatic"],
            "device": device_info,
            "availability": availability,
            "unique_id": "solartracker_mode_select",
            "icon": "mdi:cog",
        })

        # Button: Clear Alarms
        self._publish_discovery_config("button", "clear_alarms", {
            "name": "Clear Alarms",
            "command_topic": self._topic("command/clear_alarms"),
            "payload_press": "clear",
            "device": device_info,
            "availability": availability,
            "unique_id": "solartracker_clear_alarms",
            "icon": "mdi:bell-off",
        })

        # Buttons for movement
        for direction in ["up", "down", "left", "right"]:
            icons = {"up": "mdi:arrow-up", "down": "mdi:arrow-down",
                     "left": "mdi:arrow-left", "right": "mdi:arrow-right"}
            self._publish_discovery_config("button", f"move_{direction}", {
                "name": f"Move {direction.title()}",
                "command_topic": self._topic("command/move"),
                "payload_press": json.dumps({"direction": direction, "start": True}),
                "device": device_info,
                "availability": availability,
                "unique_id": f"solartracker_move_{direction}",
                "icon": icons[direction],
            })

        # Button: Go Home
        self._publish_discovery_config("button", "go_home", {
            "name": "Go Home",
            "command_topic": self._topic("command/go_home"),
            "payload_press": "home",
            "device": device_info,
            "availability": availability,
            "unique_id": "solartracker_go_home",
            "icon": "mdi:home",
        })

        # Button: Go Stow
        self._publish_discovery_config("button", "go_stow", {
            "name": "Stow (Safe Position)",
            "command_topic": self._topic("command/go_stow"),
            "payload_press": "stow",
            "device": device_info,
            "availability": availability,
            "unique_id": "solartracker_go_stow",
            "icon": "mdi:shield-home",
        })

        # Button: Sync DateTime
        self._publish_discovery_config("button", "sync_datetime", {
            "name": "Sync Clock",
            "command_topic": self._topic("command/sync_datetime"),
            "payload_press": "sync",
            "device": device_info,
            "availability": availability,
            "unique_id": "solartracker_sync_datetime",
            "icon": "mdi:clock-sync",
        })

        # Button: Zero Panel
        self._publish_discovery_config("button", "zero_panel", {
            "name": "Zero Panel Position",
            "command_topic": self._topic("command/zero_panel"),
            "payload_press": "zero",
            "device": device_info,
            "availability": availability,
            "unique_id": "solartracker_zero_panel",
            "icon": "mdi:numeric-0-box",
        })

        logger.info("Published Home Assistant discovery config")

    def _publish_discovery_config(self, component: str, object_id: str, config: dict):
        """Publish a single discovery config."""
        topic = self._discovery_topic(component, object_id)
        self._client.publish(
            topic,
            payload=json.dumps(config),
            qos=1,
            retain=True,
        )


# Global MQTT handler instance
mqtt_handler = MQTTHandler()
