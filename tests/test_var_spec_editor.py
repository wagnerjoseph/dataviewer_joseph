"""Tests for var_spec_editor."""

from dataviewer_joseph.var_spec_editor import VarSpecEditor, create_var_spec_editor


class TestVarSpecEditor:
    """Tests for VarSpecEditor class."""

    def test_create_editor(self):
        """Test creating an editor."""
        editor = VarSpecEditor(available_variables=["var1", "var2", "var3"])
        assert editor.available_variables == ["var1", "var2", "var3"]
        assert len(editor._subplots) == 0

    def test_add_subplot(self):
        """Test adding a subplot with primary variable."""
        editor = VarSpecEditor(available_variables=["var1", "var2"])
        editor.add_subplot("var1")
        assert len(editor._subplots) == 1
        assert editor._subplots[0]["primary"]["name"].value == "var1"
        assert len(editor._subplots[0]["overlays"]) == 0

    def test_remove_subplot_by_id(self):
        """Test removing a subplot by stable ID (regression for identity bug)."""
        editor = VarSpecEditor(available_variables=["var1", "var2", "var3"])
        id1 = editor.add_subplot("var1")
        id2 = editor.add_subplot("var2")
        editor.add_subplot("var3")
        assert len(editor._subplots) == 3

        editor.remove_subplot(id2)
        assert len(editor._subplots) == 2
        remaining_names = [sp["primary"]["name"].value for sp in editor._subplots]
        assert remaining_names == ["var1", "var3"]

        editor.add_subplot("var2")
        assert len(editor._subplots) == 3

        editor.remove_subplot(id1)
        assert len(editor._subplots) == 2
        remaining_names = [sp["primary"]["name"].value for sp in editor._subplots]
        assert remaining_names == ["var3", "var2"]

    def test_add_variable_to_subplot(self):
        """Test adding an overlay variable to a subplot."""
        editor = VarSpecEditor(available_variables=["var1", "var2"])
        subplot_id = editor.add_subplot("var1")
        editor.add_variable(subplot_id, "var2")

        assert len(editor._subplots) == 1
        assert len(editor._subplots[0]["overlays"]) == 1
        assert editor._subplots[0]["overlays"][0]["name"].value == "var2"

    def test_remove_variable_from_subplot(self):
        """Test removing an overlay variable from a subplot."""
        editor = VarSpecEditor(available_variables=["var1", "var2", "var3"])
        subplot_id = editor.add_subplot("var1")
        editor.add_variable(subplot_id, "var2")
        editor.add_variable(subplot_id, "var3")
        assert len(editor._subplots[0]["overlays"]) == 2

        overlay_id = id(editor._subplots[0]["overlays"][0])
        editor.remove_variable(subplot_id, overlay_id)
        assert len(editor._subplots[0]["overlays"]) == 1

    def test_to_var_specs_basic(self):
        """Test converting widgets to var_specs."""
        editor = VarSpecEditor(available_variables=["var1", "var2"])
        editor.add_subplot("var1")

        editor._subplots[0]["primary"]["label"].value = "Variable 1"
        editor._subplots[0]["primary"]["color"].value = "#ff0000"
        editor._subplots[0]["primary"]["line_width"].value = 2.0

        specs = editor.to_var_specs()
        assert len(specs) == 1
        assert specs[0]["name"] == "var1"
        assert specs[0]["label"] == "Variable 1"
        assert specs[0]["color"] == "#ff0000"
        assert specs[0]["line_width"] == 2.0
        assert "add_to" not in specs[0]

    def test_to_var_specs_with_overlay(self):
        """Test overlay configuration in var_specs."""
        editor = VarSpecEditor(available_variables=["var1", "var2"])
        subplot_id = editor.add_subplot("var1")
        editor.add_variable(subplot_id, "var2")

        editor._subplots[0]["overlays"][0]["add_second_axis"].value = True
        editor._subplots[0]["overlays"][0]["align_zero"].value = True

        specs = editor.to_var_specs()
        assert len(specs) == 2
        assert specs[0]["name"] == "var1"
        assert specs[1]["name"] == "var2"
        assert specs[1]["add_to"] == "var1"
        assert specs[1]["add_second_axis"] is True
        assert specs[1]["align_zero"] is True

    def test_to_var_specs_thresholds(self):
        """Test threshold configuration in var_specs."""
        editor = VarSpecEditor(available_variables=["var1"])
        editor.add_subplot("var1")

        editor._subplots[0]["primary"]["lower_threshold_val"].value = 0.5
        editor._subplots[0]["primary"]["lower_threshold_color"].value = "#00ff00"
        editor._subplots[0]["primary"]["upper_threshold_val"].value = 1.5
        editor._subplots[0]["primary"]["upper_threshold_color"].value = "#0000ff"

        specs = editor.to_var_specs()
        assert len(specs) == 1
        assert specs[0]["lower_treshold"] == (0.5, "#00ff00")
        assert specs[0]["upper_treshold"] == (1.5, "#0000ff")

    def test_primary_rename_updates_overlay_add_to(self):
        """Test that renaming primary variable updates overlay add_to."""
        editor = VarSpecEditor(available_variables=["var1", "var2", "var3"])
        subplot_id = editor.add_subplot("var1")
        editor.add_variable(subplot_id, "var2")

        editor._subplots[0]["primary"]["name"].value = "var3"

        specs = editor.to_var_specs()
        assert len(specs) == 2
        assert specs[0]["name"] == "var3"
        assert specs[1]["add_to"] == "var3"

    def test_color_and_label_on_same_line(self):
        """Test that color and label widgets exist in variable row."""
        editor = VarSpecEditor(available_variables=["var1"])
        editor.add_subplot("var1")

        primary = editor._subplots[0]["primary"]
        assert "color" in primary
        assert "label" in primary
        assert "name" in primary

    def test_overlay_has_axis_toggles(self):
        """Test that overlay variables have second axis and align zero toggles."""
        editor = VarSpecEditor(available_variables=["var1", "var2"])
        subplot_id = editor.add_subplot("var1")
        editor.add_variable(subplot_id, "var2")

        overlay = editor._subplots[0]["overlays"][0]
        assert "add_second_axis" in overlay
        assert "align_zero" in overlay
        assert "compute_corr" in overlay

    def test_create_var_spec_editor(self):
        """Test create_var_spec_editor helper function."""
        editor = create_var_spec_editor(["var1", "var2"])
        assert isinstance(editor, VarSpecEditor)
        assert editor.available_variables == ["var1", "var2"]

    def test_multiple_subplots(self):
        """Test multiple subplots produce correct var_specs order."""
        editor = VarSpecEditor(available_variables=["var1", "var2", "var3"])
        editor.add_subplot("var1")
        editor.add_subplot("var2")
        editor.add_subplot("var3")

        specs = editor.to_var_specs()
        assert len(specs) == 3
        assert specs[0]["name"] == "var1"
        assert specs[1]["name"] == "var2"
        assert specs[2]["name"] == "var3"

        for spec in specs:
            assert "add_to" not in spec

    def test_layout_rebuilds_on_add(self):
        """Test that layout updates when adding subplots."""
        editor = VarSpecEditor(available_variables=["var1"])
        initial_len = len(editor.layout.objects)

        editor.add_subplot("var1")
        assert len(editor.layout.objects) > initial_len

    def test_on_config_change_callback(self):
        """Test that on_config_change is triggered on widget changes."""
        call_count = [0]

        def callback():
            call_count[0] += 1

        editor = VarSpecEditor(available_variables=["var1"], on_config_change=callback)
        editor.add_subplot("var1")

        editor._subplots[0]["primary"]["label"].value = "New Label"
        assert call_count[0] >= 1

    def test_debounce_no_crash_on_rapid_changes(self):
        """Test that rapid widget changes don't crash (regression for TimeoutCallback.cancel)."""
        call_count = [0]

        def callback():
            call_count[0] += 1

        editor = VarSpecEditor(available_variables=["var1", "var2"], on_config_change=callback)
        editor.add_subplot("var1")

        for _ in range(10):
            editor._subplots[0]["primary"]["label"].value = f"Label {_}"

        assert call_count[0] >= 1

    def test_debounce_timer_cleared_on_fire(self):
        """Test that _debounce_timer is cleared after callback fires (prevents ValueError on re-arm)."""
        call_count = [0]

        def callback():
            call_count[0] += 1

        editor = VarSpecEditor(available_variables=["var1"], on_config_change=callback)
        editor.add_subplot("var1")

        assert editor._debounce_timer is None

        editor._subplots[0]["primary"]["label"].value = "First"
        assert editor._debounce_timer is None

        editor._subplots[0]["primary"]["label"].value = "Second"
        assert editor._debounce_timer is None
        assert call_count[0] >= 2

    def test_var_spec_keys_correct(self):
        """Test that var_specs have exactly the keys plotting_joseph expects."""
        editor = VarSpecEditor(available_variables=["var1", "var2"])
        subplot_id = editor.add_subplot("var1")
        editor.add_variable(subplot_id, "var2")

        editor._subplots[0]["overlays"][0]["add_second_axis"].value = True
        editor._subplots[0]["overlays"][0]["align_zero"].value = True
        editor._subplots[0]["overlays"][0]["compute_corr"].value = True

        specs = editor.to_var_specs()

        primary_keys = set(specs[0].keys())
        expected_primary = {
            "name", "label", "color", "line_width", "alpha", "plotstyle",
        }
        assert primary_keys == expected_primary

        overlay_keys = set(specs[1].keys())
        expected_overlay = expected_primary | {"add_to", "add_second_axis", "align_zero", "compute_corr"}
        assert overlay_keys == expected_overlay
        assert specs[1]["add_to"] == "var1"
