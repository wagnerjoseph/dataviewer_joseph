"""dataviewer_joseph - Interactive geospatial timeseries data viewer.

Provides an interactive Panel/GeoViews application for exploring
spatiotemporal Earth observation data with automatic discovery of
splits, variables, and locations from parquet files.

Features:
- Interactive map with click-to-select location
- Timeseries via plotting_joseph with interactive var_specs editor
- Feature importance bar charts
- Metrics comparison table
- Auto-discovery of data structure
"""

from .config import DataConfig
from .data import (
    DataIndex,
    find_splits,
    get_variable_names,
    load_location_coordinates,
    load_variable_data,
    load_timeseries_for_location,
    load_feature_importance_for_location,
    load_additional_data_for_location,
    load_metrics_from_tile,
    get_timeseries_variables,
    generate_dummy_data,
)
from .var_spec_editor import VarSpecEditor, create_var_spec_editor
from .app import create_app
from .prepare import prepare_dataviewer_data

__version__ = "0.2.0"

__all__ = [
    "DataConfig",
    "DataIndex",
    "VarSpecEditor",
    "create_app",
    "create_var_spec_editor",
    "prepare_dataviewer_data",
    "find_splits",
    "get_variable_names",
    "load_location_coordinates",
    "load_variable_data",
    "load_timeseries_for_location",
    "load_feature_importance_for_location",
    "load_additional_data_for_location",
    "load_metrics_from_tile",
    "get_timeseries_variables",
    "generate_dummy_data",
]
