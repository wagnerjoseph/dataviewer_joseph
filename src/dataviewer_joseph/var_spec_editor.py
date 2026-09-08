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

from typing import Callable

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
            ),
            "color": pn.widgets.ColorPicker(value=color_default),
            "label": pn.widgets.TextInput(value=label_default),
            "line_width": pn.widgets.FloatSlider(start=0.5, end=5, step=0.5, value=1.5),
            "alpha": pn.widgets.FloatSlider(start=0.1, end=1.0, step=0.1, value=1.0),
            "plotstyle": pn.widgets.Select(options=["line", "points", "both"], value="line"),
            "show_seasons": pn.widgets.Checkbox(value=False),
            "interpolate": pn.widgets.Checkbox(value=False),
            "lower_threshold_val": pn.widgets.FloatInput(value=None),
            "lower_threshold_color": pn.widgets.ColorPicker(value="#ff0000"),
            "upper_threshold_val": pn.widgets.FloatInput(value=None),
            "upper_threshold_color": pn.widgets.ColorPicker(value="#0000ff"),
            "apply_shading_to_all": pn.widgets.Checkbox(value=False),
        }

        if is_overlay:
            widgets["add_second_axis"] = pn.widgets.Checkbox(value=False)
            widgets["align_zero"] = pn.widgets.Checkbox(value=False)
            widgets["compute_corr"] = pn.widgets.Checkbox(value=False)
            widgets["remove_btn"] = pn.widgets.Button(label="Remove", color="danger", width=80)

        for key, widget in widgets.items():
            if hasattr(widget, "param") and hasattr(widget.param, "value"):
                widget.param.watch(self._on_widget_change, "value")

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
        return pn.Accordion(
            (
                "Advanced",
                pn.Column(
                    pn.Row(
                        pn.Column(widgets["line_width"], widgets["alpha"], width=200),
                        pn.Column(widgets["show_seasons"], widgets["interpolate"], width=200),
                        pn.Column(widgets["plotstyle"], width=200),
                    ),
                    pn.Row(
                        pn.Column(widgets["lower_threshold_val"], widgets["lower_threshold_color"], width=200),
                        pn.Column(widgets["upper_threshold_val"], widgets["upper_threshold_color"], width=200),
                        widgets["apply_shading_to_all"],
                    ),
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
                pn.Column(primary["name"], width=250),
                pn.Column(primary["color"], width=100),
                pn.Column(primary["label"], width=200),
                margin=(5, 5, 0, 5),
            )
            primary_advanced = self._create_advanced_accordion(primary)

            overlay_rows = []
            for ov_idx, ov in enumerate(sp["overlays"]):
                ov_row = pn.Row(
                    pn.Column(ov["name"], width=250),
                    pn.Column(ov["color"], width=100),
                    pn.Column(ov["label"], width=200),
                    pn.Column(ov["add_second_axis"], ov["align_zero"], width=200),
                    ov["remove_btn"],
                    margin=(5, 5, 0, 5),
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
                "show_seasons": primary["show_seasons"].value,
                "interpolate": primary["interpolate"].value,
            }

            lower_val = primary["lower_threshold_val"].value
            if lower_val is not None:
                primary_spec["lower_treshold"] = (lower_val, primary["lower_threshold_color"].value)

            upper_val = primary["upper_threshold_val"].value
            if upper_val is not None:
                primary_spec["upper_treshold"] = (upper_val, primary["upper_threshold_color"].value)

            if primary["apply_shading_to_all"].value:
                primary_spec["apply_shading_to_all"] = True

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
                    "show_seasons": ov["show_seasons"].value,
                    "interpolate": ov["interpolate"].value,
                    "add_to": primary_name,
                }

                if ov["add_second_axis"].value:
                    ov_spec["add_second_axis"] = True
                if ov["align_zero"].value:
                    ov_spec["align_zero"] = True
                if ov["compute_corr"].value:
                    ov_spec["compute_corr"] = True

                lower_val = ov["lower_threshold_val"].value
                if lower_val is not None:
                    ov_spec["lower_treshold"] = (lower_val, ov["lower_threshold_color"].value)

                upper_val = ov["upper_threshold_val"].value
                if upper_val is not None:
                    ov_spec["upper_treshold"] = (upper_val, ov["upper_threshold_color"].value)

                if ov["apply_shading_to_all"].value:
                    ov_spec["apply_shading_to_all"] = True

                specs.append(ov_spec)

        return specs

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
