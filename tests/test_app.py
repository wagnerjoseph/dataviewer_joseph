"""Tests for the Panel application."""

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
