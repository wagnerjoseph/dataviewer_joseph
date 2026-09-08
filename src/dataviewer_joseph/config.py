"""Configuration for dataviewer_joseph."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DataConfig:
    """Configuration for data paths and schema.

    All column/subfolder/model names are configurable for reusability,
    with defaults matching the backscatter analysis schema.

    Attributes:
        root: Root directory containing lookup and split folders
        id_column: Name of location identifier column
        lookup_file: Name of the lookup file with location coordinates
        metrics_subfolder: Subfolder containing per-variable metric parquet files
        timeseries_subfolder: Subfolder containing timeseries parquet files per tile
        feature_importance_subfolder: Subfolder containing feature importance data
        metrics_by_tile_subfolder: Subfolder containing metrics-by-tile parquet files
        additional_data_subfolder: Subfolder containing additional per-location data
        lat_col: Name of latitude column in lookup
        lon_col: Name of longitude column in lookup
        tile_col: Name of tile identifier column in lookup
        fi_model_subfolders: Model subfolder names within feature_importance
        fi_col_prefix: Prefix for feature importance columns
        metric_models: Model display names -> {metric: (column_suffix, direction)}
            direction is 'min' for RMSE/MAE, 'max' for Pearson
        renderer_options: Available renderer types for additional data
        default_renderer: Default renderer type for additional data
    """

    root: Path
    id_column: str = "location_id"
    lookup_file: str = "ers_tile_id_location_id.parquet"
    metrics_subfolder: str = "metrics_global_plot"
    timeseries_subfolder: str = "timeseries"
    feature_importance_subfolder: str = "feature_importance"
    metrics_by_tile_subfolder: str = "metrics_by_tile"
    additional_data_subfolder: str = "additional_data"
    lat_col: str = "lat"
    lon_col: str = "lon"
    tile_col: str = "tile_id"
    fi_model_subfolders: tuple[str, ...] = ("without_lag", "with_lag")
    fi_col_prefix: str = "fi_"
    metric_models: dict[str, dict[str, tuple[str, str]]] = field(
        default_factory=lambda: {
            "Baseline": {
                "RMSE": ("baseline_rmse", "min"),
                "MAE": ("baseline_mae", "min"),
                "Pearson": ("baseline_pearson", "max"),
            },
            "RF (Without Lag)": {
                "RMSE": ("rf_depth5_n300_without_lagged_Core_Only_feat5_rmse", "min"),
                "MAE": ("rf_depth5_n300_without_lagged_Core_Only_feat5_mae", "min"),
                "Pearson": (
                    "rf_depth5_n300_without_lagged_Core_Only_feat5_pearson",
                    "max",
                ),
            },
            "RF (With Lag)": {
                "RMSE": (
                    "rf_depth20_n300_with_lagged_Core_Short_Lags_feat17_rmse",
                    "min",
                ),
                "MAE": (
                    "rf_depth20_n300_with_lagged_Core_Short_Lags_feat17_mae",
                    "min",
                ),
                "Pearson": (
                    "rf_depth20_n300_with_lagged_Core_Short_Lags_feat17_pearson",
                    "max",
                ),
            },
        }
    )
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
