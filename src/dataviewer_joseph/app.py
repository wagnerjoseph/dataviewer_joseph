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
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geoviews as gv
from plotting_joseph import plot_map
import holoviews as hv
import numpy as np
import pandas as pd
import panel as pn
from cmcrameri import cm as crameri_cm

from .config import DataConfig
from .data import (
    DataIndex,
    find_splits,
    get_timeseries_variables,
    get_variable_names,
    load_additional_data_for_location,
    load_location_coordinates,
    load_location_lookup,
    load_map_data_for_location,
    load_timeseries_for_location,
    load_variable_data,
)
from .plotting import (
    add_dynamic_sizing,
    create_map_data_table,
    create_renderer_selector,
    plot_location_timeseries,
    render_additional_data,
)
from .var_spec_editor import VarSpecEditor

logger = logging.getLogger(__name__)

pn.extension()
hv.extension("bokeh")
gv.extension("bokeh")


def _web_mercator_to_latlon(x: float, y: float) -> tuple[float, float]:
    """Convert Web Mercator (meters) to lat/lon (degrees)."""
    R = 6378137  # Earth radius in meters
    lon = (x / R) * (180 / math.pi)
    lat = (math.atan(math.exp(y / R)) * (360 / math.pi)) - 90
    return lat, lon


def _trigger_browser_download(data: bytes, filename: str):
    """Prepare file download for FileDownload widget."""
    return data, filename


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
                    lat_min, lon_min = _web_mercator_to_latlon(x_start, y_start)
                    lat_max, lon_max = _web_mercator_to_latlon(x_end, y_end)
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
            from .data import load_location_coordinates

            # Load data
            var_file = (
                self.config.root
                / split_dir
                / self.config.metrics_subfolder
                / f"{variable_name}.parquet"
            )
            if not var_file.exists():
                self._show_error(f"Variable file not found: {variable_name}")
                return None

            var_data = pd.read_parquet(var_file)
            coords = load_location_coordinates(self.config)
            map_data = var_data.merge(coords, on=self.config.id_column, how="left")
            map_data = map_data.dropna(
                subset=[self.config.lon_col, self.config.lat_col]
            )

            if map_data.empty:
                self._show_error("No data available for download")
                return None

            # Current dataviewer extent (live from rendered map)
            extent = self._read_live_extent()
            if extent is None:
                self._show_error("Map extent could not be determined")
                return None

            # Match the live map's colormap (including reversal for Sequential)
            # and color limits (percentile-based; symmetric for Diverging).
            cmap = _cmap_object(self.cmap_select.value)
            values = map_data[variable_name].to_numpy()
            valid = values[~np.isnan(values)]
            vmin = float(np.percentile(valid, 2)) if len(valid) else None
            vmax = float(np.percentile(valid, 98)) if len(valid) else None

            if self.gradient_select.value == "Sequential":
                cmap = cmap.reversed()
                value_range = (vmin, vmax)
            elif vmin is None or vmax is None:
                value_range = None
            else:
                max_abs = max(abs(vmin), abs(vmax))
                value_range = (-max_abs, max_abs)

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
DEFAULT_CMAP = "batlow"


def _cmap_object(name: str):
    """Resolve a Crameri colormap name to its matplotlib colormap object."""
    return crameri_cm.cmaps[name]


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

    # Pre-load coordinates
    try:
        coords = load_location_coordinates(config)
    except Exception:
        coords = None

    # Per-session state
    state = {
        "current_split": None,
        "current_variable": None,
        "selected_location_id": None,
        "map_data": None,
        "points_element": None,
        "highlight_stream": None,
        "location_lookup": None,
        "updating_location_input": False,
        "last_plot_location_id": None,
        "var_spec_editor": None,
        "renderer_selector": None,
        "additional_data": None,
        "current_timeseries_fig": None,
        "map_rendered": False,
    }

    # =============================================================================
    # WIDGETS
    # =============================================================================

    available_splits = find_splits(config)
    single_split = len(available_splits) <= 1
    split_select = pn.widgets.Select(
        name="Split",
        options={s: s for s in available_splits},
        value=available_splits[-1] if available_splits else None,
    )

    # Get variables for initial split
    initial_variables = (
        get_variable_names(config, split_select.value) if split_select.value else []
    )
    variable_select = pn.widgets.Select(
        name="Variable",
        options=initial_variables,
        value=initial_variables[0] if initial_variables else None,
    )

    location_input = pn.widgets.IntInput(
        name="Location ID",
        value=None,
        step=1,
    )

    gradient_select = pn.widgets.Select(
        name="Gradient",
        options=list(CRAMERI_CMAPS.keys()),
        value=DEFAULT_GRADIENT,
    )
    cmap_select = pn.widgets.Select(
        name="Colormap",
        options=CRAMERI_CMAPS[DEFAULT_GRADIENT],
        value=DEFAULT_CMAP,
    )

    loading_indicator = pn.indicators.LoadingSpinner(
        value=False, size=25, name="Loading…"
    )

    download_map_button = pn.widgets.FileDownload(
        file=None,
        filename="map.png",
        label="Download Map",
        button_type="primary",
        icon="download",
        width=150,
        disabled=True,
    )

    download_timeseries_button = pn.widgets.FileDownload(
        file=None,
        filename="timeseries.png",
        label="Download Timeseries",
        button_type="primary",
        icon="download",
        width=170,
        disabled=True,
    )

    error_pane = pn.pane.Alert(
        "",
        alert_type="danger",
        sizing_mode="stretch_width",
        visible=False,
        styles={"min-width": "220px"},
    )

    # Renderer selector for additional data
    def on_renderer_change(renderer_type):
        """Re-render additional data when renderer type changes."""
        additional_data = state.get("additional_data")
        if additional_data is not None:
            render_and_display_additional_data(additional_data)

    renderer_selector = create_renderer_selector(
        available_renderers=config.renderer_options,
        default_renderer=config.default_renderer,
        on_change=on_renderer_change,
        auto_suggest=True,
    )
    state["renderer_selector"] = renderer_selector

    # =============================================================================
    # PANES
    # =============================================================================

    map_pane = pn.pane.HoloViews(
        None,
        sizing_mode="fixed",
        styles={
            "width": "50vw",
            "height": "75vh",
            "min-width": "50vw",
            "max-width": "50vw",
        },
    )

    timeseries_pane = pn.Column(
        pn.pane.Markdown("**Click a location on the map to view timeseries**"),
        sizing_mode="stretch_width",
    )
    timeseries_pane.min_height = 400

    map_data_table_pane = pn.Column(
        sizing_mode="stretch_both",
        margin=0,
        styles={"padding": "0"},
    )

    additional_data_pane = pn.Column(
        sizing_mode="fixed",
        width=800,
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
        """Load and prepare map data with coordinates."""
        var_data = load_variable_data(config, split_dir, variable_name)
        if coords is not None:
            merged = var_data.merge(coords, on=config.id_column, how="left")
            # Use actual column names from the merged dataframe
            lon_cols = [c for c in merged.columns if c.startswith("lon")]
            lat_cols = [c for c in merged.columns if c.startswith("lat")]
            if lon_cols and lat_cols:
                merged = merged.dropna(subset=[lon_cols[0], lat_cols[0]])
            return merged
        return var_data

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

                # Get var_specs from editor
                var_spec_editor = state.get("var_spec_editor")
                var_specs = (
                    var_spec_editor.to_var_specs() if var_spec_editor else None
                )

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
                    timeseries_plot = pn.pane.Matplotlib(figs[0], tight=True)
                    timeseries_pane.clear()
                    timeseries_pane.append(timeseries_plot)
                    state["last_plot_location_id"] = location_id
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
                state["last_plot_location_id"] = None
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
            state["last_plot_location_id"] = None
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
        """Render additional data using selected renderer and display it.
        
        Args:
            attrs: pandas Series with attribute names as index
        """
        renderer_selector = state.get("renderer_selector")
        if renderer_selector is None:
            return
        
        renderer_type = renderer_selector.get_renderer_type()
        
        # Update selector with data characteristics (for auto-suggest)
        renderer_selector.set_data(attrs)
        
        try:
            plot = render_additional_data(
                attrs,
                renderer_type=renderer_type,
                title="Additional Data",
                width=400,
                height=300,
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

        # Reset cache to force re-render
        state["last_plot_location_id"] = None

        # Get var_specs from editor
        var_spec_editor = state.get("var_spec_editor")
        var_specs = (
            var_spec_editor.to_var_specs() if var_spec_editor else None
        )

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
            timeseries_plot = pn.pane.Matplotlib(figs[0], tight=True)
            timeseries_pane.clear()
            timeseries_pane.append(timeseries_plot)
            state["last_plot_location_id"] = location_id

    def _make_highlight(
        location_id: int, map_data: pd.DataFrame, lon_col: str, lat_col: str
    ) -> hv.Overlay:
        """Create highlight marker for selected location."""
        if location_id is None or map_data is None:
            return hv.Overlay([])

        row = map_data.loc[map_data[config.id_column] == location_id]
        if row.empty:
            return hv.Overlay([])

        h_df = pd.DataFrame(
            {
                lon_col: [float(row[lon_col].iloc[0])],
                lat_col: [float(row[lat_col].iloc[0])],
                config.id_column: [location_id],
            }
        )

        # Create a more visible highlight with multiple rings
        outer_ring = gv.Points(
            h_df, kdims=[lon_col, lat_col], vdims=[config.id_column]
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
            h_df, kdims=[lon_col, lat_col], vdims=[config.id_column]
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
            h_df, kdims=[lon_col, lat_col], vdims=[config.id_column]
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

    def _auto_clim(values: np.ndarray) -> tuple[float, float]:
        """Compute automatic color limits (2nd and 98th percentile)."""
        valid = values[~np.isnan(values)]
        if len(valid) == 0:
            return (None, None)
        return (float(np.percentile(valid, 2)), float(np.percentile(valid, 98)))

    def _gradient_cmap_and_clim(vmin, vmax):
        """Return the effective colormap and color limits for the selected gradient type."""
        cmap = _cmap_object(cmap_select.value)
        if gradient_select.value == "Sequential":
            return cmap.reversed(), (vmin, vmax)
        if vmin is None or vmax is None:
            return cmap, (None, None)
        max_abs = max(abs(vmin), abs(vmax))
        return cmap, (-max_abs, max_abs)

    def create_on_selection_update():
        """Create a shared selection update callback."""

        def on_selection_update(index):
            """Update UI elements when selection changes."""
            map_data = state.get("map_data")
            if map_data is None or index is None or len(index) == 0:
                state["selected_location_id"] = None
                location_input.value = None
                info_pane.object = ""
                timeseries_pane.clear()
                timeseries_pane.append(
                    pn.pane.Markdown(
                        "**Click a location on the map to view timeseries**"
                    )
                )
                map_data_table_pane.clear()
                map_data_table_pane.append(
                    pn.pane.Markdown("Select a location to view map data")
                )
                return

            location_id = int(map_data.iloc[index[0]][config.id_column])
            state["selected_location_id"] = location_id

            state["updating_location_input"] = True
            try:
                location_input.value = location_id
            finally:
                state["updating_location_input"] = False

            info_pane.object = f"**Selected Location ID:** `{location_id}`"
            load_and_display_location_data(location_id)

        return on_selection_update

    # =============================================================================
    # MAP CREATION
    # =============================================================================

    def create_map(split_dir: str, variable_name: str):
        """Create the initial map with all layers."""
        loading_indicator.value = True

        try:
            # Load data
            map_data = _get_map_data(split_dir, variable_name)

            if map_data.empty:
                return hv.Text(0, 0, "No data available")

            state["map_data"] = map_data

            # Determine actual column names
            lon_cols = [c for c in map_data.columns if c.startswith("lon")]
            lat_cols = [c for c in map_data.columns if c.startswith("lat")]
            actual_lon = lon_cols[0] if lon_cols else config.lon_col
            actual_lat = lat_cols[0] if lat_cols else config.lat_col

            # Compute color limits
            vmin, vmax = _auto_clim(map_data[variable_name].values)
            cmap, clim = _gradient_cmap_and_clim(vmin, vmax)

            # Create points layer
            points = gv.Points(
                map_data,
                kdims=[actual_lon, actual_lat],
                vdims=[config.id_column, variable_name],
            ).opts(
                color=variable_name,
                cmap=cmap,
                size=2,
                width=800,
                height=700,
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
                    ("Lon", f"@{actual_lon}"),
                    ("Lat", f"@{actual_lat}"),
                ],
            )

            state["points_element"] = points

            # Create highlight stream
            highlight_stream = hv.streams.Selection1D(source=points)
            state["highlight_stream"] = highlight_stream

            # Create and store shared selection callback
            if (
                "on_selection_update" not in state
                or state["on_selection_update"] is None
            ):
                state["on_selection_update"] = create_on_selection_update()
            highlight_stream.add_subscriber(state["on_selection_update"])

            def update_highlight(index):
                """Update highlight based on selection."""
                if index and len(index) > 0:
                    location_id = int(map_data.iloc[index[0]][config.id_column])
                    state["selected_location_id"] = location_id
                    return _make_highlight(
                        location_id, map_data, actual_lon, actual_lat
                    )
                else:
                    state["selected_location_id"] = None
                    return hv.Overlay([])

            highlight_layer = hv.DynamicMap(
                update_highlight, streams=[highlight_stream]
            )

            # Render with basemap
            basemap = gv.tile_sources.OSM.opts(
                alpha=0.6,
                width=800,
                height=700,
                responsive=True,
            )
            result = basemap * points * highlight_layer
            state["map_rendered"] = True
            download_map_button.disabled = False
            return result

        finally:
            loading_indicator.value = False

    # =============================================================================
    # DATA UPDATE
    # =============================================================================

    def update_map_data(split_dir: str, variable_name: str):
        """Update map data without re-creating the plot."""
        loading_indicator.value = True

        try:
            saved_location_id = state.get("selected_location_id")

            # Capture current zoom ranges
            saved_ranges = None
            try:
                if hasattr(map_pane, "_plots") and map_pane._plots:
                    old_plot = list(map_pane._plots.values())[0]
                    if hasattr(old_plot, "state"):
                        saved_ranges = {
                            "x_start": old_plot.state.x_range.start,
                            "x_end": old_plot.state.x_range.end,
                            "y_start": old_plot.state.y_range.start,
                            "y_end": old_plot.state.y_range.end,
                        }
            except Exception:
                pass

            # Load new data
            map_data = _get_map_data(split_dir, variable_name)

            if map_data.empty:
                map_pane.object = hv.Text(0, 0, "No data available")
                return

            state["map_data"] = map_data

            # Determine actual column names
            lon_cols = [c for c in map_data.columns if c.startswith("lon")]
            lat_cols = [c for c in map_data.columns if c.startswith("lat")]
            actual_lon = lon_cols[0] if lon_cols else config.lon_col
            actual_lat = lat_cols[0] if lat_cols else config.lat_col

            # Compute new color limits
            vmin, vmax = _auto_clim(map_data[variable_name].values)
            cmap, clim = _gradient_cmap_and_clim(vmin, vmax)

            # Create new points element
            points = gv.Points(
                map_data,
                kdims=[actual_lon, actual_lat],
                vdims=[config.id_column, variable_name],
            ).opts(
                color=variable_name,
                cmap=cmap,
                size=2,
                width=800,
                height=700,
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
                    ("Lon", f"@{actual_lon}"),
                    ("Lat", f"@{actual_lat}"),
                ],
            )

            state["points_element"] = points

            # Create new highlight stream
            highlight_stream = hv.streams.Selection1D(source=points)
            state["highlight_stream"] = highlight_stream

            if "on_selection_update" in state:
                highlight_stream.add_subscriber(state["on_selection_update"])

            def update_highlight(index):
                if index and len(index) > 0:
                    location_id = int(map_data.iloc[index[0]][config.id_column])
                    state["selected_location_id"] = location_id
                    return _make_highlight(
                        location_id, map_data, actual_lon, actual_lat
                    )
                else:
                    state["selected_location_id"] = None
                    return hv.Overlay([])

            highlight_layer = hv.DynamicMap(
                update_highlight, streams=[highlight_stream]
            )

            basemap = gv.tile_sources.OSM.opts(
                alpha=0.6,
                width=800,
                height=700,
                responsive=True,
            )
            map_pane.object = basemap * points * highlight_layer
            state["map_rendered"] = True
            download_map_button.disabled = False

            # Restore zoom ranges
            if saved_ranges:

                def restore_ranges():
                    try:
                        if hasattr(map_pane, "_plots") and map_pane._plots:
                            bokeh_plot = list(map_pane._plots.values())[0]
                            if hasattr(bokeh_plot, "state"):
                                bokeh_plot.state.x_range.start = saved_ranges["x_start"]
                                bokeh_plot.state.x_range.end = saved_ranges["x_end"]
                                bokeh_plot.state.y_range.start = saved_ranges["y_start"]
                                bokeh_plot.state.y_range.end = saved_ranges["y_end"]
                    except Exception:
                        pass

                pn.state.onload(restore_ranges)

            # Restore location selection
            if saved_location_id is not None:
                try:
                    matching_rows = map_data[
                        map_data[config.id_column] == saved_location_id
                    ]
                    if not matching_rows.empty:
                        new_index = matching_rows.index[0]
                        pos = map_data.index.get_loc(new_index)
                        highlight_stream.event(index=[pos])
                except Exception:
                    pass

        finally:
            loading_indicator.value = False

    # =============================================================================
    # CALLBACKS
    # =============================================================================

    def on_split_change(event):
        """Handle split selection change."""
        split_dir = event.new
        state["last_plot_location_id"] = None

        variables = get_variable_names(config, split_dir)
        if variables:
            variable_select.options = variables
            variable_select.value = variables[0]
        else:
            variable_select.options = []
            variable_select.value = None

    def on_variable_change(event):
        """Handle variable selection change."""
        split_dir = split_select.value
        variable_name = event.new
        state["last_plot_location_id"] = None

        if split_dir and variable_name:
            update_map_data(split_dir, variable_name)

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
            update_map_data(split_dir, variable_name)

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

        state["selected_location_id"] = location_id
        info_pane.object = f"**Selected Location ID:** `{location_id}`"

        highlight_stream = state.get("highlight_stream")
        if highlight_stream is not None:
            pos = state["map_data"].index.get_loc(matching.index[0])
            highlight_stream.event(index=[pos])

    # Wire up callbacks
    split_select.param.watch(on_split_change, "value")
    variable_select.param.watch(on_variable_change, "value")
    location_input.param.watch(on_location_input_change, "value")
    gradient_select.param.watch(on_gradient_change, "value")
    cmap_select.param.watch(on_cmap_change, "value")

    # =============================================================================
    # DOWNLOAD HANDLER
    # =============================================================================

    download_handler = DownloadHandler(
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

    # Preload a saved configuration for a new analysis, if provided
    if var_specs:
        var_spec_editor.from_var_specs(var_specs)
    state["var_spec_editor"] = var_spec_editor

    # Use the editor's live layout (automatically updates on add/remove)
    var_spec_pane = var_spec_editor.layout

    # =============================================================================
    # VAR CONFIG IMPORT / EXPORT
    # =============================================================================

    def _generate_var_config_download():
        """Generate the var config JSON for download."""
        try:
            data = var_spec_editor.to_json().encode("utf-8")
            timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
            filename = f"var_config_{timestamp}.json"
            download_var_config_button.filename = filename
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
        button_type="primary",
        icon="download",
        width=170,
    )
    download_var_config_button.callback = _generate_var_config_download

    upload_var_config = pn.widgets.FileInput(
        name="Upload var config",
        accept=".json",
        width=170,
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
            width=300,
            margin=(10, 5),
        ),
        sizing_mode="stretch_width",
        margin=(5, 5),
    )

    # =============================================================================
    # INITIALIZATION
    # =============================================================================

    if split_select.value and variable_select.value:
        result = create_map(split_select.value, variable_select.value)
        map_pane.object = result

    # =============================================================================
    # LAYOUT
    # =============================================================================

    bottom_row = pn.Row(
        map_data_table_pane,
        additional_data_pane,
        sizing_mode="fixed",
        height=420,
        styles={
            "width": "100%",
            "gap": "10px",
        },
        margin=0,
    )

    right_column = pn.Column(
        timeseries_pane,
        bottom_row,
        sizing_mode="fixed",
        styles={
            "width": "50vw",
            "height": "78vh",
            "min-width": "50vw",
            "max-width": "50vw",
            "overflow-y": "auto",
        },
    )

    main_layout = pn.Row(
        map_pane,
        right_column,
        sizing_mode="fixed",
        styles={
            "width": "100vw",
            "margin": "0",
            "padding": "0",
        },
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
        button_type="default",
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
        sizing_mode="fixed",
        styles={
            "position": "relative",
            "width": "50vw",
            "height": "75vh",
            "min-width": "50vw",
            "max-width": "50vw",
        },
    )

    main_layout = pn.Row(
        map_with_config,
        right_column,
        sizing_mode="fixed",
        styles={
            "width": "100vw",
            "margin": "0",
            "padding": "0",
        },
    )

    return pn.Column(
        pn.pane.Markdown(
            "# Dataviewer",
            sizing_mode="stretch_width",
        ),
        controls_row,
        info_pane,
        # Renderer selector for additional data
        pn.Row(
            renderer_selector.layout,
            sizing_mode="fixed",
            height=80,
        ),
        main_layout,
        sizing_mode="stretch_width",
        styles={"margin": "0", "padding": "0"},
    )
