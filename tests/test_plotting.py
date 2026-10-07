"""Tests for plotting utilities."""

import math

import numpy as np
import pandas as pd
import pytest

from dataviewer_joseph.plotting.map_data_table import create_map_data_table
from dataviewer_joseph.plotting.maps import (
    find_nearest_location,
    haversine_km,
    web_mercator_to_latlon,
)


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


class TestHaversineKm:
    """Tests for haversine_km function."""

    def test_one_degree_latitude(self):
        """One degree of latitude is about 111.2 km."""
        assert haversine_km(0.0, 0.0, 1.0, 0.0) == pytest.approx(111.19, abs=0.1)

    def test_zero_distance(self):
        """Distance between identical points is zero."""
        assert haversine_km(48.0, 11.0, 48.0, 11.0) == pytest.approx(0.0)

    def test_known_city_pair(self):
        """Berlin to Munich is about 504 km."""
        d = haversine_km(52.52, 13.405, 48.1375, 11.575)
        assert d == pytest.approx(504.2, abs=1.0)

    def test_symmetry(self):
        """Distance is symmetric in argument order."""
        assert haversine_km(52.52, 13.405, 48.1375, 11.575) == pytest.approx(
            haversine_km(48.1375, 11.575, 52.52, 13.405)
        )

    def test_vectorized(self):
        """Array inputs return elementwise distances."""
        d = haversine_km(0.0, 0.0, np.array([0.0, 1.0]), np.array([0.0, 0.0]))
        assert d.shape == (2,)
        assert d[0] == pytest.approx(0.0)
        assert d[1] == pytest.approx(111.19, abs=0.1)

    def test_nan_coordinates_propagate(self):
        """NaN coordinates produce NaN distances."""
        assert np.isnan(haversine_km(float("nan"), 0.0, 0.0, 0.0))
        d = haversine_km(0.0, 0.0, np.array([np.nan, 1.0]), np.array([0.0, 0.0]))
        assert np.isnan(d[0])
        assert d[1] == pytest.approx(111.19, abs=0.1)


class TestFindNearestLocation:
    """Tests for find_nearest_location function."""

    def test_returns_nearest_within_limit(self):
        """The nearest location within the limit is found."""
        data = pd.DataFrame({"lon": [10.0, 10.2], "lat": [50.0, 50.1]})
        pos = find_nearest_location(data, "lon", "lat", lon=10.05, lat=50.02)
        assert pos == 0

    def test_returns_none_beyond_limit(self):
        """None is returned when the nearest location is too far away."""
        data = pd.DataFrame({"lon": [10.0], "lat": [50.0]})
        pos = find_nearest_location(data, "lon", "lat", lon=12.0, lat=52.0)
        assert pos is None

    def test_custom_max_distance(self):
        """The maximum distance is configurable."""
        data = pd.DataFrame({"lon": [10.0], "lat": [50.0]})
        # ~7.1 km east of the location
        assert (
            find_nearest_location(
                data, "lon", "lat", lon=10.1, lat=50.0, max_distance_km=10.0
            )
            == 0
        )
        assert (
            find_nearest_location(
                data, "lon", "lat", lon=10.1, lat=50.0, max_distance_km=5.0
            )
            is None
        )

    def test_nan_coordinates_ignored(self):
        """Rows with NaN coordinates are skipped."""
        data = pd.DataFrame({"lon": [np.nan, 10.0], "lat": [np.nan, 50.0]})
        pos = find_nearest_location(data, "lon", "lat", lon=10.0, lat=50.0)
        assert pos == 1

    def test_all_nan_returns_none(self):
        """None is returned when all coordinates are NaN."""
        data = pd.DataFrame({"lon": [np.nan], "lat": [np.nan]})
        assert find_nearest_location(data, "lon", "lat", lon=10.0, lat=50.0) is None

    def test_empty_data_returns_none(self):
        """None is returned for empty or missing data."""
        data = pd.DataFrame({"lon": [], "lat": []})
        assert find_nearest_location(data, "lon", "lat", lon=10.0, lat=50.0) is None
        assert find_nearest_location(None, "lon", "lat", lon=10.0, lat=50.0) is None

    def test_returns_positional_index(self):
        """The returned index is positional, not the DataFrame label."""
        data = pd.DataFrame({"lon": [10.0, 11.0], "lat": [50.0, 51.0]}, index=[7, 3])
        assert find_nearest_location(data, "lon", "lat", lon=10.0, lat=50.0) == 0
        assert find_nearest_location(data, "lon", "lat", lon=11.0, lat=51.0) == 1


class TestWebMercatorToLatlon:
    """Tests for web_mercator_to_latlon function."""

    def test_origin(self):
        """The Web Mercator origin maps to (0, 0)."""
        assert web_mercator_to_latlon(0.0, 0.0) == (0.0, 0.0)

    def test_roundtrip(self):
        """Projected coordinates map back to the original lat/lon."""
        R = 6378137
        x = math.radians(10.0) * R
        y = R * math.log(math.tan(math.radians(90.0 + 50.0) / 2))
        lat, lon = web_mercator_to_latlon(x, y)
        assert lat == pytest.approx(50.0, abs=1e-6)
        assert lon == pytest.approx(10.0, abs=1e-6)
