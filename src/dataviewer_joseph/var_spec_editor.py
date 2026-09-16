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
        **params,
    ):
        super().__init__(**params)
        if available_variables:
            self.available_variables = available_variables
        self.on_config_change = on_config_change
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
                width=200,
            ),
            "color": pn.widgets.ColorPicker(value=color_default, width=60),
            "label": pn.widgets.TextInput(value=label_default, width=200),
            "line_width": pn.widgets.FloatSlider(start=0.5, end=5, step=0.5, value=1.5),
            "alpha": pn.widgets.FloatSlider(start=0.1, end=1.0, step=0.1, value=1.0),
            "plotstyle": pn.widgets.Select(options=["line", "points", "both"], value="line"),
            "threshold_mode": pn.widgets.RadioButtonGroup(
                options=["Value", "Percentile"],
                value="Value",
                button_type="primary",
            ),
            "lower_threshold_val": pn.widgets.FloatInput(value=None),
            "lower_threshold_color": pn.widgets.ColorPicker(value="#ff0000"),
            "upper_threshold_val": pn.widgets.FloatInput(value=None),
            "upper_threshold_color": pn.widgets.ColorPicker(value="#0000ff"),
            "lower_percentile": pn.widgets.FloatInput(value=None, step=1),
            "lower_percentile_color": pn.widgets.ColorPicker(value="#ff0000"),
            "upper_percentile": pn.widgets.FloatInput(value=None, step=1),
            "upper_percentile_color": pn.widgets.ColorPicker(value="#0000ff"),
        }

        if is_overlay:
            widgets["add_second_axis"] = pn.widgets.Checkbox(name="2nd axis", value=False)
            widgets["align_zero"] = pn.widgets.Checkbox(name="Align zero", value=False)
            widgets["compute_corr"] = pn.widgets.Checkbox(name="Correlation", value=False)
            widgets["remove_btn"] = pn.widgets.Button(label="Remove", color="danger", width=80)

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

        def column(*items, width=200):
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
                        column(widgets["line_width"], widgets["alpha"], width=200),
                        column(widgets["plotstyle"], width=200),
                    ),
                    pn.Row(widgets["threshold_mode"], margin=(5, 5)),
                    value_row,
                    percentile_row,
                    sizing_mode="stretch_width",
                ),
            ),
            active=[],
        )

    def _refresh_layout(self):
        """Rebuild the layout from current _subplots."""
        subplot_cards = []

        for sp_idx, sp in enumerate(self._subplots):
            subplot_num = sp_idx + 1

            primary = sp["primary"]
            primary_row = pn.Row(
                pn.Column(primary["name"], width=210),
                pn.Column(primary["color"], width=80),
                pn.Column(primary["label"], width=210),
                margin=(5, 5, 0, 5),
                scroll=True,
            )
            primary_advanced = self._create_advanced_accordion(primary)

            overlay_rows = []
            for ov_idx, ov in enumerate(sp["overlays"]):
                ov_row = pn.Row(
                    pn.Column(ov["name"], width=210),
                    pn.Column(ov["color"], width=80),
                    pn.Column(ov["label"], width=210),
                    pn.Column(
                        ov["add_second_axis"],
                        ov["align_zero"],
                        ov["compute_corr"],
                        width=180,
                    ),
                    ov["remove_btn"],
                    margin=(5, 5, 0, 5),
                    scroll=True,
                )
                ov_advanced = self._create_advanced_accordion(ov)
                overlay_rows.append(pn.Column(ov_row, ov_advanced, sizing_mode="stretch_width"))

            add_var_btn = pn.widgets.Button(label="+ Add variable", color="default", width=150, margin=(5, 5))

            def make_add_var(subplot_id):
                def on_click(event):
                    self.add_variable(subplot_id)
                return on_click

            add_var_btn.on_click(make_add_var(sp["id"]))

            remove_sp_btn = pn.widgets.Button(label="Remove subplot", color="warning", width=120)

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
            width=150,
            margin=(10, 5),
        )
        add_subplot_btn.on_click(lambda e: self.add_subplot())

        self.layout.objects = [
            self.layout.objects[0],
            self.layout.objects[1],
            add_subplot_btn,
            *subplot_cards,
        ]

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
