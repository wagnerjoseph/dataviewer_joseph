"""dataviewer_joseph - Interactive geospatial timeseries data viewer.

Provides an interactive Panel/GeoViews application for exploring
spatiotemporal Earth observation data with automatic discovery of
splits, variables, and locations from parquet files.

Features:
- Interactive map with click-to-select location
- Timeseries via plotting_joseph with interactive var_specs editor
- Map data table with all variables for the selected location
- Additional data with selectable renderers
- Auto-discovery of data structure
"""

from .app import create_app
from .config import DataConfig
from .data import (
    DataIndex,
    find_splits,
    generate_dummy_data,
    get_timeseries_variables,
    get_variable_names,
    load_additional_data_for_location,
    load_location_coordinates,
    load_map_data_for_location,
    load_timeseries_for_location,
    load_variable_data,
)
from .prepare import prepare_dataviewer_data
from .var_spec_editor import VarSpecEditor, create_var_spec_editor

__version__ = "0.2.0"

__all__ = [
    "DataConfig",
    "DataIndex",
    "VarSpecEditor",
    "create_app",
    "create_var_spec_editor",
    "find_splits",
    "generate_dummy_data",
    "get_timeseries_variables",
    "get_variable_names",
    "load_additional_data_for_location",
    "load_location_coordinates",
    "load_map_data_for_location",
    "load_timeseries_for_location",
    "load_variable_data",
    "prepare_dataviewer_data",
]
