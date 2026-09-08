"""Map-data table showing all variable values for a selected location."""

import logging

import pandas as pd
import panel as pn

logger = logging.getLogger(__name__)


def create_map_data_table(
    values: pd.Series | dict,
    width: int = 250,
    height: int = 300,
) -> pn.pane:
    """Create a sorted key-value table of map-data variables for a location.

    Args:
        values: Series or dict mapping variable names to values
        width: Table width
        height: Table height

    Returns:
        Panel DataFrame pane with variable/value columns
    """
    if values is None or (hasattr(values, "empty") and values.empty):
        return pn.pane.Markdown("No map data available", width=width, height=height)

    if isinstance(values, dict):
        if not values:
            return pn.pane.Markdown("No map data available", width=width, height=height)
        items = sorted(values.items(), key=lambda x: str(x[0]))
    else:
        items = [(k, v) for k, v in values.items()]
        items.sort(key=lambda x: str(x[0]))

    df = pd.DataFrame(items, columns=["Variable", "Value"])

    # Format numeric values concisely
    if "Value" in df.columns and pd.api.types.is_numeric_dtype(df["Value"]):
        df["Value"] = df["Value"].apply(
            lambda x: (
                f"{x:.6f}" if pd.notna(x) and abs(x) < 0.01
                else f"{x:.4f}" if pd.notna(x) and abs(x) < 1
                else f"{x:.3f}" if pd.notna(x) else "NaN"
            )
        )

    return pn.pane.DataFrame(df, width=width, height=height)
