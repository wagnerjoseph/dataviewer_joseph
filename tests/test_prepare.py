"""Tests for data preparation."""

import pandas as pd
import pytest

from dataviewer_joseph.prepare import discover_splits, prepare_dataviewer_data


class TestDiscoverSplits:
    """Tests for discover_splits function."""

    def _make_tile(self, directory, tile_id, extra_cols=None):
        directory.mkdir(parents=True, exist_ok=True)
        cols = {"location_id": [1, 2]}
        if extra_cols:
            cols.update(extra_cols)
        pd.DataFrame(cols).to_parquet(directory / f"{tile_id}.parquet", index=False)

    def test_common_splits(self, tmp_path):
        """Test with matching split subfolders."""
        for name in ["split_1", "split_2"]:
            self._make_tile(tmp_path / "map" / name, "0001")
            self._make_tile(tmp_path / "ts" / name, "0001")
        splits = discover_splits(tmp_path / "map", tmp_path / "ts")
        assert splits == ["split_1", "split_2"]

    def test_root_level_single_split(self, tmp_path):
        """Test that tiles directly in the dirs yield a single implicit split."""
        self._make_tile(tmp_path / "map", "0001", {"correlation": [0.5, 0.6]})
        self._make_tile(tmp_path / "ts", "0001", {"time": pd.to_datetime(["2020-01-01"] * 2)})
        splits = discover_splits(tmp_path / "map", tmp_path / "ts")
        assert splits == ["."]

    def test_empty_dirs_raises(self, tmp_path):
        """Test that empty dirs raise a clear error."""
        (tmp_path / "map").mkdir()
        (tmp_path / "ts").mkdir()
        with pytest.raises(ValueError, match="No common splits"):
            discover_splits(tmp_path / "map", tmp_path / "ts")


class TestPrepareDataviewerData:
    """Tests for prepare_dataviewer_data."""

    def test_root_level_prepare(self, tmp_path):
        """Integration: root-level map + timeseries produce a single-split output."""
        lookup = tmp_path / "lookup"
        lookup.mkdir()
        pd.DataFrame(
            {"location_id": [1, 2], "lat": [48.0, 49.0], "lon": [11.0, 12.0], "tile_id": ["0001", "0001"]}
        ).to_parquet(lookup / "ers_tile_id_location_id.parquet")

        map_dir = tmp_path / "map"
        map_dir.mkdir()
        pd.DataFrame({"location_id": [1, 2], "correlation": [0.5, 0.6]}).to_parquet(
            map_dir / "0001.parquet"
        )

        ts_dir = tmp_path / "ts"
        ts_dir.mkdir()
        pd.DataFrame(
            {
                "location_id": [1, 2],
                "time": pd.to_datetime(["2020-01-01", "2020-02-01"]),
                "backscatter40": [1.0, 2.0],
            }
        ).to_parquet(ts_dir / "0001.parquet")

        output = prepare_dataviewer_data(
            lookup_dir=lookup,
            map_data_dir=map_dir,
            timeseries_dir=ts_dir,
            output_dir=tmp_path / "out",
            output_name="dataviewer_auto",
        )

        out_dir = tmp_path / "out" / "dataviewer_auto"
        assert output == out_dir
        assert (out_dir / "ers_tile_id_location_id.parquet").exists()
        assert (out_dir / "metrics_global_plot" / "correlation.parquet").exists()
        assert (out_dir / "timeseries" / "0001.parquet").exists()
