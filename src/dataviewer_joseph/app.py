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
from typing import Any

import geoviews as gv
from cmcrameri import cm as crameri_cm
from plotting_joseph import plot_map
import holoviews as hv
import numpy as np
import pandas as pd
import panel as pn
import param

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
from .facets import FacetSchema
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


class SelectedLocationStream(hv.streams.Stream):
    """Stream carrying the currently selected location_id (None = none)."""

    location_id = param.Integer(default=None, allow_None=True)


def _tag_marker_renderer(plot: Any, element: Any) -> None:
    """Tag a marker element's renderer so dynamic sizing leaves it alone.

    The selected-location marker shows fixed-size rings; the map's
    ``add_dynamic_sizing`` hook resizes data glyphs on zoom and must not
    shrink the marker rings to the regular point size.
    """
    try:
        renderer = plot.handles.get("glyph_renderer") or plot.handles.get("glyph_renderers", [None])[0]
    except Exception:
        renderer = None
    if renderer is not None:
        renderer._dataviewer_fixed_size = True


def _match_map_aspect(plot: Any, element: Any) -> None:
    """Keep the live map's geographic proportions (equal m/m axis scales).

    Without ``match_aspect`` bokeh stretches the ranges to the pane's
    pixel box, so a wide window flattens the map horizontally. The map
    plots Web Mercator coordinates (meters on both axes), so
    ``match_aspect=True`` renders it undistorted inside the available
    space, like the downloaded map.
    """
    try:
        plot.state.match_aspect = True
    except Exception:
        pass


def _valid_timeseries_specs(specs, data):
    """Keep var_specs whose columns exist in ``data`` (splits differ).

    The var-spec editor holds the specs of whichever split it was built
    for; when a location of another split is plotted (or the plot
    regenerates), specs referencing missing columns must be dropped —
    otherwise plotting_joseph raises KeyError.
    """
    cols = set(data.columns)
    return [
        s
        for s in specs
        if s.get("name")
        and s.get("name") in cols
        and (s.get("add_to") is None or s["add_to"] in cols)
    ]


pn.extension()
hv.extension("bokeh")
gv.extension("bokeh")

# GPU (WebGL) rendering keeps the map interactive with large point counts:
# while dragging/zooming bokeh redraws the whole point cloud every frame,
# which the 2D canvas backend cannot do cheaply. Downloads and the colorbar
# are matplotlib-based and are unaffected by the browser renderer.
hv.renderer("bokeh").webgl = True


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


def _live_bokeh_plot(map_pane):
    """Return the currently rendered Bokeh plot for the active session.

    Panel 1.9 stores ``(plot, child_pane)`` tuples in ``pane._plots`` and a
    pane can hold plots for several sessions at once (``pn.serve`` shares one
    app instance). Prefer the plot whose model belongs to the current
    session's document; fall back to the most recently rendered one.
    """
    try:
        plots = getattr(map_pane, "_plots", None)
        if not plots:
            return None
    except Exception:
        return None

    cur_doc = None
    try:
        cur_doc = pn.state.curdoc
    except Exception:
        pass

    newest = None
    for value in plots.values():
        plot = value[0] if isinstance(value, (list, tuple)) else value
        if plot is None:
            continue
        state = getattr(plot, "state", None)
        if state is None:
            continue
        if cur_doc is not None and getattr(state, "document", None) is cur_doc:
            return plot
        newest = plot
    return newest


def _plot_extent(plot) -> tuple[float, float, float, float] | None:
    """Map extent of a plot/model as ``(lon_min, lon_max, lat_min, lat_max)``.

    Accepts either a HoloViews/Bokeh plot (``.state``) or a Bokeh figure
    model directly. Reads Web Mercator ranges (no clamping).
    """
    try:
        s = getattr(plot, "state", plot)
        x_start, x_end = s.x_range.start, s.x_range.end
        y_start, y_end = s.y_range.start, s.y_range.end
        if None in (x_start, x_end, y_start, y_end):
            return None
        lat_min, lon_min = web_mercator_to_latlon(float(x_start), float(y_start))
        lat_max, lon_max = web_mercator_to_latlon(float(x_end), float(y_end))
        return (lon_min, lon_max, lat_min, lat_max)
    except Exception:
        pass
    return None


def _ranges_to_extent(ranges: dict) -> tuple[float, float, float, float] | None:
    """Convert saved Web Mercator ranges to ``(lon_min, lon_max, lat_min, lat_max)``."""
    try:
        x_start, x_end = float(ranges["x_start"]), float(ranges["x_end"])
        y_start, y_end = float(ranges["y_start"]), float(ranges["y_end"])
        lat_min, lon_min = web_mercator_to_latlon(x_start, y_start)
        lat_max, lon_max = web_mercator_to_latlon(x_end, y_end)
        return (lon_min, lon_max, lat_min, lat_max)
    except Exception:
        pass
    return None


def _live_extent(map_pane) -> tuple[float, float, float, float] | None:
    """Current map extent as ``(lon_min, lon_max, lat_min, lat_max)``."""
    try:
        return _plot_extent(_live_bokeh_plot(map_pane))
    except Exception:
        pass
    return None


def _pin_map_figure(fig, extent: tuple[float, float, float, float]) -> None:
    """Pin a map figure's main axes to the requested lon/lat extent.

    ``plot_map`` sets the axes limits before drawing the selection marker;
    with global coastlines drawn, the later marker ``plot`` re-autoscales
    the axes back out to the globe. Re-pinning after the plot is built
    keeps the downloaded map on the viewer window.
    """
    ax = fig.axes[0]
    lon_min, lon_max, lat_min, lat_max = extent
    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)
    ax.autoscale(False)


def _thin_download_coastlines(fig) -> None:
    """Thin ``plot_map``'s black coastlines so the download looks cleaner.

    The map download keeps a white background (no sea/land tint); only
    ``plot_map``'s thick black coastlines (linewidth 1) are reduced. The
    selection marker is a red point and must not be touched.
    """
    ax = fig.axes[0]
    for line in ax.lines:
        color = line.get_color()
        is_black = color in ("black", "k", "0.0") or (
            isinstance(color, tuple) and tuple(color)[:3] == (0.0, 0.0, 0.0)
        )
        if is_black and (line.get_linewidth() or 0) > 0.8:
            line.set_linewidth(0.35)


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
        return _live_extent(self.map_pane)

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

            # Current dataviewer extent: always the window currently shown
            # in the viewer. The live plot ranges are authoritative; the
            # recorded map_zoom is only a fallback (e.g. no live plot yet).
            # The live frame already keeps equal degrees per pixel (the
            # aspect_ratio sizing in add_dynamic_sizing), and plot_map
            # derives the figure from the lon/lat spans, so the download
            # reproduces the viewer's extent and proportions 1:1.
            extent = self._read_live_extent() or self.state.get("map_zoom")
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

            fig = plot_map(
                data=map_data,
                var=variable_name,
                master_lookup=str(self.config.lookup_path),
                cmap=cmap,
                value_range=value_range,
                extent=extent,
                grid_sampling=0.1,
                add_coastlines=True,
                add_marker=add_marker,
                show_plot=False,
                dpi=300,
            )

            # plot_map pins the view to ``extent`` up front, but the marker
            # plotted afterwards can re-autoscale the axes back out to the
            # coastlines' global extent. Re-pin now that all artists are
            # drawn, so the download always shows the viewer window.
            _thin_download_coastlines(fig)
            _pin_map_figure(fig, extent)
            fig.savefig(tmp_path, dpi=300, bbox_inches="tight")

            data = tmp_path.read_bytes()
            tmp_path.unlink(missing_ok=True)

            self.download_map_button.filename = filename
            return BytesIO(data)

        except Exception as e:
            import traceback

            logger.error(
                f"Error generating map download: {e}\n{traceback.format_exc()}"
            )
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
        "map_zoom": None,
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

    # =============================================================================
    # VARIABLE FACETS (optional grouping, only when facet_vocab is configured)
    # =============================================================================

    facet_vocab = config.facet_vocab

    map_facet_row = pn.Row(sizing_mode="stretch_width", visible=False)
    map_facet_selects: dict[str, pn.widgets.Select] = {}
    state["map_facet_schema"] = None

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

            if tile_id is not None and not pd.isna(tile_id):
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
                var_specs = var_spec_editor.to_var_specs() if var_spec_editor else None
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

                if (
                    map_data_for_location is not None
                    and not map_data_for_location.empty
                ):
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
            additional_data_pane.append(pn.pane.Markdown(f"Error rendering: {e!s}"))

    def regenerate_timeseries():
        """Re-render timeseries plot with current var_specs (from cached ts_data)."""
        ts_data = state.get("ts_data")
        location_id = state.get("ts_location_id")

        if ts_data is None or location_id is None:
            return  # No data to replot

        # Get var_specs from editor (keep only columns of THIS split)
        var_spec_editor = state.get("var_spec_editor")
        var_specs = var_spec_editor.to_var_specs() if var_spec_editor else None
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

    def _update_map_zoom(extent):
        """Record the newest live extent (drives the map download)."""
        if extent is not None:
            state["map_zoom"] = extent

    def _mark_selection(location_id: int | None):
        """Publish the selected location to the map's marker layer."""
        stream = state.get("highlight_stream")
        if stream is not None and stream.location_id != location_id:
            stream.event(location_id=location_id)

    def select_location(pos: int, location_id: int):
        """Select a location: update state, widgets, and load its data."""
        state["selected_location_id"] = location_id

        state["updating_location_input"] = True
        try:
            location_input.value = location_id
        finally:
            state["updating_location_input"] = False

        info_pane.object = f"**Selected Location ID:** `{location_id}`"
        _mark_selection(location_id)
        load_and_display_location_data(location_id)

    def clear_selection():
        """Clear the current selection: marker, timeseries, tables, downloads."""
        state["selected_location_id"] = None

        state["updating_location_input"] = True
        try:
            location_input.value = None
        finally:
            state["updating_location_input"] = False

        state["current_timeseries_fig"] = None
        download_timeseries_button.disabled = True

        info_pane.object = "**Status:** Ready - Select a location to view details"
        timeseries_pane.clear()
        timeseries_pane.append(
            pn.pane.Markdown("**Click a location on the map to view timeseries**")
        )
        map_data_table_pane.clear()
        map_data_table_pane.append(
            pn.pane.Markdown("Select a location to view map data")
        )
        additional_data_pane.clear()
        additional_data_pane.append(
            pn.pane.Markdown("Select a location to view additional data")
        )
        _mark_selection(None)

    def create_tap_handler(
        map_data: pd.DataFrame,
        lon_col: str,
        lat_col: str,
    ):
        """Create a tap callback that snaps map clicks to the nearest location."""

        def on_tap(x, y):
            """Snap a click anywhere on the map to the nearest location.

            Clicking near a point selects it; clicking anywhere else (no
            location within the snap distance) clears the current selection."""
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
                clear_selection()
                info_pane.object = (
                    f"**No location within {SNAP_DISTANCE_KM:g} km of click — "
                    "selection cleared"
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
            plot = _live_bokeh_plot(map_pane)
            if plot is None:
                return None
            s = getattr(plot, "state", plot)
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
                fill_alpha=0.9,
                hover_fill_alpha=1.0,
                hover_line_alpha=1.0,
                responsive=True,
                tools=["tap", "hover", "box_zoom", "wheel_zoom", "reset"],
                colorbar=True,
                clim=clim,
                title=f"{variable_name} - {split_dir}",
                active_tools=["wheel_zoom"],
                hooks=[
                    _match_map_aspect,
                    lambda p, e, upd=_update_map_zoom: add_dynamic_sizing(
                        p, e, on_extent_change=upd
                    ),
                ],
                hover_tooltips=[
                    ("Location ID", f"@{config.id_column}"),
                    ("Value", f"@{variable_name}"),
                    ("Lon", f"@{config.lon_col}"),
                    ("Lat", f"@{config.lat_col}"),
                ],
            )

            def _marker_rings(marker_df):
                """The three ring Points of the selection marker."""
                rings = []
                for ring_size, fill_alpha, line_width, line_alpha, line_color in (
                    (30, 0.2, 3, 0.5, "red"),
                    (20, 0.3, 2, 0.6, "red"),
                    (12, 1.0, 2, 1.0, "white"),
                ):
                    rings.append(
                        gv.Points(
                            marker_df,
                            kdims=[config.lon_col, config.lat_col],
                            vdims=[config.id_column],
                        ).opts(
                            size=ring_size,
                            fill_alpha=fill_alpha,
                            line_alpha=line_alpha,
                            line_width=line_width,
                            line_color=line_color,
                            color="red",
                            marker="circle",
                            tools=[],
                            hooks=[_tag_marker_renderer],
                        )
                    )
                return hv.Overlay(rings, group="SelectedMarker")

            empty_marker_df = pd.DataFrame(
                columns=[config.lon_col, config.lat_col, config.id_column],
                dtype=float,
            )

            def update_marker(location_id=None, **_):
                """Marker overlay for the selected location (or empty rings).

                The frame type never changes (always an overlay of three
                Points): if it jumped between an empty overlay and a Points
                overlay, HoloViews would rebuild the bokeh figure and reset
                the zoom/pan to the global autofit.
                """
                map_data_for_marker = state.get("map_data")
                if location_id is None or map_data_for_marker is None:
                    return _marker_rings(empty_marker_df)
                row = map_data_for_marker[
                    map_data_for_marker[config.id_column] == location_id
                ]
                if row.empty:
                    return _marker_rings(empty_marker_df)
                h_df = pd.DataFrame(
                    {
                        config.lon_col: [float(row[config.lon_col].iloc[0])],
                        config.lat_col: [float(row[config.lat_col].iloc[0])],
                        config.id_column: [int(location_id)],
                    }
                )
                return _marker_rings(h_df)

            selection_stream = SelectedLocationStream(
                location_id=state.get("selected_location_id")
            )
            state["highlight_stream"] = selection_stream
            marker_layer = hv.DynamicMap(update_marker, streams=[selection_stream])

            # Snap clicks anywhere on the map to the nearest location
            tap_stream = hv.streams.Tap(source=points)
            state["tap_stream"] = tap_stream
            tap_stream.add_subscriber(
                create_tap_handler(map_data, config.lon_col, config.lat_col)
            )

            basemap = gv.tile_sources.OSM.opts(alpha=0.25, responsive=True)
            map_pane.object = basemap * points * marker_layer
            download_map_button.disabled = False

            # Restore zoom ranges after the pane has re-rendered. Panel swaps
            # the plot model asynchronously, so run the restore after the
            # swap — repeatedly, because the first attempt can still hit the
            # old model and the swap itself can reset the ranges.
            if saved_ranges:

                def restore_ranges():
                    try:
                        plot = _live_bokeh_plot(map_pane)
                        if plot is None:
                            return
                        s = getattr(plot, "state", plot)
                        s.x_range.start = saved_ranges["x_start"]
                        s.x_range.end = saved_ranges["x_end"]
                        s.y_range.start = saved_ranges["y_start"]
                        s.y_range.end = saved_ranges["y_end"]
                        # The saved ranges are the view the user had; record
                        # them so a download matches the map right away.
                        extent = _ranges_to_extent(saved_ranges)
                        if extent:
                            state["map_zoom"] = extent
                    except Exception:
                        pass

                def apply_restore():
                    restore_ranges()
                    doc = pn.state.curdoc
                    if doc is None:
                        return
                    # Re-apply after the model swap propagates; the last call
                    # wins, so even if an earlier attempt targeted the old
                    # figure, the new one ends up with the user's ranges.
                    for delay in (200, 600):
                        try:
                            doc.add_timeout_callback(restore_ranges, delay)
                        except Exception:
                            break

                doc = pn.state.curdoc
                if doc is not None and doc.session_context is not None:
                    pn.state.execute(apply_restore, schedule=True)
                else:
                    pn.state.onload(apply_restore)

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
            ts_names = get_timeseries_variables(config, split_dir)
            ts_schema = FacetSchema(ts_names, facet_vocab) if facet_vocab else None
            editor.update_available_variables(ts_names, facet_schema=ts_schema)

        # Rebuild the facet filters for the new split's variable names.
        rebuild_map_facets(split_dir)

    # =============================================================================
    # FACET FILTER ROW (map)
    # =============================================================================

    def apply_map_facet_filters():
        """Refilter the map variable list from the facet dropdowns."""
        schema = state.get("map_facet_schema")
        if schema is None or not map_facet_row.visible:
            return
        selection = {
            facet: widget.value
            for facet, widget in map_facet_selects.items()
            if widget.value != "All"
        }
        filtered = schema.filter_names(selection)
        variable_select.options = filtered
        current = variable_select.value
        if not filtered:
            variable_select.value = None
        elif current not in filtered:
            variable_select.value = filtered[0]

    def rebuild_map_facets(split_dir: str | None):
        """(Re)build the facet filter row for a split (map variables)."""
        names = get_variable_names(config, split_dir) if split_dir else []
        schema = FacetSchema(names, facet_vocab) if facet_vocab else None
        state["map_facet_schema"] = schema
        map_facet_selects.clear()
        if schema is None or not schema.active():
            map_facet_row.visible = False
            map_facet_row.objects = []
            # Restore the unfiltered list (a previous faceted split may have
            # narrowed it).
            variable_select.options = names
            return
        widgets = []
        for facet in schema.active_facets():
            values = schema.facet_values(facet)
            widget = pn.widgets.Select(
                label=facet.title(),
                options=["All"] + values,
                value="All",
                width=150,
            )
            widget.param.watch(lambda event: apply_map_facet_filters(), "value")
            map_facet_selects[facet] = widget
            widgets.append(widget)
        map_facet_row.objects = widgets
        map_facet_row.visible = True
        apply_map_facet_filters()

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
            clear_selection()
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
    ts_facet_schema = FacetSchema(ts_variables, facet_vocab) if facet_vocab else None

    # Create editor with callback to regenerate plot on config change
    var_spec_editor = VarSpecEditor(
        available_variables=ts_variables,
        on_config_change=regenerate_timeseries,
        facet_schema=ts_facet_schema,
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
            logger.warning(f"Could not auto-import most recent var config: {e}")
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

            logger.error(f"Error generating var config: {e}\n{traceback.format_exc()}")
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

            logger.error(f"Error importing var config: {e}\n{traceback.format_exc()}")
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

    rebuild_map_facets(split_select.value)

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

    controls = [
        variable_select,
        location_input,
        gradient_select,
        cmap_select,
        loading_indicator,
        download_map_button,
        download_timeseries_button,
    ]
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

    layout = pn.Column(
        pn.pane.Markdown(
            "# Dataviewer",
            sizing_mode="stretch_width",
        ),
        map_facet_row,
        controls_row,
        info_pane,
        main_layout,
        sizing_mode="stretch_both",
        styles={"margin": "0", "padding": "0"},
    )
    # Reference for tests that need to inspect per-app state (map_zoom,
    # selected_location_id, highlight stream). No runtime consumers.
    layout._dv_state = state
    return layout
