"""Pydantic models for the Solar Tracker API."""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime


class OperatingMode(str, Enum):
    """Operating mode of the solar tracker."""
    MANUAL = "manual"
    AUTOMATIC = "automatic"


class Direction(str, Enum):
    """Movement direction."""
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


class AlarmType(str, Enum):
    """Types of alarms (matching STcontrol terminology)."""
    VERTICAL_LIMIT = "vertical_limit"      # Bit 0 - fim de curso vertical
    TILT_LIMIT_FLAT = "tilt_limit_flat"    # Bit 1 - fim de curso horizontal (panel flat/stowed)
    WEST_LIMIT = "west_limit"              # Bit 2
    WIND_SPEED = "wind_speed"              # Bit 3 - limite de vento excedido
    ACTUATOR_CURRENT = "actuator_current"  # Bit 4
    ROTATION_CURRENT = "rotation_current"  # Bit 5
    UNKNOWN_6 = "unknown_alarm_6"          # Bit 6 - unknown
    ENCODER_ERROR = "encoder_error"        # Bit 7


class AlarmEntry(BaseModel):
    """Alarm history entry with timestamp."""
    alarm_type: str = Field(..., description="Alarm type code")
    timestamp: datetime = Field(..., description="When the alarm was triggered")
    message: str = Field("", description="Human-readable alarm message")


class ConnectionStatus(BaseModel):
    """Serial connection status."""
    connected: bool = False
    port: str = ""
    baudrate: int = 0
    last_rx: Optional[datetime] = None
    last_tx: Optional[datetime] = None


class TrackerPosition(BaseModel):
    """Current position of the solar tracker."""
    horizontal: Optional[float] = Field(None, description="Horizontal/Azimuth angle in degrees")
    vertical: Optional[float] = Field(None, description="Vertical/Altitude angle in degrees")


class SunPosition(BaseModel):
    """Calculated sun position."""
    azimuth: Optional[float] = Field(None, description="Sun azimuth angle in degrees")
    altitude: Optional[float] = Field(None, description="Sun altitude angle in degrees")


class TrackerLimits(BaseModel):
    """Configured limits for the solar tracker."""
    east_limit: Optional[int] = Field(None, description="East limit angle")
    west_limit: Optional[int] = Field(None, description="West limit angle")
    min_altitude_sunrise: Optional[float] = Field(None, description="Min altitude at sunrise")
    min_altitude_sunset: Optional[float] = Field(None, description="Min altitude at sunset")


class ObservedLimits(BaseModel):
    """Observed physical limits of the tracker, tracked over time."""
    horizontal_min: Optional[float] = Field(None, description="Minimum observed horizontal angle")
    horizontal_max: Optional[float] = Field(None, description="Maximum observed horizontal angle")
    vertical_min: Optional[float] = Field(None, description="Minimum observed vertical angle")
    vertical_max: Optional[float] = Field(None, description="Maximum observed vertical angle")
    first_seen: Optional[datetime] = Field(None, description="When tracking started")
    last_updated: Optional[datetime] = Field(None, description="Last time a limit was updated")


class TrackerStatus(BaseModel):
    """Full status of the solar tracker."""
    mode: OperatingMode = OperatingMode.MANUAL
    position: TrackerPosition = TrackerPosition()
    sun_position: SunPosition = SunPosition()
    limits: TrackerLimits = TrackerLimits()
    wind_speed: Optional[float] = Field(None, description="Current wind speed")
    max_wind_threshold: Optional[int] = Field(None, description="Max wind threshold")
    alarms: List[str] = Field(default_factory=list, description="Current active alarms")
    alarm_history: List[AlarmEntry] = Field(default_factory=list, description="Alarm history log")
    observed_limits: ObservedLimits = ObservedLimits()
    connection: ConnectionStatus = ConnectionStatus()
    utc_time: Optional[datetime] = None
    firmware_version: Optional[str] = Field(None, description="Firmware version string")


class MoveCommand(BaseModel):
    """Command to move the tracker."""
    direction: Direction
    duration_ms: Optional[int] = Field(None, description="Duration in milliseconds (None = while held)")


class SetLimitsCommand(BaseModel):
    """Command to set tracker limits."""
    east_limit: Optional[int] = Field(None, ge=0, le=99)
    west_limit: Optional[int] = Field(None, ge=0, le=99)


class SetWindThresholdCommand(BaseModel):
    """Command to set max wind threshold."""
    max_wind: int = Field(..., ge=0, le=99, description="Max wind speed threshold")


class CommandResponse(BaseModel):
    """Generic command response."""
    success: bool
    message: str
    data: Optional[dict] = None


class SetGPSLocationCommand(BaseModel):
    """Command to set GPS location for sun calculations."""
    latitude: float = Field(..., ge=-90, le=90, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude in decimal degrees")


class SetDateTimeCommand(BaseModel):
    """Command to set tracker internal clock."""
    year: int = Field(..., ge=2000, le=2255, description="Full year (2000-2255)")
    month: int = Field(..., ge=1, le=12, description="Month (1-12)")
    day: int = Field(..., ge=1, le=31, description="Day (1-31)")
    hour: int = Field(..., ge=0, le=23, description="Hour (0-23)")
    minute: int = Field(..., ge=0, le=59, description="Minute (0-59)")
    second: int = Field(..., ge=0, le=59, description="Second (0-59)")


class PresetPosition(int, Enum):
    """Preset position numbers."""
    POSITION_1 = 1
    HOME = 2
    STOW = 3
