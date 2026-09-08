"""Renderer selector widget for additional data visualization.

Provides a dropdown to select how additional data should be rendered.
"""

from collections.abc import Callable

import panel as pn
import param

from .renderers import RENDERERS, suggest_renderer


class RendererSelector(param.Parameterized):
    """Widget for selecting renderer type for additional data.
    
    Features:
    - Dropdown with available renderer types
    - Auto-suggestion based on data characteristics
    - Callback when selection changes
    """
    
    renderer_type = param.Selector(
        default="bar",
        objects=list(RENDERERS.keys()),
        doc="Selected renderer type",
    )
    
    auto_suggest = param.Boolean(
        default=True,
        doc="If True, auto-suggest renderer based on data",
    )
    
    def __init__(
        self,
        available_renderers: list[str] | None = None,
        default_renderer: str = "bar",
        on_change: Callable | None = None,
        **params,
    ):
        """Initialize renderer selector.
        
        Args:
            available_renderers: List of renderer type names to offer
            default_renderer: Default renderer type
            on_change: Callback called when renderer changes
        """
        super().__init__(**params)
        
        if available_renderers:
            self.param.renderer_type.objects = available_renderers
        
        self.renderer_type = default_renderer
        self.on_change = on_change
        
        # Create widget
        self._widget = pn.widgets.Select(
            name="Plot Style",
            options=list(RENDERERS.keys()),
            value=default_renderer,
        )
        
        # Wire up callback
        self._widget.param.watch(self._on_widget_change, "value")
    
    def _on_widget_change(self, event):
        """Handle widget value change."""
        self.renderer_type = event.new
        if self.on_change:
            self.on_change(event.new)
    
    @property
    def layout(self) -> pn.widgets.Select:
        """Get the widget layout."""
        return self._widget
    
    def set_data(self, attrs: dict | None):
        """Update selector based on data characteristics.
        
        If auto_suggest is True, suggests best renderer for the data.
        
        Args:
            attrs: Attribute data (Series or dict), or None to clear
        """
        if attrs is None:
            return
        
        if self.auto_suggest:
            suggested = suggest_renderer(attrs)
            if suggested in self.param.renderer_type.objects:
                # Prevent triggering callback during update
                self._widget.param.update(value=suggested)
    
    def get_renderer_type(self) -> str:
        """Get currently selected renderer type."""
        return self.renderer_type


def create_renderer_selector(
    available_renderers: list[str] | None = None,
    default_renderer: str = "bar",
    on_change: Callable | None = None,
    auto_suggest: bool = True,
) -> RendererSelector:
    """Create a renderer selector widget.
    
    Args:
        available_renderers: List of renderer types to offer
        default_renderer: Default renderer type
        on_change: Callback when selection changes
        auto_suggest: If True, auto-suggest based on data
        
    Returns:
        RendererSelector instance
    """
    selector = RendererSelector(
        available_renderers=available_renderers,
        default_renderer=default_renderer,
        on_change=on_change,
        auto_suggest=auto_suggest,
    )
    return selector
