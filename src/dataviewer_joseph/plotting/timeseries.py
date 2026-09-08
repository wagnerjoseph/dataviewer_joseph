"""Timeseries plotting using plotting_joseph."""

import logging
import pandas as pd

logger = logging.getLogger(__name__)


def plot_location_timeseries(
    data: pd.DataFrame,
    location_ids: list[int],
    var_specs: list[dict] | None = None,
    time_col: str = "time",
    location_id_col: str = "location_id",
    figsize: tuple[int, int] = (10, 5),
    font_scale: float = 1.0,
    show_plot: bool = False,
    save_dir: str | None = None,
    master_lookup: str | None = None,
) -> list:
    """Plot timeseries data using plotting_joseph.plot_time_series.

    Args:
        data: DataFrame with location_id, time, and variable columns
        location_ids: List of location IDs to plot
        var_specs: Variable specifications for plotting_joseph (see var_spec_editor)
        time_col: Name of time column
        location_id_col: Name of location ID column
        figsize: Base figure size
        font_scale: Font size scale factor
        show_plot: Whether to display plots interactively
        save_dir: Directory to save figures
        master_lookup: Path to master lookup for country/neighbor data

    Returns:
        List of matplotlib Figure objects (one per location)
    """
    try:
        from plotting_joseph import plot_time_series
    except ImportError as e:
        logger.error(f"Could not import plotting_joseph: {e}")
        raise ImportError(
            "plotting_joseph is required. Install with: pip install plotting-joseph"
        ) from e

    # Prepare data
    df = data.copy()
    if time_col not in df.columns:
        raise ValueError(
            f"Time column '{time_col}' not found. Available: {df.columns.tolist()}"
        )
    if location_id_col not in df.columns:
        raise ValueError(f"Location ID column '{location_id_col}' not found")

    # Ensure time is datetime
    if not pd.api.types.is_datetime64_any_dtype(df[time_col]):
        df[time_col] = pd.to_datetime(df[time_col])

    # Call plotting_joseph's function
    figs = plot_time_series(
        data=df,
        var_specs=var_specs,
        location_ids=location_ids,
        figsize=figsize,
        font_scale=font_scale,
        show_plot=show_plot,
        save_dir=save_dir,
        master_lookup=master_lookup,
    )

    return figs
