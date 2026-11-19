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

    def test_from_var_specs_rebuilds_subplots_and_overlays(self):
        """Test that from_var_specs reconstructs subplots and overlays."""
        editor = VarSpecEditor(available_variables=["var1", "var2", "var3"])
        editor.add_subplot("var1")
        editor.add_variable(0, "var2")
        editor.add_variable(0, "var3")
        editor.add_subplot("var1")
        # remove the extra default subplot for a clean check
        editor.remove_subplot(1)

        specs = editor.to_var_specs()
        specs[1]["label"] = "Overlay two"
        specs[1]["add_second_axis"] = True
        specs[1]["align_zero"] = True

        loaded = VarSpecEditor(available_variables=["var1", "var2", "var3"])
        loaded.from_var_specs(specs)

        assert len(loaded._subplots) == 1
        assert loaded._subplots[0]["primary"]["name"].value == "var1"
        assert len(loaded._subplots[0]["overlays"]) == 2
        assert loaded._subplots[0]["overlays"][0]["name"].value == "var2"
        assert loaded._subplots[0]["overlays"][0]["label"].value == "Overlay two"
        assert loaded._subplots[0]["overlays"][0]["add_second_axis"].value is True
        assert loaded._subplots[0]["overlays"][0]["align_zero"].value is True

        assert loaded.to_var_specs() == specs

    def test_json_round_trip_with_tuples(self):
        """Test to_json/from_json round-trips thresholds as tuples."""
        editor = VarSpecEditor(available_variables=["var1", "var2"])
        editor.add_subplot("var1")
        editor.add_variable(0, "var2")
        editor._subplots[0]["primary"]["lower_threshold_val"].value = 0.5
        editor._subplots[0]["primary"]["lower_threshold_color"].value = "#00ff00"
        editor._subplots[0]["overlays"][0]["threshold_mode"].value = "Percentile"
        editor._subplots[0]["overlays"][0]["upper_percentile"].value = 90

        text = editor.to_json()
        loaded = VarSpecEditor(available_variables=["var1", "var2"])
        loaded.from_json(text)

        original = editor.to_var_specs()
        result = loaded.to_var_specs()
        assert result == original
        assert result[0]["lower_treshold"] == (0.5, "#00ff00")
        assert result[1]["upper_percentile"][0] == 90

    def test_from_json_accepts_bare_list(self):
        """Test from_json accepts a bare list of specs."""
        editor = VarSpecEditor(available_variables=["var1"])
        editor.add_subplot("var1")
        editor._subplots[0]["primary"]["color"].value = "#112233"

        text = editor.to_json()
        import json

        bare = json.dumps(editor.to_var_specs())

        loaded = VarSpecEditor(available_variables=["var1"])
        loaded.from_json(bare)
        assert loaded.to_var_specs() == editor.to_var_specs()

        # wrapped envelope also works
        loaded2 = VarSpecEditor(available_variables=["var1"])
        loaded2.from_json(text)
        assert loaded2.to_var_specs() == editor.to_var_specs()

    def test_from_json_invalid_raises(self):
        """Test from_json raises on malformed input."""
        editor = VarSpecEditor(available_variables=["var1"])
        try:
            editor.from_json('{"format": "other"}')
            assert False, "expected ValueError"
        except ValueError:
            pass

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

    def test_update_available_variables_keeps_specs(self):
        """Switching splits updates variables without resetting subplots."""
        editor = VarSpecEditor(
            available_variables=["swe", "lai", "swvl1"], on_config_change=lambda: None
        )
        editor.add_subplot("swe")
        editor.add_variable(0, "lai")

        editor.update_available_variables(["swe", "precip"])

        # Subplots survive; still-available names keep their selections
        assert len(editor._subplots) == 1
        assert editor._subplots[0]["primary"]["name"].value == "swe"
        assert editor._subplots[0]["overlays"][0]["name"].value is None
        assert editor.available_variables == ["swe", "precip"]

        # A variable that disappeared is dropped from the specs
        editor._subplots[0]["overlays"][0]["name"].value = "precip"
        specs = editor.to_var_specs()
        assert len(specs) == 2
        assert specs[0]["name"] == "swe"
        assert specs[1]["name"] == "precip"
        assert specs[1]["add_to"] == "swe"

    def test_add_subplot_after_update_uses_new_variables(self):
        """New subplots created after a split switch use the new variables."""
        editor = VarSpecEditor(available_variables=["var1"])
        editor.add_subplot("var1")

        editor.update_available_variables(["new_var"])
        editor.add_subplot()

        assert editor._subplots[1]["primary"]["name"].value == "new_var"


# =============================================================================
# FACET CHAIN: per-variable selectors instead of one big dropdown
# =============================================================================

FACET_VOCAB = {
    "group": ["lai", "swvl1"],
    "scale": ["year", "month"],
    "model": ["linear", "tree", "ridge"],
}

TS_COLUMNS = [
    "lai_deviation",
    "swvl1_deviation",
    "rho_bias_lai_year",
    "rho_bias_swvl1_month",
    "prediction_linear",
    "prediction_tree",
    "bias_linear",
    "bias_ridge",
    "backscatter40",
]


def _faceted_editor(**kwargs):
    from dataviewer_joseph.facets import FacetSchema

    schema = FacetSchema(TS_COLUMNS, FACET_VOCAB)
    return VarSpecEditor(
        available_variables=TS_COLUMNS, facet_schema=schema, **kwargs
    )


class TestFacetChain:
    """Per-variable facet selector chain."""

    def test_chain_built_per_row(self):
        editor = _faceted_editor()
        editor.add_subplot()
        widgets = editor._subplots[0]["primary"]
        assert widgets.get("chain")
        assert list(widgets["chain"]) == [
            "group",
            "scale",
            "model",
            "metric",
            "other",
        ]

    def test_resolve_on_single_match(self):
        editor = _faceted_editor()
        editor.add_subplot("bias_linear")
        w = editor._subplots[0]["primary"]
        assert w["chain"]["model"].value == "linear"  # synced from the name
        # Free picks: ignore the synced values, choose group + scale only.
        w["chain"]["model"].value = "All"
        w["chain"]["metric"].value = "All"
        w["chain"]["group"].value = "lai"
        # Two candidates (lai_deviation, rho_bias_lai_year): stays unchanged.
        assert w["name"].value == "bias_linear"
        w["chain"]["scale"].value = "year"
        # Exactly one left: the row applies it.
        assert w["name"].value == "rho_bias_lai_year"
        assert "rho_bias_lai_year" in w["chain_status"].object

    def test_model_only_pick_resolves(self):
        editor = _faceted_editor()
        editor.add_subplot("bias_linear")
        w = editor._subplots[0]["primary"]
        w["chain"]["metric"].value = "All"
        w["chain"]["model"].value = "tree"
        assert w["name"].value == "prediction_tree"

    def test_no_match_keeps_name(self):
        editor = _faceted_editor()
        editor.add_subplot("bias_linear")
        w = editor._subplots[0]["primary"]
        w["chain"]["group"].value = "swvl1"
        w["chain"]["scale"].value = "year"
        w["chain"]["metric"].value = "rho"
        assert w["name"].value == "bias_linear"
        assert "No variable matches" in w["chain_status"].object

    def test_other_facet_selects_unbound(self):
        editor = _faceted_editor()
        editor.add_subplot("bias_linear")
        w = editor._subplots[0]["primary"]
        w["chain"]["other"].value = "backscatter40"
        assert w["name"].value == "backscatter40"

    def test_spec_import_reconstructs_chain(self):
        editor = _faceted_editor()
        editor.from_var_specs([{"name": "prediction_linear"}])
        w = editor._subplots[0]["primary"]
        assert w["name"].value == "prediction_linear"
        assert w["chain"]["model"].value == "linear"
        assert w["chain"]["metric"].value == "prediction"

    def test_spec_import_unbound_name(self):
        editor = _faceted_editor()
        editor.from_var_specs([{"name": "backscatter40"}])
        w = editor._subplots[0]["primary"]
        assert w["chain"]["other"].value == "backscatter40"

    def test_flat_fallback_without_schema(self):
        editor = VarSpecEditor(available_variables=TS_COLUMNS)
        editor.add_subplot("bias_linear")
        w = editor._subplots[0]["primary"]
        assert "chain" not in w
        assert w["name"].value == "bias_linear"

    def test_update_schema_rebuilds_chain(self):
        from dataviewer_joseph.facets import FacetSchema

        editor = _faceted_editor()
        editor.add_subplot("bias_linear")
        assert editor._subplots[0]["primary"]["chain"]["model"].value == "linear"

        # A split without facetable names removes the chain (flat fallback).
        editor.update_available_variables(["plain_a"], facet_schema=None)
        w = editor._subplots[0]["primary"]
        assert "chain" not in w

        # A fresh split with a matching schema re-adds the chain; picking the
        # facets resolves the row again.
        names = ["lai_deviation_year", "lai_deviation_month", "swvl1_deviation_year"]
        editor.update_available_variables(
            names,
            facet_schema=FacetSchema(names, FACET_VOCAB),
        )
        w = editor._subplots[0]["primary"]
        assert set(w["chain"]) == {"group", "scale"}
        w["chain"]["group"].value = "lai"
        w["chain"]["scale"].value = "year"
        assert w["name"].value == "lai_deviation_year"
