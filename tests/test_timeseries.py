"""Tests for timeseries plotting."""

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from dataviewer_joseph.data import DataIndex, load_timeseries_for_location
from dataviewer_joseph.plotting.timeseries import plot_location_timeseries


class TestPlotLocationTimeseries:
    """Tests for plot_location_timeseries function."""

    def test_basic_plot(self, data_config):
        """Test basic timeseries plotting."""
        index = DataIndex(data_config)
        location_id = index.locations["location_id"].iloc[0]

        ts_data = load_timeseries_for_location(
            data_config, "split_2020_2022", location_id
        )

        figs = plot_location_timeseries(
            data=ts_data,
            location_ids=[location_id],
            time_col="time",
            location_id_col="location_id",
        )

        # plot_time_series returns a list of figures
        assert isinstance(figs, list)
        assert len(figs) > 0
        assert hasattr(figs[0], "get_axes")
        for fig in figs:
            plt.close(fig)

    def test_plot_with_var_specs(self, data_config):
        """Test plotting with custom var_specs."""
        index = DataIndex(data_config)
        location_id = index.locations["location_id"].iloc[0]

        ts_data = load_timeseries_for_location(
            data_config, "split_2020_2022", location_id
        )

        var_specs = [
            {
                "name": "backscatter40",
                "label": "Backscatter",
                "color": "#0000ff",
                "line_width": 2.0,
            },
            {
                "name": "lai",
                "label": "LAI",
                "color": "#00ff00",
            },
        ]

        figs = plot_location_timeseries(
            data=ts_data,
            location_ids=[location_id],
            var_specs=var_specs,
        )

        assert isinstance(figs, list)
        assert len(figs) > 0
        for fig in figs:
            plt.close(fig)

    def test_plot_multiple_locations(self, data_config):
        """Test plotting multiple locations."""
        index = DataIndex(data_config)
        location_ids = index.locations["location_id"].iloc[:2].tolist()

        # Load data for both locations
        ts_data_list = []
        for loc_id in location_ids:
            ts = load_timeseries_for_location(data_config, "split_2020_2022", loc_id)
            if ts is not None:
                ts_data_list.append(ts)

        if ts_data_list:
            ts_data = pd.concat(ts_data_list, ignore_index=True)

            figs = plot_location_timeseries(
                data=ts_data,
                location_ids=location_ids,
            )

            assert len(figs) == len(location_ids)
            for fig in figs:
                plt.close(fig)

    def test_plot_no_time_column_raises(self, data_config):
        """Test that plotting without time column raises an error."""
        df = pd.DataFrame({"location_id": [1, 2, 3], "var1": [4, 5, 6]})

        with pytest.raises(ValueError, match="Time column"):
            plot_location_timeseries(
                data=df,
                location_ids=[1],
            )
