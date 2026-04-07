"""SMA inverter data endpoints - reads from SBFspot SQLite database."""

import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inverter", tags=["inverter"])

SBFSPOT_DB = os.environ.get("SBFSPOT_DB", "/data/SBFspot.db")


def _get_db() -> sqlite3.Connection:
    """Open a read-only connection to the SBFspot database."""
    db_uri = f"file:{SBFSPOT_DB}?mode=ro&immutable=1"
    try:
        conn = sqlite3.connect(db_uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.OperationalError as exc:
        logger.error(f"Cannot open SBFspot database at {SBFSPOT_DB}: {exc}")
        raise HTTPException(status_code=503, detail=f"SBFspot database unavailable: {exc}")


@router.get("/status")
async def inverter_status() -> dict[str, Any]:
    """Return current inverter status from the SBFspot database.

    Combines data from the Inverters table (identity, daily/total yield)
    and the latest SpotData row (live power, temperature).
    """
    conn = _get_db()
    try:
        # Get inverter info
        inv = conn.execute(
            "SELECT Serial, Name, Type, SW_Version, EToday, ETotal, Status, TimeStamp "
            "FROM Inverters ORDER BY TimeStamp DESC LIMIT 1"
        ).fetchone()

        if inv is None:
            raise HTTPException(status_code=404, detail="No inverter data found")

        # Get latest spot data for live power and temperature
        spot = conn.execute(
            "SELECT TimeStamp, Pac1, Pac2, Pac3, Temperature, Status "
            "FROM SpotData WHERE Serial = ? ORDER BY TimeStamp DESC LIMIT 1",
            (inv["Serial"],),
        ).fetchone()

        current_power = 0
        temperature = None
        last_update = inv["TimeStamp"]
        status = inv["Status"]

        if spot is not None:
            current_power = (spot["Pac1"] or 0) + (spot["Pac2"] or 0) + (spot["Pac3"] or 0)
            temperature = spot["Temperature"] if spot["Temperature"] else None
            last_update = spot["TimeStamp"]
            status = spot["Status"]

        return {
            "name": inv["Name"],
            "type": inv["Type"],
            "firmware": inv["SW_Version"],
            "current_power": current_power,
            "today_yield": inv["EToday"] or 0,
            "total_yield": inv["ETotal"] or 0,
            "temperature": temperature,
            "status": status,
            "last_update": datetime.fromtimestamp(last_update, tz=timezone.utc).isoformat() if last_update else None,
        }
    finally:
        conn.close()


@router.get("/today")
async def inverter_today() -> list[dict[str, Any]]:
    """Return today's power readings from DayData for charting.

    Returns an array of {timestamp, power} objects for the current day.
    """
    conn = _get_db()
    try:
        # Get any inverter serial
        inv = conn.execute("SELECT Serial FROM Inverters LIMIT 1").fetchone()
        if inv is None:
            raise HTTPException(status_code=404, detail="No inverter data found")

        # Calculate start-of-day as unix timestamp (UTC)
        now = datetime.now(tz=timezone.utc)
        start_of_day = int(datetime(now.year, now.month, now.day, tzinfo=timezone.utc).timestamp())

        rows = conn.execute(
            "SELECT TimeStamp, Power FROM DayData "
            "WHERE Serial = ? AND TimeStamp >= ? ORDER BY TimeStamp ASC",
            (inv["Serial"], start_of_day),
        ).fetchall()

        return [
            {
                "timestamp": datetime.fromtimestamp(row["TimeStamp"], tz=timezone.utc).isoformat(),
                "power": row["Power"] or 0,
            }
            for row in rows
        ]
    finally:
        conn.close()
