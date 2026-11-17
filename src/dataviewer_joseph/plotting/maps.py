"""Interactive map plotting for dataviewer_joseph."""

import logging
import math
import time
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0

# How long the view must be idle after the last range event before the
# zoom-adaptive point size is applied (trailing debounce).
ZOOM_DEBOUNCE_MS = 300


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
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
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


def add_dynamic_sizing(
    plot: Any, element: Any, on_extent_change: Any = None
) -> None:
    """Adapt point size to the zoom level using Bokeh range callbacks.

    Every sized glyph state of every sized renderer is resized — the base,
    selection/nonselection (tapped points), hover (inspected points) and
    muted glyphs — so no state can fall out of sync and make points appear
    smaller on hover or after selection. Renderers tagged with
    ``_dataviewer_fixed_size`` (e.g. the selected-location marker) keep
    their size. Both axes are watched (a zoom can change only one range)
    and the applied size is re-resolved on every update, so no callback can
    hold a stale renderer. Sizes are applied with a ``ZOOM_DEBOUNCE_MS``
    trailing debounce: a drag/zoom fires one range event per frame, and
    each event cancels and reschedules the single pending apply, so the
    glyphs stay completely untouched during the gesture and are resized
    exactly once, once the view has been idle for the debounce period.
    The ``on_extent_change`` callback still runs on every event (pure
    computation, keeps downloads in sync with the view).

    Args:
        plot: The HoloViews/Bokeh plot (``.state`` is the bokeh figure)
        element: The rendered HoloViews element
        on_extent_change: Optional callback invoked with the current
            ``(lon_min, lon_max, lat_min, lat_max)`` extent whenever the
            view ranges change (or immediately, with the initial extent).
    """
    # Prevent duplicate callbacks
    if getattr(plot.state, "_size_callback_added", False):
        return
    plot.state._size_callback_added = True

    def scatters() -> list:
        """All glyph renderers on the figure that expose a ``size``."""
        out = []
        for r in plot.state.renderers:
            if getattr(r, "_dataviewer_fixed_size", False):
                continue
            if hasattr(r, "glyph") and hasattr(r.glyph, "size"):
                out.append(r)
        return out

    def current_extent() -> tuple[float, float, float, float] | None:
        """Current extent as ``(lon_min, lon_max, lat_min, lat_max)``."""
        try:
            s = plot.state
            x_start, x_end = s.x_range.start, s.x_range.end
            y_start, y_end = s.y_range.start, s.y_range.end
            if None in (x_start, x_end, y_start, y_end):
                return None
            values = (x_start, x_end, y_start, y_end)
            if not all(math.isfinite(float(v)) for v in values):
                return None
            lat_min, lon_min = web_mercator_to_latlon(float(x_start), float(y_start))
            lat_max, lon_max = web_mercator_to_latlon(float(x_end), float(y_end))
            return (lon_min, lon_max, lat_min, lat_max)
        except Exception:
            return None

    def desired_size() -> float | None:
        """Point size matching the current x-range extent (km)."""
        x_start = plot.state.x_range.start
        x_end = plot.state.x_range.end
        if None in (x_start, x_end):
            return None
        extent = (x_end - x_start) / 1000
        size = (10_000 / extent) ** 1.2
        result = max(1.0, min(50.0, size))
        # Round away float noise: pan updates can wobble the extent in the
        # last bits, which would toggle the size and patch the model every
        # frame. At most ~7 size steps/decade is plenty visually.
        return round(result, 1) if math.isfinite(result) else None

    def apply_zoom() -> None:
        """Apply the size and frame aspect for the current range.

        The frame is kept at equal degrees per pixel (lon span / lat span in
        degrees), the same proportions as the downloaded map: Bokeh's
        ``match_aspect`` alone uses the data-unit (Web Mercator meters) ratio,
        which is wider than the degree ratio away from the equator.
        """
        try:
            size = desired_size()
            if size is None:
                return
            for renderer in scatters():
                for name in ("glyph", "selection_glyph", "nonselection_glyph", "hover_glyph", "muted_glyph"):
                    glyph = getattr(renderer, name, None)
                    if glyph is not None and hasattr(glyph, "size"):
                        current = getattr(glyph, "size", None)
                        if current != size:
                            glyph.size = size
            extent = current_extent()
            if extent is not None:
                lon_min, lon_max, lat_min, lat_max = extent
                lon_span = lon_max - lon_min
                lat_span = lat_max - lat_min
                if lon_span > 0 and lat_span > 0:
                    ratio = max(0.05, min(20.0, lon_span / lat_span))
                    if getattr(plot.state, "aspect_ratio", None) != ratio:
                        plot.state.aspect_ratio = ratio
        except Exception:
            pass

    def _schedule_apply(delay_ms: float) -> None:
        """(Re)schedule the single post-interaction apply on the document.

        Each range event cancels the previous timer and starts a new one,
        so during a continuous drag/zoom nothing is applied at all — the
        glyphs are only touched once the view has been idle.
        """
        doc = plot.document or getattr(plot.state, "document", None)
        if doc is None:
            return  # No bokeh document (e.g. unit tests): flush is tested directly.
        try:
            handle = getattr(plot.state, "_dv_timeout_handle", None)
            if handle is not None:
                try:
                    doc.remove_timeout_callback(handle)
                except Exception:
                    pass
            plot.state._dv_timeout_handle = doc.add_timeout_callback(
                apply_when_idle, max(1, int(round(delay_ms)))
            )
        except Exception:
            pass

    def apply_when_idle() -> None:
        """Debounced apply: only touch glyphs once idle for ``ZOOM_DEBOUNCE_MS``."""
        try:
            idle_ms = (time.time() - plot.state._last_zoom_time) * 1000.0
            if idle_ms < ZOOM_DEBOUNCE_MS:
                _schedule_apply(ZOOM_DEBOUNCE_MS - idle_ms)
                return
            apply_zoom()
        except Exception:
            pass

    def update_size(attr: str, old: Any, new: Any) -> None:
        """Record the event; the size is applied once the view settles."""
        plot.state._last_zoom_time = time.time()
        if on_extent_change is not None:
            try:
                on_extent_change(current_extent())
            except Exception:
                pass
        _schedule_apply(ZOOM_DEBOUNCE_MS)

    plot.state._last_zoom_time = 0.0
    # Exposed so tests can fire the debounced apply deterministically.
    plot.state._dv_sizer_flush = apply_when_idle

    for rng in (plot.state.x_range, plot.state.y_range):
        for attr in ("start", "end"):
            rng.on_change(attr, update_size)

    # Trigger initial update
    apply_zoom()
    if on_extent_change is not None:
        try:
            on_extent_change(current_extent())
        except Exception:
            pass
