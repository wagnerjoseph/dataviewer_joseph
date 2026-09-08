"""Feature importance plotting."""

import logging
import pandas as pd
import holoviews as hv
import panel as pn

logger = logging.getLogger(__name__)

hv.extension("bokeh")


def create_feature_importance_plot(
    fi_data: dict,
    fi_col_prefix: str = "fi_",
    width: int = 300,
    height: int = 250,
) -> pn.Row:
    """Create two horizontal bar charts for feature importance.

    Args:
        fi_data: Dictionary with model names as keys, Series/DataFrames as values
        fi_col_prefix: Prefix for feature importance columns
        width: Width of each plot
        height: Height of each plot

    Returns:
        Panel Row with two bar charts
    """
    if not fi_data:
        return pn.Column(pn.pane.Markdown("No feature importance data available"))

    plots = []
    model_names = ["without_lag", "with_lag"]

    for model_name in model_names:
        if model_name not in fi_data or fi_data[model_name] is None:
            plots.append(
                hv.Text(0, 0, f"No data for {model_name} model").opts(
                    title=f"Feature Importance ({model_name.replace('_', ' ').title()})",
                    width=width,
                    height=height,
                )
            )
            continue

        fi_series = fi_data[model_name]
        fi_cols = [col for col in fi_series.index if str(col).startswith(fi_col_prefix)]

        if not fi_cols:
            plots.append(
                hv.Text(0, 0, f"No FI columns for {model_name}").opts(
                    title=f"Feature Importance ({model_name.replace('_', ' ').title()})",
                    width=width,
                    height=height,
                )
            )
            continue

        # Build feature importance dict
        fi_dict = {}
        for col in fi_cols:
            clean_name = str(col)[len(fi_col_prefix) :]
            # Clean up lag suffixes
            clean_name = (
                clean_name.replace("_lag1m", " lag1")
                .replace("_lag2m", " lag2")
                .replace("_lag3m", " lag3")
                .replace("_lag4m", " lag4")
                .replace("_lag5m", " lag5")
                .replace("_lag6m", " lag6")
            )
            value = fi_series[col]
            if pd.notna(value) and value > 0:
                fi_dict[clean_name] = value

        if not fi_dict:
            plots.append(
                hv.Text(0, 0, "No positive FI values").opts(
                    title=f"Feature Importance ({model_name.replace('_', ' ').title()})",
                    width=width,
                    height=height,
                )
            )
            continue

        # Sort descending
        fi_sorted = sorted(fi_dict.items(), key=lambda x: x[1], reverse=True)
        fi_df = pd.DataFrame(fi_sorted, columns=["feature", "importance"])

        # Create horizontal bar chart
        plot = hv.Bars(fi_df, kdims="feature", vdims="importance").opts(
            title=f"Feature Importance ({model_name.replace('_', ' ').title()})",
            xlabel="Feature",
            ylabel="Importance",
            width=width,
            height=height,
            invert_axes=True,
            color="steelblue" if model_name == "without_lag" else "coral",
            xrotation=45,
        )
        plots.append(plot)

    return pn.Row(
        *plots,
        styles={"gap": "10px"},
        margin=0,
        sizing_mode="fixed",
        width=width * 2 + 10,
    )
