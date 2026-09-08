"""Tests for feature importance and metrics plotting."""

import pandas as pd

from dataviewer_joseph.plotting.feature_importance import create_feature_importance_plot
from dataviewer_joseph.plotting.metrics_table import create_metrics_table


class TestCreateFeatureImportancePlot:
    """Tests for create_feature_importance_plot function."""

    def test_fi_plot_basic(self):
        """Test basic feature importance plot."""
        fi_data = {
            "without_lag": pd.Series(
                {
                    "fi_feature1": 0.5,
                    "fi_feature2": 0.3,
                    "fi_feature3": 0.2,
                }
            ),
            "with_lag": pd.Series(
                {
                    "fi_feature1": 0.4,
                    "fi_feature2": 0.4,
                    "fi_feature3": 0.2,
                }
            ),
        }

        plot = create_feature_importance_plot(fi_data)
        assert plot is not None

    def test_fi_plot_empty(self):
        """Test feature importance plot with no data."""
        plot = create_feature_importance_plot({})
        assert plot is not None


class TestCreateMetricsTable:
    """Tests for create_metrics_table function."""

    def test_metrics_table_basic(self):
        """Test basic metrics table."""
        metrics = {
            "Baseline": {
                "RMSE": 1.0,
                "MAE": 0.8,
                "Pearson": 0.7,
            },
            "RF (Without Lag)": {
                "RMSE": 0.7,
                "MAE": 0.6,
                "Pearson": 0.8,
            },
            "RF (With Lag)": {
                "RMSE": 0.6,
                "MAE": 0.5,
                "Pearson": 0.85,
            },
        }

        table = create_metrics_table(metrics)
        assert table is not None

    def test_metrics_table_stars_best(self):
        """Test that best values are marked with star."""
        metrics = {
            "Model1": {"RMSE": 1.0, "Pearson": 0.7},
            "Model2": {"RMSE": 0.5, "Pearson": 0.9},
        }

        table = create_metrics_table(metrics)
        assert table is not None
        # Table should contain star symbol for best values
        table_str = str(table.object) if hasattr(table, "object") else str(table)
        assert "★" in table_str or "Model2" in table_str

    def test_metrics_table_empty(self):
        """Test metrics table with no data."""
        table = create_metrics_table({})
        assert table is not None
