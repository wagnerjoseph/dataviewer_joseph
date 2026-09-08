"""Configuration for dataviewer_joseph."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DataConfig:
    """Configuration for data paths and schema.

    All column/subfolder names are configurable so the viewer works with
    arbitrary use cases and data layouts.

    Attributes:
        root: Root directory containing lookup and split folders
        id_column: Name of location identifier column
        lookup_file: Name of the lookup file with location coordinates
        metrics_subfolder: Subfolder containing per-variable map data parquet files
        timeseries_subfolder: Subfolder containing timeseries parquet files per tile
        additional_data_subfolder: Subfolder containing additional per-location data
        lat_col: Name of latitude column in lookup
        lon_col: Name of longitude column in lookup
        tile_col: Name of tile identifier column in lookup
        renderer_options: Available renderer types for additional data
        default_renderer: Default renderer type for additional data
    """

    root: Path
    id_column: str = "location_id"
    lookup_file: str = "ers_tile_id_location_id.parquet"
    metrics_subfolder: str = "metrics_global_plot"
    timeseries_subfolder: str = "timeseries"
    additional_data_subfolder: str = "additional_data"
    lat_col: str = "lat"
    lon_col: str = "lon"
    tile_col: str = "tile_id"
    renderer_options: list[str] = field(
        default_factory=lambda: ["bar", "scatter", "table", "histogram", "box"]
    )
    default_renderer: str = "bar"

    def __post_init__(self) -> None:
        if isinstance(self.root, str):
            self.root = Path(self.root)
        self.root = self.root.expanduser().resolve()

    @property
    def lookup_path(self) -> Path:
        """Path to the lookup file."""
        return self.root / self.lookup_file
