"""Pluggable renderers for additional data visualization.

Provides multiple rendering options for per-location attribute data:
- bar: Horizontal bar chart (good for ranked numeric values)
- scatter: Scatter plot (good for comparing two numeric attributes)
- table: Key-value table (good for mixed types or detailed inspection)
- histogram: Histogram distribution (good for single numeric attribute)
- box: Box plot (good for statistical summary)

Each renderer takes attribute data and returns a Panel/HoloViews object.
"""

import logging
from collections.abc import Callable
from typing import Any

import holoviews as hv
import numpy as np
import pandas as pd
import panel as pn

logger = logging.getLogger(__name__)

hv.extension("bokeh")


def render_bar(
    attrs: pd.Series | dict[str, Any],
    title: str = "Additional Data",
    width: int = 400,
    height: int = 300,
    color: str = "steelblue",
    invert_axes: bool = True,
) -> hv.Element:
    """Render attributes as horizontal bar chart.
    
    Args:
        attrs: Series or dict mapping attribute names to values
        title: Plot title
        width: Plot width
        height: Plot height
        color: Bar color
        invert_axes: If True, show horizontal bars
        
    Returns:
        HoloViews Bars element
    """
    if isinstance(attrs, pd.Series):
        attrs_dict = attrs.to_dict()
    else:
        attrs_dict = dict(attrs)
    
    # Filter to numeric, positive values
    filtered = {
        k: v for k, v in attrs_dict.items()
        if pd.api.types.is_numeric_dtype(type(v)) and pd.notna(v) and v != 0
    }
    
    if not filtered:
        return hv.Text(0, 0, "No numeric data available").opts(
            title=title, width=width, height=height
        )
    
    # Sort by value descending
    sorted_items = sorted(filtered.items(), key=lambda x: x[1], reverse=True)
    df = pd.DataFrame(sorted_items, columns=["attribute", "value"])
    
    plot = hv.Bars(df, kdims="attribute", vdims="importance" if "importance" in df.columns else "value").opts(
        title=title,
        xlabel="Attribute",
        ylabel="Value",
        width=width,
        height=height,
        invert_axes=invert_axes,
        color=color,
        xrotation=45,
    )
    
    return plot


def render_scatter(
    attrs: pd.Series | dict[str, Any],
    title: str = "Additional Data",
    width: int = 400,
    height: int = 300,
    color: str = "steelblue",
    size: int = 8,
) -> hv.Element:
    """Render attributes as scatter plot.
    
    Args:
        attrs: Series or dict mapping attribute names to values
        title: Plot title
        width: Plot width
        height: Plot height
        color: Point color
        size: Point size
        
    Returns:
        HoloViews Scatter element
    """
    if isinstance(attrs, pd.Series):
        attrs_dict = attrs.to_dict()
    else:
        attrs_dict = dict(attrs)
    
    # Filter to numeric values
    filtered = {
        k: v for k, v in attrs_dict.items()
        if pd.api.types.is_numeric_dtype(type(v)) and pd.notna(v)
    }
    
    if len(filtered) < 2:
        return hv.Text(0, 0, "Need ≥2 numeric values for scatter").opts(
            title=title, width=width, height=height
        )
    
    # Create scatter with index as x, value as y
    items = list(filtered.items())
    df = pd.DataFrame({
        "index": range(len(items)),
        "attribute": [str(k) for k, v in items],
        "value": [v for k, v in items],
    })
    
    plot = hv.Scatter(df, kdims="index", vdims="value").opts(
        title=title,
        xlabel="Attribute Index",
        ylabel="Value",
        width=width,
        height=height,
        color=color,
        size=size,
        tools=["hover"],
    ).opts(
        hover_tooltips=[
            ("Attribute", "@attribute"),
            ("Value", "@value"),
        ]
    )
    
    return plot


def render_table(
    attrs: pd.Series | dict[str, Any],
    title: str = "Additional Data",
    width: int = 400,
    height: int = 300,
) -> pn.pane.DataFrame:
    """Render attributes as a key-value table.
    
    Good for mixed types or detailed inspection.
    
    Args:
        attrs: Series or dict mapping attribute names to values
        title: Table title
        width: Table width
        height: Table height
        
    Returns:
        Panel DataFrame pane
    """
    if isinstance(attrs, pd.Series):
        df = attrs.to_frame(name="value")
        df.index.name = "attribute"
        df = df.reset_index()
    else:
        df = pd.DataFrame(list(attrs.items()), columns=["attribute", "value"])
    
    if df.empty:
        return pn.pane.Markdown("No data available", width=width, height=height)
    
    # Format numeric values
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if df[col].abs().max() < 0.01:
            df[col] = df[col].apply(lambda x: f"{x:.6f}" if pd.notna(x) else "NaN")
        elif df[col].abs().max() < 1:
            df[col] = df[col].apply(lambda x: f"{x:.4f}" if pd.notna(x) else "NaN")
        else:
            df[col] = df[col].apply(lambda x: f"{x:.3f}" if pd.notna(x) else "NaN")
    
    table = pn.pane.DataFrame(
        df,
        width=width,
        height=height,
    )
    
    return table


def render_histogram(
    attrs: pd.Series | dict[str, Any],
    title: str = "Additional Data",
    width: int = 400,
    height: int = 300,
    color: str = "steelblue",
    bins: int = 20,
) -> hv.Element:
    """Render attribute values as histogram.
    
    Args:
        attrs: Series or dict mapping attribute names to values
        title: Plot title
        width: Plot width
        height: Plot height
        color: Bar color
        bins: Number of histogram bins
        
    Returns:
        HoloViews Histogram element
    """
    if isinstance(attrs, pd.Series):
        values = attrs.dropna().values
    else:
        values = np.array([v for v in attrs.values() if pd.notna(v)])
    
    if len(values) < 2:
        return hv.Text(0, 0, "Need ≥2 values for histogram").opts(
            title=title, width=width, height=height
        )
    
    if not pd.api.types.is_numeric_dtype(values.dtype):
        return hv.Text(0, 0, "Non-numeric data").opts(
            title=title, width=width, height=height
        )
    
    plot = hv.Histogram(np.histogram(values, bins=bins)).opts(
        title=title,
        xlabel="Value",
        ylabel="Frequency",
        width=width,
        height=height,
        color=color,
    )
    
    return plot


def render_box(
    attrs: pd.Series | dict[str, Any],
    title: str = "Additional Data",
    width: int = 400,
    height: int = 300,
    color: str = "steelblue",
) -> hv.Element:
    """Render attribute values as box plot.
    
    Args:
        attrs: Series or dict mapping attribute names to values
        title: Plot title
        width: Plot width
        height: Plot height
        color: Box color
        
    Returns:
        HoloViews BoxWhisker element
    """
    if isinstance(attrs, pd.Series):
        values = attrs.dropna().values
    else:
        values = np.array([v for v in attrs.values() if pd.notna(v)])
    
    if len(values) < 4:
        return hv.Text(0, 0, "Need ≥4 values for box plot").opts(
            title=title, width=width, height=height
        )
    
    if not pd.api.types.is_numeric_dtype(values.dtype):
        return hv.Text(0, 0, "Non-numeric data").opts(
            title=title, width=width, height=height
        )
    
    # Create DataFrame for BoxWhisker
    df = pd.DataFrame({"value": values, "category": "All"})
    
    plot = hv.BoxWhisker(df, kdims="category", vdims="value").opts(
        title=title,
        ylabel="Value",
        width=width,
        height=height,
        color=color,
    )
    
    return plot


# Registry of available renderers
RENDERERS: dict[str, Callable] = {
    "bar": render_bar,
    "scatter": render_scatter,
    "table": render_table,
    "histogram": render_histogram,
    "box": render_box,
}


def get_renderer(renderer_type: str) -> Callable:
    """Get renderer function by name.
    
    Args:
        renderer_type: Name of renderer ("bar", "scatter", "table", "histogram", "box")
        
    Returns:
        Renderer function
        
    Raises:
        ValueError: If renderer type not found
    """
    if renderer_type not in RENDERERS:
        available = ", ".join(RENDERERS.keys())
        raise ValueError(f"Unknown renderer type: {renderer_type}. Available: {available}")
    return RENDERERS[renderer_type]


def suggest_renderer(attrs: pd.Series | dict[str, Any]) -> str:
    """Suggest best renderer type based on data characteristics.
    
    Args:
        attrs: Series or dict of attributes
        
    Returns:
        Suggested renderer type name
    """
    if isinstance(attrs, pd.Series):
        values = attrs.dropna()
        n_values = len(values)
        is_numeric = pd.api.types.is_numeric_dtype(values.dtype)
    else:
        values = pd.Series([v for v in attrs.values() if pd.notna(v)])
        n_values = len(values)
        is_numeric = pd.api.types.is_numeric_dtype(values.dtype) if len(values) > 0 else False
    
    # No data
    if n_values == 0:
        return "table"
    
    # Single value → table
    if n_values == 1:
        return "table"
    
    # Non-numeric → table
    if not is_numeric:
        return "table"
    
    # Few numeric values (2-5) → bar chart
    if n_values <= 5:
        return "bar"
    
    # Many numeric values → histogram or box
    if n_values > 20:
        return "histogram"
    
    # Medium numeric values → bar or box
    return "bar"


def render_additional_data(
    attrs: pd.Series | dict[str, Any],
    renderer_type: str | None = None,
    title: str = "Additional Data",
    width: int = 400,
    height: int = 300,
    **kwargs,
) -> hv.Element | pn.pane.DataFrame:
    """Render additional data using specified or auto-suggested renderer.
    
    Args:
        attrs: Series or dict of attribute names to values
        renderer_type: Renderer type ("bar", "scatter", "table", "histogram", "box").
                      If None, auto-suggests based on data.
        title: Plot title
        width: Plot width
        height: Plot height
        **kwargs: Additional arguments passed to renderer
        
    Returns:
        HoloViews element or Panel DataFrame pane
    """
    if renderer_type is None:
        renderer_type = suggest_renderer(attrs)
    
    renderer = get_renderer(renderer_type)
    
    # Call renderer with common parameters
    return renderer(
        attrs,
        title=title,
        width=width,
        height=height,
        **kwargs,
    )
