"""Tests for data loading and indexing."""

import pandas as pd

from dataviewer_joseph.config import DataConfig
from dataviewer_joseph.data import (
    DataIndex,
    find_splits,
    generate_dummy_data,
    get_timeseries_variables,
    get_variable_names,
    load_additional_data_for_location,
    load_location_coordinates,
    load_map_data_for_location,
    load_timeseries_for_location,
    load_variable_data,
)


class TestFindSplits:
    """Tests for find_splits function."""

    def test_finds_splits(self, temp_data_dir):
        """Test that splits are discovered correctly."""
        config = DataConfig(root=temp_data_dir)
        splits = find_splits(config)
        assert len(splits) == 2
        assert "split_2020_2022" in splits
        assert "split_2023_2024" in splits

    def test_no_splits(self, tmp_path):
        """Test with empty directory."""
        config = DataConfig(root=tmp_path)
        splits = find_splits(config)
        assert len(splits) == 0


class TestGetVariableNames:
    """Tests for get_variable_names function."""

    def test_get_variables(self, data_config):
        """Test variable discovery."""
        variables = get_variable_names(data_config, "split_2020_2022")
        assert len(variables) > 0
        assert "rmse" in variables


class TestLoadLocationCoordinates:
    """Tests for load_location_coordinates function."""

    def test_load_coordinates(self, data_config):
        """Test loading location coordinates."""
        coords = load_location_coordinates(data_config)
        assert len(coords) > 0
        assert "location_id" in coords.columns
        assert "lat" in coords.columns
        assert "lon" in coords.columns


class TestDataIndex:
    """Tests for DataIndex class."""

    def test_discover_splits(self, data_config):
        """Test split discovery."""
        index = DataIndex(data_config)
        assert len(index.splits) == 2

    def test_load_locations(self, data_config):
        """Test location loading."""
        index = DataIndex(data_config)
        assert index.locations is not None
        assert len(index.locations) > 0


class TestLoadVariableData:
    """Tests for load_variable_data function."""

    def test_load_variable(self, data_config):
        """Test loading variable data."""
        var_data = load_variable_data(data_config, "split_2020_2022", "rmse")
        assert len(var_data) > 0
        assert "location_id" in var_data.columns
        assert "rmse" in var_data.columns


class TestLoadTimeseries:
    """Tests for load_timeseries_for_location function."""

    def test_load_timeseries(self, data_config):
        """Test loading timeseries for a location."""
        index = DataIndex(data_config)
        location_id = index.locations["location_id"].iloc[0]

        ts_data = load_timeseries_for_location(
            data_config, "split_2020_2022", location_id
        )

        assert ts_data is not None
        assert len(ts_data) > 0
        assert "time" in ts_data.columns

    def test_load_nonexistent_location(self, data_config):
        """Test loading timeseries for a location that doesn't exist."""
        ts_data = load_timeseries_for_location(data_config, "split_2020_2022", -99999)
        assert ts_data is None


class TestLoadMapDataForLocation:
    """Tests for load_map_data_for_location function."""

    def test_load_map_data(self, data_config):
        """Test loading all map variables for a location."""
        index = DataIndex(data_config)
        location_id = index.locations["location_id"].iloc[0]

        values = load_map_data_for_location(
            data_config, "split_2020_2022", location_id
        )

        assert values is not None
        assert len(values) > 0
        assert "rmse" in values.index

    def test_load_nonexistent_location(self, data_config):
        """Test loading map data for a location that doesn't exist."""
        values = load_map_data_for_location(
            data_config, "split_2020_2022", -99999
        )
        assert values is None or values.empty


class TestLoadAdditionalData:
    """Tests for load_additional_data_for_location function."""

    def test_load_additional_data(self, data_config):
        """Test loading additional data for a location."""
        index = DataIndex(data_config)
        location_id = index.locations["location_id"].iloc[0]
        tile_id = index.locations["tile_id"].iloc[0]

        attrs = load_additional_data_for_location(
            data_config,
            "split_2020_2022",
            location_id,
            tile_id,
        )

        assert attrs is not None
        assert len(attrs) > 0


class TestGetTimeseriesVariables:
    """Tests for get_timeseries_variables function."""

    def test_get_ts_variables(self, data_config):
        """Test getting timeseries variable names."""
        ts_vars = get_timeseries_variables(data_config, "split_2020_2022")
        assert len(ts_vars) > 0
        assert "backscatter40" in ts_vars


class TestGenerateDummyData:
    """Tests for generate_dummy_data function."""

    def test_generate_basic(self, tmp_path):
        """Test basic dummy data generation."""
        config = generate_dummy_data(tmp_path, n_locations=20, n_tiles=2)

        assert config.root == tmp_path
        assert config.lookup_path.exists()

    def test_generate_structure(self, tmp_path):
        """Test that all required subfolders are created."""
        config = generate_dummy_data(tmp_path, n_locations=10, n_tiles=1)

        # Check lookup
        assert config.lookup_path.exists()

        # Check split structure
        for split in ["split_2020_2022", "split_2023_2024"]:
            split_dir = tmp_path / split
            assert (split_dir / "metrics_global_plot").exists()
            assert (split_dir / "additional_data").exists()
            assert (split_dir / "timeseries").exists()

    def test_generate_reproducible(self, tmp_path):
        """Test that data generation is reproducible."""
        config1 = generate_dummy_data(tmp_path / "run1", seed=42)
        config2 = generate_dummy_data(tmp_path / "run2", seed=42)

        lookup1 = pd.read_parquet(config1.lookup_path)
        lookup2 = pd.read_parquet(config2.lookup_path)

        assert lookup1.equals(lookup2)
