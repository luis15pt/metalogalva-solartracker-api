"""Configuration settings for the Solar Tracker API."""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Serial port configuration
    serial_port: str = Field(default="/dev/ttyUSB0", description="Serial port device")
    serial_baudrate: int = Field(default=9600, description="Baud rate")
    serial_bytesize: int = Field(default=8, description="Data bits")
    serial_parity: str = Field(default="N", description="Parity: N, E, O, M, S")
    serial_stopbits: float = Field(default=1, description="Stop bits: 1, 1.5, 2")
    serial_timeout: float = Field(default=1.0, description="Read timeout in seconds")

    # MQTT configuration
    mqtt_broker: str = Field(default="mosquitto", description="MQTT broker host")
    mqtt_port: int = Field(default=1883, description="MQTT broker port")
    mqtt_username: Optional[str] = Field(default=None, description="MQTT username")
    mqtt_password: Optional[str] = Field(default=None, description="MQTT password")
    mqtt_topic_prefix: str = Field(default="solartracker", description="MQTT topic prefix")
    mqtt_discovery_prefix: str = Field(default="homeassistant", description="HA discovery prefix")
    mqtt_client_id: str = Field(default="solartracker-api", description="MQTT client ID")

    # API configuration
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")

    # Logging
    log_level: str = Field(default="INFO", description="Log level")

    # Polling intervals (seconds)
    status_poll_interval: float = Field(default=5.0, description="Status polling interval")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
