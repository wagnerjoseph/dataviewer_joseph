"""Metrics table plotting."""

import logging
import pandas as pd
import panel as pn

logger = logging.getLogger(__name__)


def create_metrics_table(
    metrics: dict[str, dict[str, float]],
    metric_models: dict[str, dict[str, tuple[str, str]]] | None = None,
) -> pn.pane.DataFrame:
    """Create a 3x3 table showing metric values for all models.

    Marks the best value in each metric column with ★.

    Args:
        metrics: Nested dictionary: {model: {metric: value}}
        metric_models: Model configuration from DataConfig (optional)

    Returns:
        Panel DataFrame pane with formatted values
    """
    if not metrics:
        return pn.pane.Markdown("No metrics data available")

    # Determine metric names from first model
    metric_names = list(next(iter(metrics.values())).keys())

    # Find best values for each metric
    best_models = {}
    for metric in metric_names:
        values = {
            model: data[metric] for model, data in metrics.items() if metric in data
        }
        if not values:
            continue

        # Determine direction (min or max is better)
        direction = "min"  # default
        if metric_models:
            for model_cfg in metric_models.values():
                if metric in model_cfg:
                    direction = model_cfg[metric][1]
                    break

        if direction == "min":
            best_model = min(values, key=values.get)
        else:
            best_model = max(values, key=values.get)
        best_models[metric] = best_model

    # Create rows with ★ symbol for best values
    rows = []
    for model_name, model_data in metrics.items():
        row = {"Model": model_name}
        for metric in metric_names:
            if metric not in model_data:
                row[metric] = "N/A"
                continue

            value = model_data[metric]
            value_str = f"{value:.3f}"

            # Add ★ symbol for best values
            if metric in best_models and best_models[metric] == model_name:
                value_str = f"★{value_str}"

            row[metric] = value_str

        rows.append(row)

    # Create DataFrame
    df = pd.DataFrame(rows)

    # Create Panel DataFrame pane
    table_pane = pn.pane.DataFrame(
        df,
        width=250,
        height=300,
    )

    return table_pane
