"""Configuration for dataviewer_joseph."""

from dataclasses import dataclass
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
        config_subfolder: Subfolder where saved var configs are stored
        facet_vocab: Optional vocabulary that activates variable grouping.
            Maps a facet name (e.g. ``"group"``, ``"scale"``, ``"model"``)
            to the token values that identify it in column names, e.g.
            ``{"group": ["lai", "swvl1"], "scale": ["year", "month"],
            "model": ["linear", "tree", "ridge"]}``. Names are split on
            ``"_"``; a name carries the facet value if any of its tokens is
            in the vocabulary. When ``None`` (default) no grouping UI is
            shown and the viewer works with plain flat variable lists.
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
    config_subfolder: str = "config"
    facet_vocab: dict[str, list[str]] | None = None

    def __post_init__(self) -> None:
        if isinstance(self.root, str):
            self.root = Path(self.root)
        self.root = self.root.expanduser().resolve()
        if self.facet_vocab is None:
            self.facet_vocab = self._load_facet_vocab()

    def _load_facet_vocab(self) -> dict[str, list[str]] | None:
        """Adopt a ``facet_vocab`` stored in the data folder, if any.

        ``generate_dummy_data(faceted=True)`` (and any preparer) may write
        ``dataviewer_meta.json`` next to the lookup table so the viewer
        enables its variable-grouping UI for an existing data directory
        without passing the vocabulary in code. An explicit ``facet_vocab``
        argument always wins.
        """
        import json

        meta_path = self.root / "dataviewer_meta.json"
        try:
            if meta_path.is_file():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                vocab = meta.get("facet_vocab")
                if isinstance(vocab, dict):
                    return vocab
        except Exception:
            pass
        return None

    @property
    def lookup_path(self) -> Path:
        """Path to the lookup file."""
        return self.root / self.lookup_file

    @property
    def config_dir(self) -> Path:
        """Directory where saved var configs are stored."""
        return self.root / self.config_subfolder
