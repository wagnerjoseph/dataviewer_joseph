"""Interactive Panel application for dataviewer_joseph.

Features:
- Interactive map with OSM basemap and clickable points
- Split and variable selectors
- Location ID input (or click on map)
- Timeseries via plotting_joseph with var_specs editor
- Map data table showing all variable values for the selected location
- Additional data viewer with selectable renderer (bar, scatter, table, histogram, box)
- Auto-discovery of splits, variables, and locations from parquet files
"""

from io import BytesIO
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geoviews as gv
from cmcrameri import cm as crameri_cm
from plotting_joseph import plot_map
import holoviews as hv
import numpy as np
import pandas as pd
import panel as pn

from .config import DataConfig
from .data import (
    DataIndex,
    find_splits,
    get_timeseries_variables,
    get_variable_names,
    load_additional_data_for_location,
    load_location_lookup,
    load_map_data_for_location,
    load_timeseries_for_location,
    load_variable_data,
)
from .plotting import (
    add_dynamic_sizing,
    create_map_data_table,
    find_nearest_location,
    plot_location_timeseries,
    render_additional_data,
    web_mercator_to_latlon,
)
from .var_spec_editor import VarSpecEditor

logger = logging.getLogger(__name__)


def _valid_timeseries_specs(specs, data):
    """Keep var_specs whose columns exist in ``data`` (splits differ).

    The var-spec editor holds the specs of whichever split it was built
    for; when a location of another split is plotted (or the plot
    regenerates), specs referencing missing columns must be dropped —
    otherwise plotting_joseph raises KeyError.
    """
    cols = set(data.columns)
    return [
        s for s in specs
        if s.get("name") and s.get("name") in cols
        and (s.get("add_to") is None or s["add_to"] in cols)
    ]


pn.extension()
hv.extension("bokeh")
gv.extension("bokeh")

# Bokeh 3.9's WebGL backend renders scatter glyph colors with swapped R/B
# channels on some GPUs (colorbar and matplotlib downloads stay correct —
# they do not use WebGL). Force the 2D canvas backend for correct colors.
hv.renderer("bokeh").webgl = False


def _config_timestamp() -> str:
    """Return a sortable timestamp string for a var config filename."""
    return pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")


def save_var_config(config: DataConfig, json_text: str) -> Path:
    """Save a var config JSON string into the data's config folder.

    Args:
        config: DataConfig pointing at the data root
        json_text: Serialized var config JSON

    Returns:
        Path to the written file
    """
    config_dir = config.config_dir
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / f"var_config_{_config_timestamp()}.json"
    path.write_text(json_text, encoding="utf-8")
    logger.info(f"Saved var config to {path}")
    return path


def load_most_recent_var_config(config: DataConfig) -> str | None:
    """Return the content of the most recent var config in the data folder.

    The most recent file is chosen by modification time (ties broken by
    filename, which embeds a timestamp). Returns ``None`` if no config exists.

    Args:
        config: DataConfig pointing at the data root

    Returns:
        The JSON text of the newest config, or None if none found
    """
    config_dir = config.config_dir
    if not config_dir.is_dir():
        return None

    files = [p for p in config_dir.glob("*.json") if p.is_file()]
    if not files:
        return None

    newest = max(files, key=lambda p: (p.stat().st_mtime, p.name))
    try:
        return newest.read_text(encoding="utf-8")
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Could not read var config {newest}: {e}")
        return None


class DownloadHandler:
    """Handler for map and timeseries downloads."""

    def __init__(
        self,
        state: dict,
        split_select: pn.widgets.Select,
        variable_select: pn.widgets.Select,
        cmap_select: pn.widgets.Select,
        gradient_select: pn.widgets.Select,
        config: DataConfig,
        error_pane: pn.pane.Alert,
        loading_indicator: pn.indicators.LoadingSpinner,
        download_map_button: pn.widgets.FileDownload,
        download_timeseries_button: pn.widgets.FileDownload,
        map_pane: pn.pane.HoloViews,
    ):
        self.state = state
        self.split_select = split_select
        self.variable_select = variable_select
        self.cmap_select = cmap_select
        self.gradient_select = gradient_select
        self.config = config
        self.error_pane = error_pane
        self.loading_indicator = loading_indicator
        self.download_map_button = download_map_button
        self.download_timeseries_button = download_timeseries_button
        self.map_pane = map_pane

        # Set up callbacks for FileDownload widgets
        self.download_map_button.callback = self._generate_map_download
        self.download_timeseries_button.callback = self._generate_timeseries_download

    def _show_error(self, message: str):
        """Display an error message."""
        self.error_pane.object = f"**Error:** {message}"
        self.error_pane.visible = True

    def _read_live_extent(self) -> tuple[float, float, float, float] | None:
        """Read the current zoom extent directly from the live rendered map.

        Returns ``(lon_min, lon_max, lat_min, lat_max)`` from the current
        Web Mercator ranges (no clamping).
        """
        try:
            if hasattr(self.map_pane, "_plots") and self.map_pane._plots:
                plot = list(self.map_pane._plots.values())[0]
                if isinstance(plot, (list, tuple)):
                    plot = plot[0]
                if hasattr(plot, "state"):
                    s = plot.state
                    x_start = s.x_range.start
                    x_end = s.x_range.end
                    y_start = s.y_range.start
                    y_end = s.y_range.end
                    if None in (x_start, x_end, y_start, y_end):
                        return None
                    lat_min, lon_min = web_mercator_to_latlon(x_start, y_start)
                    lat_max, lon_max = web_mercator_to_latlon(x_end, y_end)
                    return (lon_min, lon_max, lat_min, lat_max)
        except Exception:
            pass
        return None

    def _generate_map_download(self):
        """Generate map file content for download."""
        split_dir = self.split_select.value
        variable_name = self.variable_select.value

        if not split_dir or not variable_name:
            self._show_error("No split or variable selected")
            return None

        self.loading_indicator.value = True
        self.error_pane.visible = False

        try:
            # Load data
            map_data = load_variable_data(self.config, split_dir, variable_name)

            if map_data.empty:
                self._show_error("No data available for download")
                return None

            # Current dataviewer extent (live from rendered map)
            extent = self._read_live_extent()
            if extent is None:
                self._show_error("Map extent could not be determined")
                return None

            # Match the live map's colors: shared backend selection
            # (Sequential reversed, percentile ranges; Diverging symmetric).
            _, cmap, value_range = _gradient_style(
                self.cmap_select.value,
                self.gradient_select.value,
                map_data[variable_name].to_numpy(),
            )

            # Marker for the currently selected location, if any
            selected_location_id = self.state.get("selected_location_id")
            add_marker = (
                [("o", int(selected_location_id))]
                if selected_location_id is not None
                else None
            )

            timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
            filename = f"map_{split_dir}_{variable_name}_{timestamp}.png"
            tmp_path = Path("/tmp") / filename

            plot_map(
                data=map_data,
                var=variable_name,
                master_lookup=str(self.config.lookup_path),
                cmap=cmap,
                value_range=value_range,
                extent=extent,
                grid_sampling=0.1,
                add_coastlines=True,
                add_marker=add_marker,
                save_path=str(tmp_path),
                show_plot=False,
                dpi=300,
            )

            data = tmp_path.read_bytes()
            tmp_path.unlink(missing_ok=True)

            self.download_map_button.filename = filename
            return BytesIO(data)

        except Exception as e:
            import traceback

            logger.error(f"Error generating map download: {e}\n{traceback.format_exc()}")
            self._show_error(f"Failed to generate map: {e!s}")
            return None
        finally:
            self.loading_indicator.value = False

    def _generate_timeseries_download(self):
        """Generate timeseries file content for download."""
        fig = self.state.get("current_timeseries_fig")
        if fig is None:
            self._show_error("No timeseries plot available")
            return None

        self.error_pane.visible = False

        try:
            buf = BytesIO()
            fig.savefig(buf, format="png", dpi=300, bbox_inches="tight")

            timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
            location_id = self.state.get("selected_location_id", "unknown")
            filename = f"timeseries_location_{location_id}_{timestamp}.png"

            self.download_timeseries_button.filename = filename
            return buf
        except Exception as e:
            import traceback

            logger.error(
                f"Error generating timeseries download: {e}\n{traceback.format_exc()}"
            )
            self._show_error(f"Failed to generate timeseries: {e!s}")
            return None

# Curated Fabio Crameri scientific colormaps for the map, grouped by gradient type.
CRAMERI_CMAPS = {
    "Sequential": ["batlow", "oslo", "lajolla", "bilbao"],
    "Diverging": ["vik", "broc", "cork", "roma"],
}
DEFAULT_GRADIENT = "Sequential"
DEFAULT_CMAP = "oslo"
SNAP_DISTANCE_KM = 50.0

_N_PALETTE = 256


def _cmap_hex_palette(cmap_name: str, reversed_colors: bool = False) -> list[str]:
    """Sample a Crameri colormap into a list of hex colors (low → high)."""
    cmap = crameri_cm.cmaps[cmap_name]
    if reversed_colors:
        cmap = cmap.reversed()
    rgba = (cmap(np.linspace(0.0, 1.0, _N_PALETTE))[:, :3] * 255).round().astype(int)
    return [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in rgba]


def _gradient_style(
    cmap_name: str, gradient_type: str, values: np.ndarray
) -> tuple[list[str], object, tuple[float, float] | None]:
    """Backend color selection, shared by the live map and downloads.

    Sequential maps are reversed (high values = dark) and use percentile
    limits; Diverging maps keep the natural direction with limits symmetric
    around zero.

    Returns:
        (palette_hexes, cmap_object, clim) — the palette drives the interactive
        colorbar/markers, the cmap object drives matplotlib-based downloads,
        and clim holds the color limits already normalized the same way.
    """
    valid = values[~np.isnan(values)]
    if len(valid) == 0:
        return [], crameri_cm.cmaps[cmap_name], (None, None)
    vmin = float(np.percentile(valid, 2))
    vmax = float(np.percentile(valid, 98))
    reversed_colors = gradient_type == "Sequential"

    if reversed_colors:
        clim = (vmin, vmax)
    else:
        max_abs = max(abs(vmin), abs(vmax))
        clim = (-max_abs, max_abs)
    cmap = crameri_cm.cmaps[cmap_name]
    return (
        _cmap_hex_palette(cmap_name, reversed_colors=reversed_colors),
        cmap.reversed() if reversed_colors else cmap,
        clim,
    )


def create_app(config: DataConfig, var_specs: list[dict] | None = None) -> pn.Column:
    """Create the interactive data viewer application.

    Args:
        config: DataConfig instance pointing to data root
        var_specs: Optional list of timeseries var_specs to preload into the
            var_spec editor. Lets a saved var config be reused for a new
            analysis. See ``VarSpecEditor.from_var_specs``.

    Returns:
        Panel Column application with map, timeseries, map data table, and additional data
    """
    # Initialize data index
    index = DataIndex(config)

    if not index.splits:
        return pn.Column(
            pn.pane.Alert(
                f"**Error:** No splits found in {config.root}. "
                f"Ensure data directory contains split folders with metrics_global_plot subfolders.",
                alert_type="danger",
                sizing_mode="stretch_width",
            )
        )

    # Per-session state
    state = {
        "current_split": None,
        "current_variable": None,
        "selected_location_id": None,
        "map_data": None,
        "location_lookup": None,
        "updating_location_input": False,
        "ts_data": None,
        "ts_location_id": None,
        "ts_tile_id": None,
        "var_spec_editor": None,
        "additional_data": None,
        "current_timeseries_fig": None,
    }

    # =============================================================================
    # WIDGETS
    # =============================================================================

    available_splits = find_splits(config)
    single_split = len(available_splits) <= 1
    split_select = pn.widgets.Select(
        label="Split",
        options={s: s for s in available_splits},
        value=available_splits[-1] if available_splits else None,
        width=200,
    )

    # Get variables for initial split
    initial_variables = (
        get_variable_names(config, split_select.value) if split_select.value else []
    )
    variable_select = pn.widgets.Select(
        label="Variable",
        options=initial_variables,
        value=initial_variables[0] if initial_variables else None,
        width=200,
    )

    location_input = pn.widgets.IntInput(
        label="Location ID",
        value=None,
        step=1,
        width=120,
    )

    gradient_select = pn.widgets.Select(
        label="Gradient",
        options=list(CRAMERI_CMAPS.keys()),
        value=DEFAULT_GRADIENT,
        width=150,
    )
    cmap_select = pn.widgets.Select(
        label="Colormap",
        options=CRAMERI_CMAPS[DEFAULT_GRADIENT],
        value=DEFAULT_CMAP,
        width=150,
    )

    loading_indicator = pn.indicators.LoadingSpinner(
        value=False, size=25, label="Loading…"
    )

    download_map_button = pn.widgets.FileDownload(
        file=None,
        filename="map.png",
        label="Download Map",
        color="primary",
        icon="download",
        disabled=True,
    )

    download_timeseries_button = pn.widgets.FileDownload(
        file=None,
        filename="timeseries.png",
        label="Download Timeseries",
        color="primary",
        icon="download",
        disabled=True,
    )

    error_pane = pn.pane.Alert(
        "",
        alert_type="danger",
        sizing_mode="stretch_width",
        visible=False,
        styles={"min-width": "220px"},
    )

    # =============================================================================
    # PANES
    # =============================================================================

    map_pane = pn.pane.HoloViews(
        None,
        sizing_mode="stretch_both",
        min_height=500,
    )

    timeseries_pane = pn.Column(
        pn.pane.Markdown("**Click a location on the map to view timeseries**"),
        sizing_mode="stretch_both",
    )
    timeseries_pane.min_height = 280

    map_data_table_pane = pn.Column(
        sizing_mode="stretch_both",
        margin=0,
        styles={"padding": "0"},
    )

    additional_data_pane = pn.Column(
        sizing_mode="stretch_both",
        margin=0,
        styles={"padding": "0"},
    )

    info_pane = pn.pane.Markdown(
        "**Status:** Ready - Select a location to view details",
        sizing_mode="stretch_width",
    )

    # =============================================================================
    # HELPER FUNCTIONS
    # =============================================================================

    def _get_map_data(split_dir: str, variable_name: str) -> pd.DataFrame:
        """Load map data (variable values merged with coordinates) for a split."""
        return load_variable_data(config, split_dir, variable_name)

    def load_and_display_location_data(location_id: int):
        """Load and display timeseries, map data table, and additional data for a location."""
        try:
            split_dir = split_select.value
            map_data = state.get("map_data")

            if map_data is None:
                return

            matching = map_data[map_data[config.id_column] == location_id]
            if matching.empty:
                return

            tile_id = None
            try:
                lookup = load_location_lookup(config)
                loc_row = lookup[lookup[config.id_column] == location_id]
                if not loc_row.empty:
                    tile_id = loc_row[config.tile_col].iloc[0]
            except Exception:
                pass

            if tile_id:
                with ThreadPoolExecutor(max_workers=2) as executor:
                    ts_future = executor.submit(
                        load_timeseries_for_location,
                        config,
                        split_dir,
                        location_id,
                        tile_id,
                    )
                    map_future = executor.submit(
                        load_map_data_for_location,
                        config,
                        split_dir,
                        location_id,
                    )

                    ts_data = ts_future.result()
                    map_data_for_location = map_future.result()
            else:
                ts_data = None
                map_data_for_location = None

            if ts_data is not None and not ts_data.empty:
                # Cache ts_data for config-driven replot
                state["ts_data"] = ts_data
                state["ts_location_id"] = location_id
                state["ts_tile_id"] = tile_id

                # Get var_specs from editor (keep only columns of THIS split)
                var_spec_editor = state.get("var_spec_editor")
                var_specs = (
                    var_spec_editor.to_var_specs() if var_spec_editor else None
                )
                if var_specs:
                    var_specs = _valid_timeseries_specs(var_specs, ts_data)

                # Plot timeseries using plotting_joseph
                figs = plot_location_timeseries(
                    data=ts_data,
                    location_ids=[location_id],
                    var_specs=var_specs,
                    time_col="time",
                    location_id_col=config.id_column,
                    figsize=(10, 5),
                    font_scale=1.0,
                    show_plot=False,
                    master_lookup=str(config.lookup_path),
                )

                if figs and len(figs) > 0:
                    timeseries_plot = pn.pane.Matplotlib(
                        figs[0],
                        tight=True,
                        sizing_mode="stretch_width",
                    )
                    timeseries_pane.clear()
                    timeseries_pane.append(timeseries_plot)
                    state["current_timeseries_fig"] = figs[0]
                    download_timeseries_button.disabled = False

                if map_data_for_location is not None and not map_data_for_location.empty:
                    map_data_table = create_map_data_table(map_data_for_location)
                    map_data_table_pane.clear()
                    map_data_table_pane.append(map_data_table)
                else:
                    map_data_table_pane.clear()
                    map_data_table_pane.append(
                        pn.pane.Markdown("No map data available for this location")
                    )

                # Load and render additional data
                additional_data = load_additional_data_for_location(
                    config, split_dir, location_id, tile_id
                )
                state["additional_data"] = additional_data
                if additional_data is not None:
                    render_and_display_additional_data(additional_data)
                else:
                    additional_data_pane.clear()
                    additional_data_pane.append(
                        pn.pane.Markdown("Select a location to view additional data")
                    )
            else:
                state["current_timeseries_fig"] = None
                download_timeseries_button.disabled = True
                timeseries_pane.clear()
                timeseries_pane.append(
                    pn.pane.Markdown(
                        f"**No timeseries data found for location {location_id}**"
                    )
                )
                map_data_table_pane.clear()
                map_data_table_pane.append(
                    pn.pane.Markdown("Select a location to view map data")
                )
                additional_data_pane.clear()
                additional_data_pane.append(
                    pn.pane.Markdown("Select a location to view additional data")
                )

        except Exception as e:
            import traceback

            logger.error(f"Error loading location data: {e}\n{traceback.format_exc()}")
            state["current_timeseries_fig"] = None
            download_timeseries_button.disabled = True
            error_msg = f"Error: {e!s}"
            timeseries_pane.clear()
            timeseries_pane.append(pn.pane.Markdown(f"**Error:** {error_msg}"))
            map_data_table_pane.clear()
            map_data_table_pane.append(pn.pane.Markdown("Error loading map data"))
            additional_data_pane.clear()
            additional_data_pane.append(
                pn.pane.Markdown("Error loading additional data")
            )

    def render_and_display_additional_data(attrs):
        """Render additional data (auto-suggested style) and display it.

        Args:
            attrs: pandas Series with attribute names as index
        """
        try:
            plot = render_additional_data(
                attrs,
                title="Additional Data",
                width=280,
                height=210,
            )
            additional_data_pane.clear()
            additional_data_pane.append(plot)
        except Exception as e:
            logger.warning(f"Error rendering additional data: {e}")
            additional_data_pane.clear()
            additional_data_pane.append(
                pn.pane.Markdown(f"Error rendering: {e!s}")
            )

    def regenerate_timeseries():
        """Re-render timeseries plot with current var_specs (from cached ts_data)."""
        ts_data = state.get("ts_data")
        location_id = state.get("ts_location_id")

        if ts_data is None or location_id is None:
            return  # No data to replot

        # Get var_specs from editor (keep only columns of THIS split)
        var_spec_editor = state.get("var_spec_editor")
        var_specs = (
            var_spec_editor.to_var_specs() if var_spec_editor else None
        )
        if var_specs:
            var_specs = _valid_timeseries_specs(var_specs, ts_data)

        # Plot timeseries using plotting_joseph
        figs = plot_location_timeseries(
            data=ts_data,
            location_ids=[location_id],
            var_specs=var_specs,
            time_col="time",
            location_id_col=config.id_column,
            figsize=(10, 5),
            font_scale=1.0,
            show_plot=False,
            master_lookup=str(config.lookup_path),
        )

        if figs and len(figs) > 0:
            timeseries_plot = pn.pane.Matplotlib(
                figs[0],
                tight=True,
                sizing_mode="stretch_width",
            )
            timeseries_pane.clear()
            timeseries_pane.append(timeseries_plot)

    def select_location(pos: int, location_id: int):
        """Select a location: update state, widgets, and load its data."""
        state["selected_location_id"] = location_id

        state["updating_location_input"] = True
        try:
            location_input.value = location_id
        finally:
            state["updating_location_input"] = False

        info_pane.object = f"**Selected Location ID:** `{location_id}`"
        load_and_display_location_data(location_id)

    def create_tap_handler(
        map_data: pd.DataFrame,
        lon_col: str,
        lat_col: str,
    ):
        """Create a tap callback that snaps map clicks to the nearest location."""

        def on_tap(x, y):
            """Snap a click anywhere on the map to the nearest location."""
            if x is None or y is None:
                return
            if abs(x) <= 180 and abs(y) <= 90:
                tap_lat, tap_lon = y, x
            else:
                tap_lat, tap_lon = web_mercator_to_latlon(x, y)
            pos = find_nearest_location(
                map_data,
                lon_col,
                lat_col,
                tap_lon,
                tap_lat,
                max_distance_km=SNAP_DISTANCE_KM,
            )
            if pos is None:
                selected = state.get("selected_location_id")
                suffix = (
                    f" (keeping Location ID `{selected}`)"
                    if selected is not None
                    else ""
                )
                info_pane.object = (
                    f"**No location within {SNAP_DISTANCE_KM:g} km of click**{suffix}"
                )
                return
            location_id = int(map_data.iloc[pos][config.id_column])
            select_location(pos, location_id)

        return on_tap

    # =============================================================================
    # MAP RENDERING
    # =============================================================================

    def _saved_view_ranges() -> dict | None:
        """Return the current zoom ranges of the live map plot, if any."""
        try:
            if hasattr(map_pane, "_plots") and map_pane._plots:
                plot = list(map_pane._plots.values())[0]
                if hasattr(plot, "state"):
                    s = plot.state
                    return {
                        "x_start": s.x_range.start,
                        "x_end": s.x_range.end,
                        "y_start": s.y_range.start,
                        "y_end": s.y_range.end,
                    }
        except Exception:
            pass
        return None

    def render_map(split_dir: str, variable_name: str, preserve_view: bool = False):
        """Render the map for a split/variable.

        Builds a complete fresh overlay (points, colormap, colorbar, streams)
        and assigns it to the map pane, so legend and markers always refer to
        the same points element. When ``preserve_view`` is True, the current
        zoom ranges and location selection are carried over.
        """
        loading_indicator.value = True

        try:
            saved_ranges = _saved_view_ranges() if preserve_view else None

            map_data = _get_map_data(split_dir, variable_name)

            if map_data.empty:
                map_pane.object = hv.Text(0, 0, "No data available")
                return

            state["map_data"] = map_data

            palette, _, clim = _gradient_style(
                cmap_select.value,
                gradient_select.value,
                map_data[variable_name].values,
            )

            points = gv.Points(
                map_data,
                kdims=[config.lon_col, config.lat_col],
                vdims=[config.id_column, variable_name],
            ).opts(
                color=variable_name,
                cmap=palette,
                size=5,
                alpha=0.9,
                responsive=True,
                tools=["tap", "hover", "box_zoom", "wheel_zoom", "reset"],
                colorbar=True,
                clim=clim,
                title=f"{variable_name} - {split_dir}",
                active_tools=["wheel_zoom"],
                hooks=[add_dynamic_sizing],
                hover_tooltips=[
                    ("Location ID", f"@{config.id_column}"),
                    ("Value", f"@{variable_name}"),
                    ("Lon", f"@{config.lon_col}"),
                    ("Lat", f"@{config.lat_col}"),
                ],
            )

            # Snap clicks anywhere on the map to the nearest location
            tap_stream = hv.streams.Tap(source=points)
            tap_stream.add_subscriber(
                create_tap_handler(map_data, config.lon_col, config.lat_col)
            )

            basemap = gv.tile_sources.OSM.opts(alpha=0.25, responsive=True)
            map_pane.object = basemap * points
            download_map_button.disabled = False

            # Restore zoom ranges after the pane has re-rendered
            if saved_ranges:

                def restore_ranges():
                    try:
                        if hasattr(map_pane, "_plots") and map_pane._plots:
                            bokeh_plot = list(map_pane._plots.values())[0]
                            if hasattr(bokeh_plot, "state"):
                                s = bokeh_plot.state
                                s.x_range.start = saved_ranges["x_start"]
                                s.x_range.end = saved_ranges["x_end"]
                                s.y_range.start = saved_ranges["y_start"]
                                s.y_range.end = saved_ranges["y_end"]
                    except Exception:
                        pass

                pn.state.onload(restore_ranges)

        finally:
            loading_indicator.value = False

    # =============================================================================
    # CALLBACKS
    # =============================================================================

    def on_split_change(event):
        """Handle split selection change."""
        split_dir = event.new

        variables = get_variable_names(config, split_dir)
        if variables:
            variable_select.options = variables
            variable_select.value = variables[0]
        else:
            variable_select.options = []
            variable_select.value = None

        # Keep the user's var_specs; just update the available variables so
        # new subplots use THIS split's columns. Specs whose columns do not
        # exist for the new split are filtered out at plot time
        # (_valid_timeseries_specs) instead of being dropped here.
        editor = state.get("var_spec_editor")
        if editor is not None:
            editor.update_available_variables(
                get_timeseries_variables(config, split_dir)
            )

    def on_variable_change(event):
        """Handle variable selection change."""
        split_dir = split_select.value
        variable_name = event.new

        if split_dir and variable_name:
            render_map(split_dir, variable_name, preserve_view=True)

    def on_gradient_change(event):
        """Repopulate colormap options when the gradient type changes."""
        gradient_type = event.new
        options = CRAMERI_CMAPS[gradient_type]
        cmap_select.options = options
        cmap_select.value = options[0]

    def on_cmap_change(event):
        """Re-render the map when the colormap changes."""
        split_dir = split_select.value
        variable_name = variable_select.value
        if split_dir and variable_name:
            render_map(split_dir, variable_name, preserve_view=True)

    def on_location_input_change(event):
        """Handle manual location ID input."""
        if state.get("updating_location_input", False):
            return

        location_id = event.new
        if location_id is None:
            return

        if state["map_data"] is None:
            return

        matching = state["map_data"][state["map_data"][config.id_column] == location_id]

        if matching.empty:
            info_pane.object = (
                f"**Error:** Location ID `{location_id}` not found in current view"
            )
            return

        pos = state["map_data"].index.get_loc(matching.index[0])
        select_location(pos, location_id)

    # Wire up callbacks
    split_select.param.watch(on_split_change, "value")
    variable_select.param.watch(on_variable_change, "value")
    location_input.param.watch(on_location_input_change, "value")
    gradient_select.param.watch(on_gradient_change, "value")
    cmap_select.param.watch(on_cmap_change, "value")

    # =============================================================================
    # DOWNLOAD HANDLER
    # =============================================================================

    # Instantiate the handler (its constructor wires up the FileDownload callbacks).
    DownloadHandler(
        state=state,
        split_select=split_select,
        variable_select=variable_select,
        cmap_select=cmap_select,
        gradient_select=gradient_select,
        config=config,
        error_pane=error_pane,
        loading_indicator=loading_indicator,
        download_map_button=download_map_button,
        download_timeseries_button=download_timeseries_button,
        map_pane=map_pane,
    )

    # =============================================================================
    # VAR SPEC EDITOR
    # =============================================================================

    # Initialize var_spec editor with available timeseries variables
    ts_variables = (
        get_timeseries_variables(config, split_select.value)
        if split_select.value
        else []
    )

    # Create editor with callback to regenerate plot on config change
    var_spec_editor = VarSpecEditor(
        available_variables=ts_variables, on_config_change=regenerate_timeseries
    )
    # Add default subplots (one per variable, creating 3 panels by default)
    for var in ts_variables[:3]:
        var_spec_editor.add_subplot(var)

    # Preload a saved configuration for a new analysis, if provided.
    # Otherwise auto-import the most recent config saved in the data folder.
    if var_specs:
        var_spec_editor.from_var_specs(var_specs)
    else:
        try:
            saved_text = load_most_recent_var_config(config)
            if saved_text:
                var_spec_editor.from_json(saved_text)
                logger.info("Auto-imported the most recent var config")
        except Exception as e:
            logger.warning(
                f"Could not auto-import most recent var config: {e}"
            )
    state["var_spec_editor"] = var_spec_editor

    # Use the editor's live layout (automatically updates on add/remove)
    var_spec_pane = var_spec_editor.layout

    # =============================================================================
    # VAR CONFIG IMPORT / EXPORT
    # =============================================================================

    def _generate_var_config_download():
        """Generate the var config JSON for download and save it to the data folder."""
        try:
            json_text = var_spec_editor.to_json()
            data = json_text.encode("utf-8")
            filename = f"var_config_{_config_timestamp()}.json"
            download_var_config_button.filename = filename
            try:
                save_var_config(config, json_text)
            except Exception as e:
                logger.warning(f"Could not save var config to data folder: {e}")
            return BytesIO(data)
        except Exception as e:
            import traceback

            logger.error(
                f"Error generating var config: {e}\n{traceback.format_exc()}"
            )
            return None

    download_var_config_button = pn.widgets.FileDownload(
        file=None,
        filename="var_config.json",
        label="Download var config",
        color="primary",
        icon="download",
    )
    download_var_config_button.callback = _generate_var_config_download

    upload_var_config = pn.widgets.FileInput(
        label="Upload var config",
        accept=".json",
    )

    def on_var_config_upload(event):
        """Load an uploaded var config into the editor and refresh the plot."""
        if not event.new:
            return
        try:
            text = event.new.decode("utf-8")
            var_spec_editor.from_json(text)
            regenerate_timeseries()
            error_pane.visible = False
        except Exception as e:
            import traceback

            logger.error(
                f"Error importing var config: {e}\n{traceback.format_exc()}"
            )
            error_pane.object = f"**Error:** Failed to import var config: {e!s}"
            error_pane.visible = True

    upload_var_config.param.watch(on_var_config_upload, "value")

    var_config_controls = pn.Row(
        download_var_config_button,
        upload_var_config,
        pn.pane.Markdown(
            "_Export the current timeseries config, or import a saved one. "
            "Imported config applies immediately._",
            width=210,
            margin=(10, 5),
        ),
        sizing_mode="stretch_width",
        margin=(5, 5),
    )

    # =============================================================================
    # INITIALIZATION
    # =============================================================================

    if split_select.value and variable_select.value:
        render_map(split_select.value, variable_select.value)

    # =============================================================================
    # LAYOUT
    # =============================================================================

    bottom_row = pn.Row(
        map_data_table_pane,
        additional_data_pane,
        sizing_mode="stretch_both",
        margin=0,
    )

    right_column = pn.Column(
        timeseries_pane,
        bottom_row,
        sizing_mode="stretch_both",
        styles={"overflow-y": "auto"},
    )

    # Collapsible floating var_spec editor panel (overlays the map)
    config_panel = pn.Column(
        var_config_controls,
        var_spec_pane,
        sizing_mode="stretch_width",
        visible=False,
        styles={
            "position": "absolute",
            "top": "40px",
            "right": "10px",
            "left": "10px",
            "max-height": "72vh",
            "overflow-y": "auto",
            "overflow-x": "auto",
            "z-index": "100",
            "background": "white",
            "border": "1px solid #ddd",
            "border-radius": "5px",
            "box-shadow": "0 2px 10px rgba(0,0,0,0.15)",
        },
    )

    config_toggle = pn.widgets.Button(
        icon="cog",
        label="Config",
        color="default",
        styles={
            "position": "absolute",
            "top": "5px",
            "right": "10px",
            "z-index": "200",
        },
    )

    def toggle_config(event):
        config_panel.visible = not config_panel.visible

    config_toggle.on_click(toggle_config)

    controls = [variable_select, location_input, gradient_select, cmap_select, loading_indicator, download_map_button, download_timeseries_button]
    if not single_split:
        controls.insert(0, split_select)

    controls_row = pn.Row(
        *controls,
        error_pane,
        sizing_mode="stretch_width",
    )

    map_with_config = pn.Row(
        map_pane,
        config_panel,
        config_toggle,
        sizing_mode="stretch_both",
        styles={
            "position": "relative",
        },
    )

    main_layout = pn.Row(
        map_with_config,
        right_column,
        sizing_mode="stretch_both",
        margin=0,
    )

    return pn.Column(
        pn.pane.Markdown(
            "# Dataviewer",
            sizing_mode="stretch_width",
        ),
        controls_row,
        info_pane,
        main_layout,
        sizing_mode="stretch_both",
        styles={"margin": "0", "padding": "0"},
    )
