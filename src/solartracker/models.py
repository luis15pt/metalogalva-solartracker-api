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


class AlarmEntry(BaseModel):
    """One alarm: either currently active, or an entry of the tracker's own alarm log."""
    code: str = Field(..., description="Alarm code, e.g. rotation_encoder")
    message: str = Field("", description="Human-readable message")
    severity: str = Field("fault", description="fault, warning or info")
    timestamp: Optional[datetime] = Field(None, description="Last activation (tracker clock, UTC)")


class WindSettings(BaseModel):
    """Wind protection settings stored in the tracker."""
    trip: int = Field(..., description="Alarm trips above this speed, km/h")
    release: int = Field(..., description="Wind must stay below this to release, km/h")
    hold_minutes: int = Field(..., description="Minutes below release before the alarm clears")
    count: int = Field(1, description="Consecutive samples above trip needed")


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


class ObservedLimits(BaseModel):
    """Observed physical limits of the tracker, tracked over time."""
    horizontal_min: Optional[float] = Field(None, description="Minimum observed horizontal angle")
    horizontal_max: Optional[float] = Field(None, description="Maximum observed horizontal angle")
    vertical_min: Optional[float] = Field(None, description="Minimum observed vertical angle")
    vertical_max: Optional[float] = Field(None, description="Maximum observed vertical angle")
    first_seen: Optional[datetime] = Field(None, description="When tracking started")
    last_updated: Optional[datetime] = Field(None, description="Last time a limit was updated")


class GotoState(BaseModel):
    """Progress of a go-to-angle move."""
    active: bool = False
    phase: str = Field("idle", description="idle, starting, tilt, rotation, done, failed or cancelled")
    target_altitude: Optional[float] = None
    target_azimuth: Optional[float] = None
    message: str = ""


class GotoCommand(BaseModel):
    """Drive the panel to a tilt and/or azimuth (manual mode)."""
    altitude: Optional[float] = Field(None, ge=25, le=90, description="Panel altitude: 90 = flat, 25 = most upright")
    azimuth: Optional[float] = Field(None, ge=0, le=360, description="Panel azimuth, compass degrees")


class TrackerStatus(BaseModel):
    """Full status of the solar tracker."""
    mode: OperatingMode = OperatingMode.MANUAL
    position: TrackerPosition = TrackerPosition()
    sun_position: SunPosition = SunPosition()
    wind_speed: Optional[float] = Field(None, description="Wind speed from the tracker, km/h")
    wind_settings: Optional[WindSettings] = None
    max_wind_threshold: Optional[int] = Field(None, description="Wind trip threshold, km/h")
    alarm_word: int = Field(0, description="Raw 16-bit alarm word")
    alarms: List[str] = Field(default_factory=list, description="Active fault/warning codes")
    limit_switches: List[str] = Field(default_factory=list, description="Active limit switches (informational)")
    active_alarms: List[AlarmEntry] = Field(default_factory=list, description="All active bits with details")
    alarm_history: List[AlarmEntry] = Field(default_factory=list, description="Tracker alarm log, newest first")
    tilt_encoder: Optional[int] = Field(None, description="Actuator encoder pulse counter (low 16 bits)")
    rotation_encoder: Optional[int] = Field(None, description="Rotation encoder pulse counter (low 16 bits)")
    observed_limits: ObservedLimits = ObservedLimits()
    connection: ConnectionStatus = ConnectionStatus()
    utc_time: Optional[datetime] = Field(None, description="Tracker clock (UTC)")
    firmware_version: Optional[str] = Field(None, description="Firmware version string")
    last_frame: Optional[datetime] = Field(None, description="When the last valid status frame arrived (UTC)")
    link_ok: bool = Field(False, description="True while status frames are arriving")
    frames_ok: int = 0
    frames_bad: int = 0
    goto: GotoState = GotoState()


class MoveCommand(BaseModel):
    """Command to move the tracker."""
    direction: Direction
    duration_ms: Optional[int] = Field(None, description="Duration in milliseconds (None = while held)")


class SetWindThresholdCommand(BaseModel):
    """Command to set the wind trip threshold."""
    max_wind: int = Field(..., ge=10, le=99, description="Wind trip threshold, km/h")
    release: Optional[int] = Field(None, ge=5, le=99, description="Release threshold, km/h (default 75% of trip)")


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


class PresetPosition(str, Enum):
    """Stored positions the tracker can drive to (manual mode)."""
    MAINTENANCE = "maintenance"
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
