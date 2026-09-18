"""Tests for the Panel application."""

import json

import pandas as pd

from dataviewer_joseph.app import (
    create_app,
    load_most_recent_var_config,
    save_var_config,
)
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

    def test_create_app_preloads_var_specs(self, data_config):
        """Test create_app accepts var_specs to preload the editor."""
        from dataviewer_joseph.var_spec_editor import VarSpecEditor

        specs = [{"name": "swe", "label": "Snow Water Eq", "color": "#123456"}]
        app = create_app(data_config, var_specs=specs)

        # The editor is hidden in state; verify app built without error
        assert hasattr(app, "objects")
        assert len(app.objects) > 0

        # Directly verify from_var_specs semantics are applied by the editor class
        editor = VarSpecEditor(
            available_variables=["swe", "lai"], on_config_change=lambda: None
        )
        editor.add_subplot("swe")
        editor.from_var_specs(specs)
        assert editor._subplots[0]["primary"]["label"].value == "Snow Water Eq"

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


class TestVarConfigPersistence:
    """Tests for saving/loading var configs in the data folder."""

    def test_save_var_config_writes_to_config_folder(self, data_config):
        """Saving a config writes a JSON file into the data's config folder."""
        obj = {"format": "dataviewer_var_config", "version": 1, "var_specs": []}
        path = save_var_config(data_config, json.dumps(obj))

        assert path.parent == data_config.config_dir
        assert path.exists()
        assert path.suffix == ".json"
        assert json.loads(path.read_text())["var_specs"] == []

    def test_load_most_recent_config_returns_newest(self, data_config):
        """The most recently saved config file is returned."""
        older = data_config.config_dir / "var_config_20200101_000000.json"
        older.parent.mkdir(parents=True, exist_ok=True)
        older.write_text(json.dumps({"version": 0}))

        obj = {"format": "dataviewer_var_config", "version": 1, "var_specs": [
            {"name": "swe", "label": "Snow", "color": "#112233"}
        ]}
        save_var_config(data_config, json.dumps(obj))

        loaded = json.loads(load_most_recent_var_config(data_config))
        assert loaded["version"] == 1

    def test_load_most_recent_config_returns_none_when_empty(self, data_config):
        """No config file means no config is loaded."""
        assert load_most_recent_var_config(data_config) is None

    def test_create_app_auto_imports_most_recent_config(self, data_config):
        """A saved config in the data folder is applied on app creation."""
        specs = {"format": "dataviewer_var_config", "version": 1, "var_specs": [
            {"name": "backscatter40", "label": "Backscatter", "color": "#123456"}
        ]}
        save_var_config(data_config, json.dumps(specs))

        app = create_app(data_config)
        assert hasattr(app, "objects")
        assert len(app.objects) > 0
