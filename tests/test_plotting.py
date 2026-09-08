"""Tests for plotting utilities."""

import pandas as pd

from dataviewer_joseph.plotting.map_data_table import create_map_data_table


class TestCreateMapDataTable:
    """Tests for create_map_data_table function."""

    def test_table_basic(self):
        """Test basic map data table."""
        values = pd.Series({"rmse": 0.5, "mae": 0.4, "pearson": 0.8})
        table = create_map_data_table(values)
        assert table is not None

    def test_table_dict(self):
        """Test map data table from a dict."""
        values = {"elevation": 500.0, "slope": 12.5}
        table = create_map_data_table(values)
        assert table is not None
        assert hasattr(table, "object")

    def test_table_empty(self):
        """Test map data table with no data."""
        table = create_map_data_table({})
        assert table is not None

    def test_table_none(self):
        """Test map data table with None."""
        table = create_map_data_table(None)
        assert table is not None
