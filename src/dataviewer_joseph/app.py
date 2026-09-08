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

import logging
from concurrent.futures import ThreadPoolExecutor

import geoviews as gv
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


def create_app(config: DataConfig) -> pn.Column:
    """Create the interactive data viewer application.

    Args:
        config: DataConfig instance pointing to data root

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
    }

    # =============================================================================
    # WIDGETS
    # =============================================================================

    available_splits = find_splits(config)
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

    loading_indicator = pn.indicators.LoadingSpinner(
        value=False, size=25, name="Loading…"
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
                )

                if figs and len(figs) > 0:
                    timeseries_plot = pn.pane.Matplotlib(figs[0], tight=True)
                    timeseries_pane.clear()
                    timeseries_pane.append(timeseries_plot)
                    state["last_plot_location_id"] = location_id

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

            # Create points layer
            points = gv.Points(
                map_data,
                kdims=[actual_lon, actual_lat],
                vdims=[config.id_column, variable_name],
            ).opts(
                color=variable_name,
                cmap="viridis",
                size=2,
                width=800,
                height=700,
                responsive=True,
                tools=["tap", "hover", "box_zoom", "wheel_zoom", "reset"],
                colorbar=True,
                clim=(vmin, vmax),
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
            return basemap * points * highlight_layer

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

            # Create new points element
            points = gv.Points(
                map_data,
                kdims=[actual_lon, actual_lat],
                vdims=[config.id_column, variable_name],
            ).opts(
                color=variable_name,
                cmap="viridis",
                size=2,
                width=800,
                height=700,
                responsive=True,
                tools=["tap", "hover", "box_zoom", "wheel_zoom", "reset"],
                colorbar=True,
                clim=(vmin, vmax),
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
    state["var_spec_editor"] = var_spec_editor

    # Use the editor's live layout (automatically updates on add/remove)
    var_spec_pane = var_spec_editor.layout

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

    # Collapsible var_spec editor panel
    var_spec_accordion = pn.Accordion(
        ("Timeseries Configuration", var_spec_pane),
        active=[],
    )

    return pn.Column(
        pn.pane.Markdown(
            "# Dataviewer",
            sizing_mode="stretch_width",
        ),
        pn.Row(
            split_select,
            variable_select,
            location_input,
            loading_indicator,
        ),
        info_pane,
        # Renderer selector for additional data
        pn.Row(
            renderer_selector.layout,
            sizing_mode="fixed",
            height=80,
        ),
        var_spec_accordion,
        main_layout,
        sizing_mode="stretch_width",
        styles={"margin": "0", "padding": "0"},
    )
