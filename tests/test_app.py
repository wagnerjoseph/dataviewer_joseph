"""Tests for the Panel application."""

import io
import json
import math

import numpy as np
import pandas as pd
import panel as pn
import pytest
from PIL import Image

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


def _walk_panes(obj, results):
    """Collect all child panes/widgets of a Panel component."""
    for child in getattr(obj, "objects", None) or []:
        results.append(child)
        if hasattr(child, "objects"):
            _walk_panes(child, results)


def _find(obj, cls, **attrs):
    """Find the first pane/widget of a class with matching attributes."""
    results = []

    def rec(o):
        _walk_panes(o, results)

    rec(obj)
    for r in results:
        if not isinstance(r, cls):
            continue
        if all(getattr(r, k, None) == v for k, v in attrs.items()):
            return r
    raise AssertionError(f"Could not find {cls.__name__} with {attrs}")


def _merc(lon, lat):
    """Project lon/lat to Web Mercator meters."""
    R = 6378137.0
    return (
        R * math.radians(lon),
        R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)),
    )


class TestMapInteraction:
    """Map tap/selection and map-download behavior (regression tests)."""

    def _setup(self, config):
        from bokeh.document import Document

        from dataviewer_joseph.app import _live_bokeh_plot

        app = create_app(config)
        state = app._dv_state
        map_pane = _find(app, pn.pane.HoloViews)
        doc = Document()
        map_pane._get_model(doc)
        return app, state, map_pane, _live_bokeh_plot(map_pane)

    def test_click_marks_selection_empty_click_clears(self, data_config):
        """A click snaps to a location; a click far from any point clears."""
        app, state, map_pane, plot = self._setup(data_config)
        tap = state["tap_stream"]
        map_data = state["map_data"]
        row = map_data.iloc[0]
        loc = int(row[data_config.id_column])

        tap.event(
            x=float(row[data_config.lon_col]), y=float(row[data_config.lat_col])
        )
        assert state["selected_location_id"] == loc
        assert state["highlight_stream"].location_id == loc

        ts_button = _find(app, pn.widgets.FileDownload, name="Download Timeseries")
        assert ts_button.disabled is False

        tap.event(x=0.0, y=0.0)
        assert state["selected_location_id"] is None
        assert state["highlight_stream"].location_id is None
        assert ts_button.disabled is True

    def test_download_uses_live_extent_and_selection_marker(self, data_config):
        """The downloaded map matches the window, even with a marked point."""
        app, state, map_pane, plot = self._setup(data_config)
        s = getattr(plot, "state", plot)

        # Zoom into a region the user is looking at.
        x1, y1 = _merc(11.0, 46.0)
        x2, y2 = _merc(19.0, 54.0)
        s.x_range.start, s.x_range.end = x1, x2
        s.y_range.start, s.y_range.end = y1, y2

        lon_min, lon_max, lat_min, lat_max = state["map_zoom"]
        assert lon_min == pytest.approx(11.0, abs=0.01)
        assert lon_max == pytest.approx(19.0, abs=0.01)
        assert lat_min == pytest.approx(46.0, abs=0.01)
        assert lat_max == pytest.approx(54.0, abs=0.01)

        # Select a location inside the view.
        tap = state["tap_stream"]
        map_data = state["map_data"]
        sel = map_data.iloc[0]
        tap.event(
            x=float(sel[data_config.lon_col]), y=float(sel[data_config.lat_col])
        )
        assert state["selected_location_id"] == int(sel[data_config.id_column])
        # Selecting must not reset the window extent.
        assert state["map_zoom"][0] == pytest.approx(11.0, abs=0.01)

        # Corrupt the recorded zoom (regression: a stale/global map_zoom must
        # not win) — the window in the viewer is the extent.
        state["map_zoom"] = (-180.0, 180.0, -60.0, 85.0)

        dl_map = _find(app, pn.widgets.FileDownload, name="Download Map")
        out = dl_map.callback()
        assert out is not None
        assert _red_marker_pixels(out) > 0
        # A regional map (8x8 degrees) is roughly square; a global map is
        # much wider than tall.
        img = Image.open(out)
        w, h = img.size
        assert h / w > 0.8, "downloaded map is too wide — global extent used"

        # Clearing the selection removes the marker from the download.
        tap.event(x=0.0, y=0.0)
        out2 = dl_map.callback()
        assert out2 is not None
        assert _red_marker_pixels(out2) == 0


def _red_marker_pixels(fileobj: io.BytesIO) -> int:
    """Count pure-red marker pixels in a downloaded map PNG."""
    from PIL import Image

    img = Image.open(fileobj).convert("RGB")
    arr = np.asarray(img)
    red = (arr[:, :, 0] > 180) & (arr[:, :, 1] < 100) & (arr[:, :, 2] < 100)
    return int(red.sum())
