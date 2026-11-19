"""Tests for facet (subgroup) handling."""

from dataviewer_joseph.facets import FacetSchema, tokenize

VOCAB = {
    "group": ["lai", "swvl1"],
    "scale": ["year", "month"],
    "model": ["linear", "tree", "ridge"],
}

MAP_NAMES = sorted(
    [
        "lai_deviation_year",
        "lai_deviation_month",
        "swvl1_deviation_year",
        "swvl1_deviation_month",
        "rho_bias_lai_year",
        "prediction_linear",
        "prediction_tree",
        "bias_ridge",
    ]
)


def test_tokenize():
    assert tokenize("lai_deviation_year") == ["lai", "deviation", "year"]
    assert tokenize(" Rho_Bias_lai ") == ["rho", "bias", "lai"]
    assert tokenize("") == []


def test_schema_detects_facets():
    schema = FacetSchema(MAP_NAMES, VOCAB)
    assert schema.active()
    assert schema.facet_values("group") == ["lai", "swvl1"]
    assert schema.facet_values("scale") == ["month", "year"]
    assert schema.facet_values("model") == ["linear", "ridge", "tree"]
    assert schema.facet_values("metric") == ["bias", "deviation", "prediction", "rho"]

    assert schema.value_of("lai_deviation_year", "group") == "lai"
    assert schema.value_of("lai_deviation_year", "scale") == "year"
    assert schema.value_of("prediction_linear", "model") == "linear"
    assert schema.value_of("bias_ridge", "group") is None


def test_metric_contains_matching():
    schema = FacetSchema(MAP_NAMES, VOCAB)
    assert schema.has_metric_value("rho_bias_lai_year", "rho")
    assert schema.has_metric_value("rho_bias_lai_year", "bias")
    assert not schema.has_metric_value("lai_deviation_year", "rho")
    # Multi-token metrics end up in both token buckets.
    assert "rho_bias_lai_year" in schema.filter_names({"metric": "rho"})
    assert "rho_bias_lai_year" in schema.filter_names({"metric": "bias"})


def test_filter_combinations_interchangeable():
    schema = FacetSchema(MAP_NAMES, VOCAB)
    assert schema.filter_names() == MAP_NAMES
    assert schema.filter_names({}) == MAP_NAMES
    assert schema.filter_names({"group": "lai"}) == [
        "lai_deviation_month",
        "lai_deviation_year",
        "rho_bias_lai_year",
    ]
    assert schema.filter_names({"group": "lai", "scale": "year"}) == [
        "lai_deviation_year",
        "rho_bias_lai_year",
    ]
    # Model-only filter works independently of group/scale.
    assert schema.filter_names({"model": "linear"}) == ["prediction_linear"]
    assert schema.filter_names({"scale": "month", "model": "tree"}) == []
    # Group + metric combination (no hierarchy)
    assert schema.filter_names({"group": "swvl1", "metric": "deviation"}) == [
        "swvl1_deviation_month",
        "swvl1_deviation_year",
    ]


def test_single_token_names_not_metrics():
    schema = FacetSchema(["lat", "time", "lai", "lai_mean_bias"], VOCAB)
    assert schema.facet_values("metric") == ["bias", "mean"]


def test_flat_mode_without_vocab():
    schema = FacetSchema(["a_la_composit", "mae", "rmse"], None)
    assert not schema.active()
    assert schema.filter_names({"group": "lai"}) == []
    assert schema.filter_names() == ["a_la_composit", "mae", "rmse"]
    assert schema.group_tree() == {"__all__": ["a_la_composit", "mae", "rmse"]}


def test_empty_vocab_inactive():
    schema = FacetSchema(["lage_year", "swvl1_month"], {})
    assert not schema.active()


def test_group_tree_nesting_and_fallback():
    schema = FacetSchema(MAP_NAMES, VOCAB)
    tree = schema.group_tree()  # group -> scale -> model -> names by default
    assert set(tree) == {"lai", "swvl1", "(unspecified)"}
    assert set(tree["lai"]) == {"year", "month"}
    # Third nesting level is the "model" facet; these names have none.
    assert set(tree["lai"]["year"]) == {"(unspecified)"}
    assert set(tree["lai"]["year"]["(unspecified)"]) == {
        "lai_deviation_year",
        "rho_bias_lai_year",
    }
    assert tree["swvl1"]["year"]["(unspecified)"] == ["swvl1_deviation_year"]
    # Names without a group token land in the fallback bucket; they have no
    # scale either, so that level is "(unspecified)" and the model facet is
    # the deepest level.
    assert set(tree["(unspecified)"]) == {"(unspecified)"}
    assert set(tree["(unspecified)"]["(unspecified)"]) == {
        "linear",
        "ridge",
        "tree",
    }
    assert tree["(unspecified)"]["(unspecified)"]["linear"] == [
        "prediction_linear"
    ]
    assert tree["(unspecified)"]["(unspecified)"]["ridge"] == ["bias_ridge"]


def test_group_tree_one_level():
    schema = FacetSchema(["lai_year", "lai_month", "swvl1_year"], VOCAB)
    tree = schema.group_tree(["group"])
    assert set(tree) == {"lai", "swvl1"}
    assert set(tree["lai"]) == {"lai_month", "lai_year"}
    assert tree["swvl1"] == ["swvl1_year"]


def test_group_tree_no_facet_order():
    schema = FacetSchema(["lai_year"], VOCAB)
    assert schema.group_tree() == {"__all__": ["lai_year"]}
