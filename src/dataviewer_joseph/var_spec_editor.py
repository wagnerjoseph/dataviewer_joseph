"""Interactive var_specs editor for plotting_joseph integration.

Provides Panel widgets for configuring var_specs without writing code.
Features:
- Subplot-based model: each subplot = one panel with a primary variable + optional overlays
- Live layout: add/remove subplots and variables updates the UI immediately
- Compact rows: variable name + color + label on one line
- Advanced options collapsed in accordion per variable
- Auto-update callback (debounced) when config changes
- Stable IDs for correct removal (no stale identity bugs)
"""

from collections.abc import Callable

import panel as pn
import param

pn.extension()

_OTHER_FACET = "other"
_UNSET = object()


def _chain_label(facet: str) -> str:
    """Editor label for a chain facet."""
    return "Other" if facet == _OTHER_FACET else facet.title()


class VarSpecEditor(param.Parameterized):
    """Interactive editor for building var_specs for plot_time_series.

    Each subplot represents one panel in the final plot.
    Subplots contain a primary variable and optional overlay variables.
    """

    available_variables = param.List(default=[], doc="Available data columns")

    def __init__(
        self,
        available_variables: list[str] | None = None,
        on_config_change: Callable | None = None,
        facet_schema: object | None = None,
        **params,
    ):
        super().__init__(**params)
        if available_variables:
            self.available_variables = available_variables
        self.on_config_change = on_config_change
        self.facet_schema = facet_schema
        self._subplots: list[dict] = []
        self._next_id = 0
        self._debounce_timer = None

        self._color_palette = [
            "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
            "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
        ]

        self.layout = pn.Column(
            pn.pane.Markdown("### Timeseries Configuration"),
            pn.pane.Markdown(
                "*Each subplot = one panel. Add variables to overlay on the same panel. "
                "Advanced options are in collapsible accordions.*"
            ),
            sizing_mode="stretch_width",
        )
        self._refresh_layout()

    def _debounced_trigger(self):
        """Trigger on_config_change with debounce (~300ms)."""
        if self._debounce_timer is not None:
            try:
                pn.state.curdoc.remove_timeout_callback(self._debounce_timer)
            except Exception:
                pass
            self._debounce_timer = None

        def trigger():
            self._debounce_timer = None
            if self.on_config_change:
                self.on_config_change()

        if pn.state.curdoc is not None:
            self._debounce_timer = pn.state.curdoc.add_timeout_callback(trigger, 300)
        else:
            trigger()

    def _on_widget_change(self, event=None):
        """Called when any widget changes - triggers debounced update."""
        self._debounced_trigger()

    # ------------------------------------------------------------------ #
    # facet chain (optional: one selector per facet instead of one big   #
    # variable dropdown)                                                 #
    # ------------------------------------------------------------------ #

    def _chain_active(self) -> bool:
        """:meth:`facet_schema` is set and detected enough groups."""
        schema = self.facet_schema
        if schema is None:
            return False
        try:
            return bool(getattr(schema, "active")())
        except Exception:
            return False

    def _chain_facets(self) -> list[str]:
        """Ordered facet names for a variable row (vocab order, metric last)."""
        schema = self.facet_schema
        facets = list(getattr(schema, "active_facets")())
        if getattr(schema, "unbound_names")():
            facets.append(_OTHER_FACET)
        return facets

    def _create_chain_widgets(self, widgets: dict) -> None:
        """Build the per-variable facet selector chain into ``widgets``."""
        schema = self.facet_schema
        widgets["chain"] = {}
        widgets["chain_status"] = pn.pane.Markdown(
            "",
            styles={"font-size": "11px", "color": "#666"},
            width=210,
            margin=(2, 5),
        )
        for facet in self._chain_facets():
            if facet == _OTHER_FACET:
                options = ["All"] + list(schema.unbound_names())
            else:
                options = ["All"] + list(schema.facet_values(facet))
            selector = pn.widgets.Select(
                label=_chain_label(facet),
                options=options,
                value="All",
                width=120,
                margin=(2, 2),
            )
            if facet == _OTHER_FACET:
                selector.param.watch(
                    lambda event, ws=widgets: self._on_other_change(ws), "value"
                )
            else:
                selector.param.watch(
                    lambda event, ws=widgets: self._on_vocab_change(ws), "value"
                )
            selector.param.watch(self._on_widget_change, "value")
            widgets["chain"][facet] = selector

    def _on_vocab_change(self, widgets: dict) -> None:
        """A facet pick takes precedence over a previously picked name."""
        if widgets.get("_chain_busy"):
            return
        other = widgets["chain"].get(_OTHER_FACET)
        if other is not None and other.value != "All":
            other.value = "All"
        self._resolve_chain(widgets)

    def _on_other_change(self, widgets: dict) -> None:
        """Picking an unbound column wins over any facet selection."""
        if widgets.get("_chain_busy"):
            return
        chain = widgets["chain"]
        if chain[_OTHER_FACET].value == "All":
            self._resolve_chain(widgets)
            return
        widgets["_chain_busy"] = True
        try:
            for facet, selector in chain.items():
                if facet != _OTHER_FACET:
                    selector.value = "All"
        finally:
            widgets["_chain_busy"] = False
        self._resolve_chain(widgets)

    def _set_chain_status(self, widgets: dict, text: str) -> None:
        widgets.get("chain_status").object = text

    def _resolve_chain(self, widgets: dict) -> None:
        """Resolve the row's variable from the current facet combination.

        Free picks: the combination applies as soon as exactly one column
        matches (unfulfilled selections leave the resolved name untouched).
        """
        chain = widgets.get("chain")
        if not chain:
            return
        other = chain.get(_OTHER_FACET)
        selection = {
            facet: selector.value
            for facet, selector in chain.items()
            if facet != _OTHER_FACET and selector.value != "All"
        }
        if other is not None and other.value != "All":
            widgets["name"].value = other.value
            self._set_chain_status(widgets, f"→ {other.value}")
            return
        try:
            matches = self.facet_schema.filter_names(selection)
        except Exception:
            matches = []
        if len(matches) == 1:
            widgets["name"].value = matches[0]
            self._set_chain_status(widgets, f"→ {matches[0]}")
        elif len(matches) > 1:
            current = widgets["name"].value
            note = f"{len(matches)} variables match — pick more"
            if current:
                note += f" (current: {current})"
            self._set_chain_status(widgets, note)
        else:
            self._set_chain_status(widgets, "No variable matches this combination")

    def _sync_chain_from_name(self, widgets: dict) -> None:
        """Populate the chain selects from the row's current variable name."""
        name = widgets.get("name").value
        chain = widgets.get("chain")
        schema = self.facet_schema
        if not name or not chain or schema is None:
            return
        if name in schema.unbound_names():
            if _OTHER_FACET in chain:
                chain[_OTHER_FACET].value = name
            return
        if _OTHER_FACET in chain:
            chain[_OTHER_FACET].value = "All"
        binding = getattr(schema, "binding", {}).get(name, {})
        for facet, value in binding.items():
            selector = chain.get(facet)
            if selector is not None and value in selector.options:
                selector.value = value
        metric = getattr(schema, "metric_tokens", {}).get(name) or []
        metric_selector = chain.get("metric")
        if metric_selector is not None and metric and metric[0] in metric_selector.options:
            metric_selector.value = metric[0]

    def _rebuild_chain_widgets(self, widgets: dict) -> None:
        """Recreate a row's chain for a (new) facet schema, if active."""
        if not self._chain_active():
            widgets.pop("chain", None)
            widgets.pop("chain_status", None)
            return
        self._create_chain_widgets(widgets)
        self._sync_chain_from_name(widgets)

    def _get_next_color(self, used_colors: set) -> str:
        """Get the next unused color from the palette."""
        for c in self._color_palette:
            if c not in used_colors:
                return c
        return self._color_palette[len(used_colors) % len(self._color_palette)]

    def _create_variable_widgets(self, name: str | None = None, is_overlay: bool = False) -> dict:
        """Create widgets for a variable row."""
        if name is None and self.available_variables:
            used = self._get_used_variables()
            for v in self.available_variables:
                if v not in used:
                    name = v
                    break
            if name is None:
                name = self.available_variables[0] if self.available_variables else ""

        label_default = name.replace("_", " ").title() if name else ""
        used_colors = self._get_used_colors()
        color_default = self._get_next_color(used_colors)

        widgets = {
            "name": pn.widgets.Select(
                options=self.available_variables,
                value=name if name in self.available_variables else (self.available_variables[0] if self.available_variables else None),
                width=150,
            ),
            "color": pn.widgets.ColorPicker(value=color_default, width=45),
            "label": pn.widgets.TextInput(value=label_default, width=150),
            "line_width": pn.widgets.FloatSlider(
                start=0.5, end=5, step=0.5, value=1.5, width=150
            ),
            "alpha": pn.widgets.FloatSlider(
                start=0.1, end=1.0, step=0.1, value=1.0, width=150
            ),
            "plotstyle": pn.widgets.Select(
                options=["line", "points", "both"], value="line", width=150
            ),
            "threshold_mode": pn.widgets.RadioButtonGroup(
                options=["Value", "Percentile"],
                value="Value",
                color="primary",
            ),
            "lower_threshold_val": pn.widgets.FloatInput(value=None, width=150),
            "lower_threshold_color": pn.widgets.ColorPicker(value="#ff0000"),
            "upper_threshold_val": pn.widgets.FloatInput(value=None, width=150),
            "upper_threshold_color": pn.widgets.ColorPicker(value="#0000ff"),
            "lower_percentile": pn.widgets.FloatInput(value=None, step=1, width=150),
            "lower_percentile_color": pn.widgets.ColorPicker(value="#ff0000"),
            "upper_percentile": pn.widgets.FloatInput(value=None, step=1, width=150),
            "upper_percentile_color": pn.widgets.ColorPicker(value="#0000ff"),
        }

        if is_overlay:
            widgets["add_second_axis"] = pn.widgets.Checkbox(label="2nd axis", value=False)
            widgets["align_zero"] = pn.widgets.Checkbox(label="Align zero", value=False)
            widgets["compute_corr"] = pn.widgets.Checkbox(label="Correlation", value=False)
            widgets["remove_btn"] = pn.widgets.Button(label="Remove", color="danger", width=60)

        if self._chain_active():
            self._create_chain_widgets(widgets)

        for key, widget in widgets.items():
            if hasattr(widget, "param") and hasattr(widget.param, "value"):
                widget.param.watch(self._on_widget_change, "value")

        # Keep the legend label in sync with the selected variable so the legend
        # updates when the variable dropdown is changed.
        def on_name_change(event, label_widget=widgets["label"]):
            new_name = event.new
            if new_name:
                label_widget.value = new_name.replace("_", " ").title()

        widgets["name"].param.watch(on_name_change, "value")

        if widgets.get("chain") and widgets["name"].value:
            self._sync_chain_from_name(widgets)

        return widgets

    def _get_used_variables(self) -> set:
        """Get all currently used variable names."""
        used = set()
        for sp in self._subplots:
            primary_name = sp["primary"]["name"].value
            if primary_name:
                used.add(primary_name)
            for ov in sp["overlays"]:
                ov_name = ov["name"].value
                if ov_name:
                    used.add(ov_name)
        return used

    def _get_used_colors(self) -> set:
        """Get all currently used colors."""
        used = set()
        for sp in self._subplots:
            used.add(sp["primary"]["color"].value)
            for ov in sp["overlays"]:
                used.add(ov["color"].value)
        return used

    def _create_advanced_accordion(self, widgets: dict) -> pn.Accordion:
        """Create collapsed accordion with advanced options."""

        def column(*items, width=150):
            return pn.Column(*items, width=width)

        value_row = pn.Row(
            column(widgets["lower_threshold_val"], widgets["lower_threshold_color"]),
            column(widgets["upper_threshold_val"], widgets["upper_threshold_color"]),
        )
        percentile_row = pn.Row(
            column(widgets["lower_percentile"], widgets["lower_percentile_color"]),
            column(widgets["upper_percentile"], widgets["upper_percentile_color"]),
        )

        def on_threshold_mode_change(event):
            is_percentile = event.new == "Percentile"
            value_row.visible = not is_percentile
            percentile_row.visible = is_percentile

        widgets["threshold_mode"].param.watch(on_threshold_mode_change, "value")
        value_row.visible = True
        percentile_row.visible = False

        return pn.Accordion(
            (
                "Advanced",
                pn.Column(
                    pn.Row(
                        column(widgets["line_width"], widgets["alpha"], width=150),
                        column(widgets["plotstyle"], width=150),
                    ),
                    pn.Row(widgets["threshold_mode"], margin=(5, 5)),
                    value_row,
                    percentile_row,
                    sizing_mode="stretch_width",
                ),
            ),
            active=[],
        )

    def _variable_selector_column(self, widgets: dict) -> pn.Column:
        """The variable picker of a row: facet chain or the plain dropdown.

        With facet chains the total select width is computed from the number
        of facets (each select is 120px wide plus margins), so the row never
        overflows its container and cannot overlap widgets placed after it.
        """
        chain = widgets.get("chain")
        if chain:
            n = len(chain)
            return pn.Column(
                pn.Row(
                    *chain.values(),
                    margin=(0, 4),
                    sizing_mode="stretch_width",
                ),
                widgets["chain_status"],
                width=n * 124 + 6,
            )
        return pn.Column(widgets["name"], width=160)

    def _picker_meta_items(self, widgets, extra: list | None = None) -> list:
        """Non-selector widgets of a variable row: color, label, extras."""
        items = [
            pn.Column(widgets["color"], width=60),
            pn.Column(widgets["label"], width=160),
        ]
        if extra:
            items.extend(extra)
        return items

    def _picker_row(self, widgets, extra: list | None = None):
        """The variable picker line of a row.

        With facet chains the selector column can be wide (one select per
        facet), so the color/label extras move to a second line — this keeps
        the dropdowns from overlapping the color picker at any width.
        """
        selector = self._variable_selector_column(widgets)
        meta = self._picker_meta_items(widgets, extra)
        if widgets.get("chain"):
            return pn.Column(
                selector,
                pn.Row(*meta, margin=(0, 0, 0, 5)),
                margin=(5, 5, 0, 5),
                sizing_mode="stretch_width",
            )
        return pn.Row(selector, *meta, margin=(5, 5, 0, 5))

    def _refresh_layout(self):
        """Rebuild the layout from current _subplots."""
        subplot_cards = []

        for sp_idx, sp in enumerate(self._subplots):
            subplot_num = sp_idx + 1

            primary = sp["primary"]
            primary_row = self._picker_row(primary)
            primary_advanced = self._create_advanced_accordion(primary)

            overlay_rows = []
            for ov_idx, ov in enumerate(sp["overlays"]):
                ov_row = self._picker_row(
                    ov,
                    extra=[
                        pn.Column(
                            ov["add_second_axis"],
                            ov["align_zero"],
                            ov["compute_corr"],
                            width=140,
                        ),
                        ov["remove_btn"],
                    ],
                )
                ov_advanced = self._create_advanced_accordion(ov)
                overlay_rows.append(pn.Column(ov_row, ov_advanced, sizing_mode="stretch_width"))

            add_var_btn = pn.widgets.Button(label="+ Add variable", color="default", width=115, margin=(5, 5))

            def make_add_var(subplot_id):
                def on_click(event):
                    self.add_variable(subplot_id)
                return on_click

            add_var_btn.on_click(make_add_var(sp["id"]))

            remove_sp_btn = pn.widgets.Button(label="Remove subplot", color="warning", width=90)

            def make_remove_subplot(subplot_id):
                def on_click(event):
                    self.remove_subplot(subplot_id)
                return on_click

            remove_sp_btn.on_click(make_remove_subplot(sp["id"]))

            header = pn.Row(
                pn.pane.Markdown(f"#### Subplot {subplot_num}"),
                remove_sp_btn,
                margin=(10, 0, 5, 0),
            )

            card = pn.Column(
                header,
                pn.Column(primary_row, primary_advanced, sizing_mode="stretch_width"),
                add_var_btn,
                *overlay_rows,
                styles={"border": "1px solid #ddd", "border-radius": "5px", "padding": "10px"},
                sizing_mode="stretch_width",
                margin=(5, 0),
            )
            subplot_cards.append(card)

        add_subplot_btn = pn.widgets.Button(
            label="+ Add subplot",
            color="success",
            width=115,
            margin=(10, 5),
        )
        add_subplot_btn.on_click(lambda e: self.add_subplot())

        self.layout.objects = [
            self.layout.objects[0],
            self.layout.objects[1],
            add_subplot_btn,
            *subplot_cards,
        ]

    def reset(self, names: list[str] | None = None) -> None:
        """Rebuild the editor for a new split/selection.

        Removes all subplots and (when ``names`` is given) sets the
        available variables to ``names`` with the first three as fresh
        default subplots — used when the split changes, so the specs never
        reference variables of another split.
        """
        self._subplots = []
        self._next_id = 0
        if names is not None:
            self.available_variables = list(names)
        for name in (names or [])[:3]:
            self.add_subplot(name)

    def update_available_variables(
        self, names: list[str], facet_schema: object | None = _UNSET
    ) -> None:
        """Update the available variables without resetting the subplots.

        Keeps all current subplots and selections; existing variables that
        are no longer available keep their rows but are filtered out at
        plot time, while new variables become selectable in the dropdowns.

        Args:
            names: New list of available variable names
            facet_schema: Optional fresh facet schema for the new split
                (pass ``None`` to disable the chains); when given, the
                per-variable facet chains are rebuilt from it.
        """
        if facet_schema is not _UNSET:
            self.facet_schema = facet_schema
        self.available_variables = list(names)
        for sp in self._subplots:
            for widgets in [sp["primary"], *sp["overlays"]]:
                if widgets["name"].value not in names:
                    widgets["name"].value = None
                widgets["name"].options = list(names)
                self._rebuild_chain_widgets(widgets)

    def add_subplot(self, primary_name: str | None = None) -> int:
        """Add a new subplot with a primary variable."""
        subplot_id = self._next_id
        self._next_id += 1

        primary_widgets = self._create_variable_widgets(name=primary_name, is_overlay=False)

        subplot = {
            "id": subplot_id,
            "primary": primary_widgets,
            "overlays": [],
        }
        self._subplots.append(subplot)
        self._refresh_layout()
        self._on_widget_change()
        return subplot_id

    def add_subplots(self, names: list[str]) -> None:
        """Add one subplot per name, skipping names already plotted.

        Used by the group browser's ``Add all`` buttons: every ``name``
        becomes its own timeseries panel; names that are already used as a
        primary or overlay variable anywhere are skipped.

        Args:
            names: Variable names to add as subplots.
        """
        used = self._get_used_variables()
        for name in names:
            if not name or name in used:
                continue
            self.add_subplot(name)
            used.add(name)

    def remove_subplot(self, subplot_id: int) -> None:
        """Remove a subplot by its stable ID."""
        self._subplots = [sp for sp in self._subplots if sp["id"] != subplot_id]
        self._refresh_layout()
        self._on_widget_change()

    def add_variable(self, subplot_id: int, name: str | None = None) -> None:
        """Add an overlay variable to a subplot."""
        subplot = next((sp for sp in self._subplots if sp["id"] == subplot_id), None)
        if subplot is None:
            return

        overlay_widgets = self._create_variable_widgets(name=name, is_overlay=True)

        def on_remove(event, sid=subplot_id, oid=id(overlay_widgets)):
            self.remove_variable(sid, oid)

        overlay_widgets["remove_btn"].on_click(on_remove)

        subplot["overlays"].append(overlay_widgets)
        self._refresh_layout()
        self._on_widget_change()

    def remove_variable(self, subplot_id: int, overlay_id: int) -> None:
        """Remove an overlay variable from a subplot by object identity."""
        subplot = next((sp for sp in self._subplots if sp["id"] == subplot_id), None)
        if subplot is None:
            return

        subplot["overlays"] = [ov for ov in subplot["overlays"] if id(ov) != overlay_id]
        self._refresh_layout()
        self._on_widget_change()

    def to_var_specs(self) -> list[dict]:
        """Collect widget states into var_specs list for plot_time_series."""
        specs = []

        for sp in self._subplots:
            primary = sp["primary"]
            primary_name = primary["name"].value
            if not primary_name:
                continue

            primary_spec = {
                "name": primary_name,
                "label": primary["label"].value,
                "color": primary["color"].value,
                "line_width": primary["line_width"].value,
                "alpha": primary["alpha"].value,
                "plotstyle": primary["plotstyle"].value,
            }

            if primary["threshold_mode"].value == "Percentile":
                lower_p = primary["lower_percentile"].value
                if lower_p is not None:
                    primary_spec["lower_percentile"] = (
                        lower_p, primary["lower_percentile_color"].value)
                upper_p = primary["upper_percentile"].value
                if upper_p is not None:
                    primary_spec["upper_percentile"] = (
                        upper_p, primary["upper_percentile_color"].value)
            else:
                lower_val = primary["lower_threshold_val"].value
                if lower_val is not None:
                    primary_spec["lower_treshold"] = (
                        lower_val, primary["lower_threshold_color"].value)

                upper_val = primary["upper_threshold_val"].value
                if upper_val is not None:
                    primary_spec["upper_treshold"] = (
                        upper_val, primary["upper_threshold_color"].value)

            specs.append(primary_spec)

            for ov in sp["overlays"]:
                ov_name = ov["name"].value
                if not ov_name:
                    continue

                ov_spec = {
                    "name": ov_name,
                    "label": ov["label"].value,
                    "color": ov["color"].value,
                    "line_width": ov["line_width"].value,
                    "alpha": ov["alpha"].value,
                    "plotstyle": ov["plotstyle"].value,
                    "add_to": primary_name,
                }

                if ov["add_second_axis"].value:
                    ov_spec["add_second_axis"] = True
                if ov["align_zero"].value:
                    ov_spec["align_zero"] = True
                if ov["compute_corr"].value:
                    ov_spec["compute_corr"] = True

                if ov["threshold_mode"].value == "Percentile":
                    lower_p = ov["lower_percentile"].value
                    if lower_p is not None:
                        ov_spec["lower_percentile"] = (
                            lower_p, ov["lower_percentile_color"].value)
                    upper_p = ov["upper_percentile"].value
                    if upper_p is not None:
                        ov_spec["upper_percentile"] = (
                            upper_p, ov["upper_percentile_color"].value)
                else:
                    lower_val = ov["lower_threshold_val"].value
                    if lower_val is not None:
                        ov_spec["lower_treshold"] = (
                            lower_val, ov["lower_threshold_color"].value)

                    upper_val = ov["upper_threshold_val"].value
                    if upper_val is not None:
                        ov_spec["upper_treshold"] = (
                            upper_val, ov["upper_threshold_color"].value)

                specs.append(ov_spec)

        return specs

    _THRESHOLD_KEYS = (
        "lower_treshold",
        "upper_treshold",
        "lower_percentile",
        "upper_percentile",
    )

    def _apply_spec_values(self, widgets: dict, spec: dict, is_overlay: bool) -> None:
        """Apply a var_spec dict onto a set of variable widgets."""
        widgets["name"].value = spec.get("name", widgets["name"].value)
        widgets["label"].value = spec.get("label", widgets["label"].value)
        widgets["color"].value = spec.get("color", widgets["color"].value)
        widgets["line_width"].value = spec.get(
            "line_width", widgets["line_width"].value)
        widgets["alpha"].value = spec.get("alpha", widgets["alpha"].value)
        widgets["plotstyle"].value = spec.get(
            "plotstyle", widgets["plotstyle"].value)

        has_percentile = False
        if "lower_treshold" in spec:
            val, color = spec["lower_treshold"]
            widgets["lower_threshold_val"].value = val
            if color:
                widgets["lower_threshold_color"].value = color
        if "upper_treshold" in spec:
            val, color = spec["upper_treshold"]
            widgets["upper_threshold_val"].value = val
            if color:
                widgets["upper_threshold_color"].value = color
        if "lower_percentile" in spec:
            val, color = spec["lower_percentile"]
            widgets["lower_percentile"].value = val
            if color:
                widgets["lower_percentile_color"].value = color
            has_percentile = True
        if "upper_percentile" in spec:
            val, color = spec["upper_percentile"]
            widgets["upper_percentile"].value = val
            if color:
                widgets["upper_percentile_color"].value = color
            has_percentile = True

        if has_percentile:
            widgets["threshold_mode"].value = "Percentile"
        elif "lower_treshold" in spec or "upper_treshold" in spec:
            widgets["threshold_mode"].value = "Value"

        if is_overlay:
            widgets["add_second_axis"].value = spec.get("add_second_axis", False)
            widgets["align_zero"].value = spec.get("align_zero", False)
            widgets["compute_corr"].value = spec.get("compute_corr", False)

        if widgets.get("chain"):
            self._sync_chain_from_name(widgets)

    def from_var_specs(self, specs: list[dict]) -> None:
        """Rebuild the editor's subplots from a list of var_specs.

        Specs without an ``add_to`` key become primary subplot variables; specs
        with ``add_to`` are added as overlays on the matching subplot.

        Args:
            specs: List of var_spec dicts (the format produced by ``to_var_specs``).
        """
        self._subplots = []
        self._next_id = 0

        for spec in specs or []:
            name = spec.get("name")
            if not name:
                continue

            add_to = spec.get("add_to")
            if add_to:
                target = next(
                    (sp for sp in self._subplots
                     if sp["primary"]["name"].value == add_to),
                    None,
                )
                if target is None:
                    continue
                ov_widgets = self._create_variable_widgets(
                    name=name, is_overlay=True)
                self._apply_spec_values(ov_widgets, spec, is_overlay=True)

                def on_remove(event, sid=target["id"], oid=id(ov_widgets)):
                    self.remove_variable(sid, oid)

                ov_widgets["remove_btn"].on_click(on_remove)
                target["overlays"].append(ov_widgets)
            else:
                widgets = self._create_variable_widgets(name=name, is_overlay=False)
                self._apply_spec_values(widgets, spec, is_overlay=False)
                subplot = {
                    "id": self._next_id,
                    "primary": widgets,
                    "overlays": [],
                }
                self._next_id += 1
                self._subplots.append(subplot)

        self._refresh_layout()
        self._on_widget_change()

    def _specs_to_jsonable(self, specs: list[dict]) -> list[dict]:
        """Convert specs to JSON-safe dicts (tuples -> lists)."""
        out = []
        for spec in specs:
            s = dict(spec)
            for key in self._THRESHOLD_KEYS:
                if key in s and isinstance(s[key], tuple):
                    s[key] = list(s[key])
            out.append(s)
        return out

    def _specs_from_jsonable(self, obj) -> list[dict]:
        """Convert a JSON document back into var_spec list (lists -> tuples)."""
        if isinstance(obj, dict):
            obj = obj.get("var_specs", [])
        specs = []
        for spec in obj or []:
            s = dict(spec)
            for key in self._THRESHOLD_KEYS:
                if key in s and isinstance(s[key], list):
                    s[key] = tuple(s[key])
            specs.append(s)
        return specs

    def to_json(self, indent: int = 2) -> str:
        """Serialize the current configuration to a JSON string.

        Wraps the ``var_specs`` list in a versioned envelope so the file is
        self-describing and can be reloaded with :meth:`from_json`.
        """
        import json

        payload = {
            "format": "dataviewer_var_config",
            "version": 1,
            "var_specs": self._specs_to_jsonable(self.to_var_specs()),
        }
        return json.dumps(payload, indent=indent)

    def from_json(self, text: str) -> bool:
        """Load a configuration from a JSON string produced by :meth:`to_json`.

        Also accepts a bare JSON list of var_specs for flexibility.

        Args:
            text: JSON string with the var config.

        Returns:
            True on success.

        Raises:
            ValueError: If the content is not a valid var config.
        """
        import json

        obj = json.loads(text)
        if isinstance(obj, dict) and obj.get("format") != "dataviewer_var_config":
            raise ValueError("Not a valid dataviewer var config file")
        specs = self._specs_from_jsonable(obj)
        if not isinstance(specs, list):
            raise ValueError("var config must contain a list of variable specs")
        self.from_var_specs(specs)
        return True

    def add_var(self, name: str | None = None) -> None:
        """Backward-compatible alias for add_subplot."""
        self.add_subplot(name)


def create_var_spec_editor(
    available_variables: list[str], on_config_change: Callable | None = None
) -> VarSpecEditor:
    """Create a var_spec editor with the given available variables."""
    return VarSpecEditor(
        available_variables=available_variables, on_config_change=on_config_change
    )
