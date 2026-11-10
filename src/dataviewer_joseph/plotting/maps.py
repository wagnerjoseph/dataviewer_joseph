"""Interactive map plotting for dataviewer_joseph."""

import logging
import math
import time
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0


def web_mercator_to_latlon(x: float, y: float) -> tuple[float, float]:
    """Convert Web Mercator (meters) to lat/lon (degrees)."""
    R = 6378137  # Earth radius in meters
    lon = (x / R) * (180 / math.pi)
    lat = (math.atan(math.exp(y / R)) * (360 / math.pi)) - 90
    return lat, lon


def haversine_km(
    lat1: float | np.ndarray,
    lon1: float | np.ndarray,
    lat2: float | np.ndarray,
    lon2: float | np.ndarray,
) -> float | np.ndarray:
    """Compute great-circle distances in km between two points (vectorized).

    NaN coordinates propagate to NaN distances.
    """
    lat1 = np.radians(np.asarray(lat1, dtype=float))
    lon1 = np.radians(np.asarray(lon1, dtype=float))
    lat2 = np.radians(np.asarray(lat2, dtype=float))
    lon2 = np.radians(np.asarray(lon2, dtype=float))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(
        (lon2 - lon1) / 2
    ) ** 2
    a = np.clip(a, 0.0, 1.0)
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def find_nearest_location(
    data: pd.DataFrame,
    lon_col: str,
    lat_col: str,
    lon: float,
    lat: float,
    max_distance_km: float = 50.0,
) -> int | None:
    """Find the location nearest to a query point within a maximum distance.

    Args:
        data: DataFrame with location coordinates
        lon_col: Name of the longitude column
        lat_col: Name of the latitude column
        lon: Longitude of the query point (degrees)
        lat: Latitude of the query point (degrees)
        max_distance_km: Maximum snapping distance in km

    Returns:
        Positional row index of the nearest location, or None if no
        location is within max_distance_km
    """
    if data is None or data.empty:
        return None
    lons = pd.to_numeric(data[lon_col], errors="coerce").to_numpy(dtype=float)
    lats = pd.to_numeric(data[lat_col], errors="coerce").to_numpy(dtype=float)
    distances = haversine_km(lat, lon, lats, lons)
    if not np.isfinite(distances).any():
        return None
    pos = int(np.nanargmin(distances))
    if distances[pos] > max_distance_km:
        return None
    return pos


def add_dynamic_sizing(plot: Any, element: Any) -> None:
    """Dynamic point sizing using direct Bokeh callbacks with debouncing."""
    # Prevent duplicate callbacks
    if getattr(plot.state, "_size_callback_added", False):
        return
    plot.state._size_callback_added = True

    # Find the scatter renderer
    scatter = None
    for r in plot.state.renderers:
        if hasattr(r, "glyph") and hasattr(r.glyph, "size"):
            scatter = r
            break

    if scatter is None:
        return

    # Debounce state - track last zoom time
    plot.state._last_zoom_time = 0

    def update_size_immediate():
        """Actually update the point size if zoom has stopped."""
        current_time = time.time()
        elapsed = current_time - plot.state._last_zoom_time

        # Only update if 0.3 seconds have passed since last zoom event
        if elapsed >= 0.3:
            x_start = plot.state.x_range.start
            x_end = plot.state.x_range.end
            extent = (x_end - x_start) / 1000

            # Calculate size based on extent
            size = (10_000 / extent) ** 1.2
            size = max(1, min(50, size))

            # Update the glyph size
            scatter.glyph.size = size

    def update_size(attr: str, old: Any, new: Any):
        """Update point size based on zoom level with debouncing."""
        # Record the time of this zoom event
        plot.state._last_zoom_time = time.time()

        # Schedule update for 0.3 seconds from now
        plot.document.add_timeout_callback(update_size_immediate, 300)

    # Attach callbacks directly to range changes
    plot.state.x_range.on_change("start", update_size)
    plot.state.x_range.on_change("end", update_size)

    # Trigger initial update
    plot.state._last_zoom_time = 0
    update_size_immediate()
