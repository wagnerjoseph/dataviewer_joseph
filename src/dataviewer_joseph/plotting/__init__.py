"""Plotting utilities for dataviewer_joseph."""

from .maps import create_interactive_map, add_dynamic_sizing, _auto_clim
from .timeseries import plot_location_timeseries
from .feature_importance import create_feature_importance_plot
from .metrics_table import create_metrics_table
from .renderers import (
    render_additional_data,
    render_bar,
    render_scatter,
    render_table,
    render_histogram,
    render_box,
    RENDERERS,
    get_renderer,
    suggest_renderer,
)
from .selectors import RendererSelector, create_renderer_selector

__all__ = [
    "create_interactive_map",
    "add_dynamic_sizing",
    "_auto_clim",
    "plot_location_timeseries",
    "create_feature_importance_plot",
    "create_metrics_table",
    # Additional data renderers
    "render_additional_data",
    "render_bar",
    "render_scatter",
    "render_table",
    "render_histogram",
    "render_box",
    "RENDERERS",
    "get_renderer",
    "suggest_renderer",
    # Renderer selector
    "RendererSelector",
    "create_renderer_selector",
]
