"""Interactive map plotting for dataviewer_joseph."""

import logging
import time
from typing import Any

import numpy as np
import pandas as pd
import geoviews as gv
import holoviews as hv

logger = logging.getLogger(__name__)

hv.extension("bokeh")


def _auto_clim(values: np.ndarray) -> tuple[float, float]:
    """Compute automatic color limits (2nd and 98th percentile)."""
    valid = values[~np.isnan(values)]
    if len(valid) == 0:
        return (None, None)
    return (float(np.percentile(valid, 2)), float(np.percentile(valid, 98)))


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


def create_interactive_map(
    data: pd.DataFrame,
    variable: str,
    lat_col: str = "lat",
    lon_col: str = "lon",
    location_id_col: str = "location_id",
    cmap: str = "viridis",
    width: int = 800,
    height: int = 700,
    title: str | None = None,
) -> gv.Overlay:
    """Create an interactive GeoViews map with clickable points.

    Args:
        data: DataFrame with lat, lon, variable, and location_id columns
        variable: Name of the variable column to display
        lat_col: Name of latitude column
        lon_col: Name of longitude column
        location_id_col: Name of location ID column
        cmap: Colormap name
        width: Plot width in pixels
        height: Plot height in pixels
        title: Plot title (default: variable name)

    Returns:
        GeoViews Overlay with basemap, points, and highlight layer
    """
    if variable not in data.columns:
        raise ValueError(
            f"Variable '{variable}' not found in data. Available: {data.columns.tolist()}"
        )

    if lat_col not in data.columns or lon_col not in data.columns:
        raise ValueError(f"Data must contain '{lat_col}' and '{lon_col}' columns")

    # Compute color limits
    vmin, vmax = _auto_clim(data[variable].values)

    # Create points layer
    points = gv.Points(
        data, kdims=[lon_col, lat_col], vdims=[location_id_col, variable]
    ).opts(
        color=variable,
        cmap=cmap,
        size=2,
        width=width,
        height=height,
        responsive=True,
        tools=["tap", "hover", "box_zoom", "wheel_zoom", "reset"],
        colorbar=True,
        clim=(vmin, vmax),
        title=title or variable,
        active_tools=["wheel_zoom"],
        hooks=[add_dynamic_sizing],
        hover_tooltips=[
            ("Location ID", f"@{location_id_col}"),
            ("Value", f"@{variable}"),
            ("Lon", f"@{lon_col}"),
            ("Lat", f"@{lat_col}"),
        ],
    )

    # Create highlight stream
    highlight_stream = hv.streams.Selection1D(source=points)

    def update_highlight(index):
        """Update highlight based on selection."""
        if index and len(index) > 0:
            location_id = int(data.iloc[index[0]][location_id_col])
            row = data.iloc[index[0]]
            h_df = pd.DataFrame(
                {
                    lon_col: [float(row[lon_col])],
                    lat_col: [float(row[lat_col])],
                    location_id_col: [location_id],
                }
            )

            # Create a more visible highlight with multiple rings
            outer_ring = gv.Points(
                h_df, kdims=[lon_col, lat_col], vdims=[location_id_col]
            ).opts(
                size=30,
                color="red",
                alpha=0.2,
                line_color="red",
                line_width=3,
                line_alpha=0.5,
                marker="circle",
                tools=[],
            )
            middle_ring = gv.Points(
                h_df, kdims=[lon_col, lat_col], vdims=[location_id_col]
            ).opts(
                size=20,
                color="red",
                alpha=0.3,
                line_color="red",
                line_width=2,
                line_alpha=0.6,
                marker="circle",
                tools=[],
            )
            inner_dot = gv.Points(
                h_df, kdims=[lon_col, lat_col], vdims=[location_id_col]
            ).opts(
                size=12,
                color="red",
                alpha=1.0,
                line_color="white",
                line_width=2,
                marker="circle",
                tools=[],
            )

            return outer_ring * middle_ring * inner_dot
        else:
            return hv.Overlay([])

    highlight_layer = hv.DynamicMap(update_highlight, streams=[highlight_stream])

    # Render with basemap
    basemap = gv.tile_sources.OSM.opts(
        alpha=0.6,
        width=width,
        height=height,
        responsive=True,
    )

    return basemap * points * highlight_layer, highlight_stream
