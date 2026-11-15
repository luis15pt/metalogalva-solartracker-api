"""Drive the panel to a chosen tilt and azimuth using manual jog commands.

The firmware has no "go to angle" command, so this closes the loop on the Pi:
start a jog, watch the once-per-second status frames, stop when the target is
reached. Every exit path sends a stop command.

A jog command ramps the firmware's internal target position rather than
switching the motor directly, so pulses shorter than about a second do nothing
or act late. Only continuous runs are used here; expect about 1 degree accuracy.
"""

import asyncio
import logging
from typing import Callable, Optional

from .models import Direction, GotoState, OperatingMode, TrackerStatus

logger = logging.getLogger(__name__)

START_ABOVE = 0.5      # degrees: do nothing for smaller moves
CORRECT_ABOVE = 1.0    # degrees: only re-run if the first run missed by more than this
FAIL_ABOVE = 2.0       # degrees: report failure beyond this
LEAD_SECONDS = 1.3     # stop this early: status lag plus the tracker's stop latency
FRAME_TIMEOUT = 4.0    # seconds without a status frame = link lost
STALL_FRAMES = 5       # status frames without movement = not moving
AXIS_TIMEOUT = 900     # seconds per axis
DEFAULT_RATE = 0.7     # degrees per second, measured on the tilt axis


class GotoError(Exception):
    pass


class _Axis:
    def __init__(self, name, target, read, toward_higher, toward_lower, limit_higher, limit_lower, fault):
        self.name = name
        self.target = target
        self.read = read
        self.dirs = {1: toward_higher, -1: toward_lower}
        self.limits = {1: limit_higher, -1: limit_lower}
        self.fault = fault


class GotoController:
    def __init__(self, serial, get_status: Callable[[], TrackerStatus], on_change: Callable):
        self._serial = serial
        self._status = get_status
        self._on_change = on_change
        self._task: Optional[asyncio.Task] = None
        self._frame = asyncio.Event()
        self.state = GotoState()

    @property
    def active(self) -> bool:
        return self._task is not None and not self._task.done()

    def notify_frame(self):
        """Call on every decoded status frame."""
        self._frame.set()

    def start(self, altitude: Optional[float], azimuth: Optional[float]):
        if self.active:
            raise GotoError("A move is already running")
        self.state = GotoState(active=True, phase="starting", target_altitude=altitude,
                               target_azimuth=azimuth, message="Starting")
        self._task = asyncio.create_task(self._run(altitude, azimuth))

    async def cancel(self, reason: str = "Stopped"):
        """Abort a running move. The caller is expected to send its own command next."""
        if self.active:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            await self._finish("cancelled", reason)

    async def _set(self, phase: str, message: str):
        self.state.phase = phase
        self.state.message = message
        await self._on_change()

    async def _finish(self, phase: str, message: str):
        self.state.active = False
        logger.info(f"GOTO {phase}: {message}")
        await self._set(phase, message)

    async def _run(self, altitude, azimuth):
        s = self._status
        axes = []
        if altitude is not None:
            # Jog "down" lowers the altitude number (more upright); "up" goes toward flat (90)
            axes.append(_Axis("tilt", altitude, lambda: s().position.vertical,
                              Direction.UP, Direction.DOWN, "horizontal_limit", "vertical_limit",
                              "actuator_encoder"))
        if azimuth is not None:
            # East = lower azimuth. Not yet confirmed on the real tracker; a wrong guess aborts safely.
            axes.append(_Axis("rotation", azimuth, lambda: s().position.horizontal,
                              Direction.LEFT, Direction.RIGHT, "west_limit", "east_limit",
                              "rotation_encoder"))
        try:
            notes = []
            for axis in axes:
                notes.append(await self._drive(axis))
            await self._finish("done", "; ".join(notes))
        except GotoError as e:
            await self._serial.stop()
            await self._finish("failed", str(e))
        except asyncio.CancelledError:
            await self._serial.stop()
            raise
        except Exception as e:  # never leave a motor running
            logger.exception("GOTO crashed")
            await self._serial.stop()
            await self._finish("failed", f"Internal error: {e}")

    async def _next_frame(self):
        self._frame.clear()
        try:
            await asyncio.wait_for(self._frame.wait(), FRAME_TIMEOUT)
        except asyncio.TimeoutError:
            raise GotoError("Lost the tracker link")
        st = self._status()
        if st.mode != OperatingMode.MANUAL:
            raise GotoError("Tracker left manual mode")

    def _check_faults(self, baseline: set):
        new = set(self._status().alarms) - baseline
        if new:
            raise GotoError("Tracker raised an alarm: " + ", ".join(sorted(new)))

    async def _drive(self, axis: _Axis) -> str:
        st = self._status()
        if axis.fault in st.alarms:
            raise GotoError(f"{axis.name}: encoder alarm is active, clear alarms first")
        if axis.read() is None:
            raise GotoError(f"{axis.name}: position unknown")
        baseline = set(st.alarms)
        rate = DEFAULT_RATE
        loop = asyncio.get_running_loop()

        for attempt in range(3):
            err = axis.target - axis.read()
            if abs(err) <= (START_ABOVE if attempt == 0 else CORRECT_ABOVE):
                break
            sign = 1 if err > 0 else -1
            if axis.limits[sign] in self._status().limit_switches:
                return f"{axis.name} stopped at its limit switch ({axis.read():.1f}°)"
            await self._set(axis.name, f"Moving {axis.name} to {axis.target:.1f}°")

            await self._serial.move(axis.dirs[sign], start=True)
            deadline = loop.time() + AXIS_TIMEOUT
            last, stalled, wrong = axis.read(), 0, 0
            while True:
                await self._next_frame()
                self._check_faults(baseline)
                pos = axis.read()
                step = (pos - last) * sign
                last = pos
                if step > 0.02:
                    stalled, wrong = 0, 0
                    rate = max(0.1, min(step, 5.0))  # frames arrive once per second
                elif step < -0.05:
                    wrong += 1
                    if wrong >= 2:
                        raise GotoError(f"{axis.name} is moving the wrong way, stopped")
                else:
                    stalled += 1
                if (axis.target - pos) * sign <= LEAD_SECONDS * rate:
                    break
                if axis.limits[sign] in self._status().limit_switches:
                    break
                if stalled >= STALL_FRAMES:
                    raise GotoError(f"{axis.name} is not moving (stuck at {pos:.1f}°)")
                if loop.time() > deadline:
                    raise GotoError(f"{axis.name} timed out")
            await self._serial.stop()
            await self._settle(axis)
            self._check_faults(baseline)

        err = axis.target - axis.read()
        if abs(err) > FAIL_ABOVE:
            sign = 1 if err > 0 else -1
            if axis.limits[sign] in self._status().limit_switches:
                return f"{axis.name} stopped at its limit switch ({axis.read():.1f}°)"
            raise GotoError(f"{axis.name} ended at {axis.read():.1f}°, target {axis.target:.1f}°")
        return f"{axis.name} at {axis.read():.1f}° (asked {axis.target:.1f}°)"

    async def _settle(self, axis: _Axis):
        """Wait until the axis has really stopped; repeat the stop command if it has not."""
        prev, still = axis.read(), 0
        for i in range(10):
            await self._next_frame()
            pos = axis.read()
            still = still + 1 if abs(pos - prev) < 0.02 else 0
            prev = pos
            if still >= 2:
                return
            if i >= 3 and still == 0:
                logger.warning(f"GOTO: {axis.name} still moving after stop, repeating stop")
                await self._serial.stop()
        raise GotoError(f"{axis.name} did not stop when told to")
