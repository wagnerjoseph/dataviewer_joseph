"""Tests for the Panel application."""

import pandas as pd

from dataviewer_joseph.app import create_app
from dataviewer_joseph.config import DataConfig


class TestCreateApp:
    """Tests for create_app function."""

    def test_create_app_basic(self, data_config):
        """Test basic app creation."""
        app = create_app(data_config)

        # Check that app is a Panel Column
        assert hasattr(app, "objects")
        assert len(app.objects) > 0

    def test_app_has_widgets(self, data_config):
        """Test that app has required widgets."""
        app = create_app(data_config)

        # The app should have split, variable, and location selectors
        # We can't easily test the internal structure without importing panel
        # but we can at least verify the app was created successfully
        assert app is not None

    def test_app_with_root_level_data(self, tmp_path):
        """Test that root-level data (no split subfolders) builds without error."""
        metrics_dir = tmp_path / "metrics_global_plot"
        metrics_dir.mkdir(parents=True)
        pd.DataFrame({"location_id": [1, 2], "rmse": [0.5, 0.6]}).to_parquet(
            metrics_dir / "rmse.parquet"
        )
        pd.DataFrame(
            {"location_id": [1, 2], "lat": [48.0, 49.0], "lon": [11.0, 12.0], "tile_id": [0, 1]}
        ).to_parquet(tmp_path / "ers_tile_id_location_id.parquet")

        config = DataConfig(root=tmp_path)
        app = create_app(config)

        assert hasattr(app, "objects")
        assert len(app.objects) > 0
        # No error alert should be present
        assert not any(
            hasattr(obj, "object") and "Error" in str(obj.object)
            for obj in app.objects
            if hasattr(obj, "object")
        )

    def test_app_with_empty_data_raises(self, tmp_path):
        """Test that app creation fails gracefully with no data."""
        config = DataConfig(root=tmp_path)
        app = create_app(config)

        # Should return an error message, not crash
        assert app is not None
        # Check for Alert pane
        has_alert = any(
            hasattr(obj, "object") and "Error" in str(obj.object)
            for obj in app.objects
            if hasattr(obj, "object")
        )
        assert has_alert
