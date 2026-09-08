"""Data loading and indexing for dataviewer_joseph."""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .config import DataConfig

logger = logging.getLogger(__name__)


def find_splits(config: DataConfig) -> list[str]:
    """Find all splits in the data root directory.

    Splits are subdirectories containing the metrics_subfolder with parquet
    files. If no such subdirectories exist, the data may be laid out directly
    under the root; in that case a single implicit split ``"."`` (the root
    itself) is returned so the split dimension can be ignored.

    Args:
        config: DataConfig with root path

    Returns:
        List of split names (sorted alphabetically). ``["."]`` for data placed
        directly in the root, ``[]`` when no data is found at all.
    """
    splits = []
    for item in config.root.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            metrics_dir = item / config.metrics_subfolder
            if metrics_dir.exists() and any(metrics_dir.glob("*.parquet")):
                splits.append(item.name)

    if splits:
        return sorted(splits)

    # No split subfolders: fall back to a single implicit split at the root.
    metrics_dir = config.root / config.metrics_subfolder
    if metrics_dir.exists() and any(metrics_dir.glob("*.parquet")):
        return ["."]

    return []


def get_variable_names(config: DataConfig, split: str) -> list[str]:
    """Get list of available variable names from a split's metrics folder.

    Args:
        config: DataConfig instance
        split: Split name

    Returns:
        List of variable names (parquet file stems)
    """
    metrics_dir = config.root / split / config.metrics_subfolder
    if not metrics_dir.exists():
        return []

    variables = [f.stem for f in metrics_dir.glob("*.parquet")]
    return sorted(variables)


def load_location_coordinates(config: DataConfig) -> pd.DataFrame:
    """Load location coordinates from lookup table.

    Args:
        config: DataConfig instance

    Returns:
        DataFrame with location_id, lat, lon, tile_id columns
    """
    if not config.lookup_path.exists():
        raise FileNotFoundError(
            f"Location lookup table not found: {config.lookup_path}"
        )

    coords = pd.read_parquet(config.lookup_path)
    required_cols = [config.id_column, config.lat_col, config.lon_col]
    missing = [col for col in required_cols if col not in coords.columns]
    if missing:
        raise ValueError(f"Lookup table missing required columns: {missing}")

    return coords[
        [config.id_column, config.lon_col, config.lat_col, config.tile_col]
    ].drop_duplicates()


def load_variable_data(config: DataConfig, split: str, variable: str) -> pd.DataFrame:
    """Load combined variable data for a split, merged with coordinates.

    Args:
        config: DataConfig instance
        split: Split name
        variable: Variable name to load

    Returns:
        DataFrame with location_id, variable value, lat, lon
    """
    var_file = config.root / split / config.metrics_subfolder / f"{variable}.parquet"
    if not var_file.exists():
        raise FileNotFoundError(f"Variable file not found: {var_file}")

    var_data = pd.read_parquet(var_file)
    coords = load_location_coordinates(config)
    merged = var_data.merge(coords, on=config.id_column, how="left")
    merged = merged.dropna(subset=[config.lon_col, config.lat_col])
    return merged


def load_location_lookup(config: DataConfig) -> pd.DataFrame:
    """Load location lookup table with tile_id mapping."""
    if not config.lookup_path.exists():
        raise FileNotFoundError(f"Lookup table not found: {config.lookup_path}")
    return pd.read_parquet(config.lookup_path)


def load_timeseries_for_location(
    config: DataConfig,
    split: str,
    location_id: int,
    tile_id: str | None = None,
) -> pd.DataFrame | None:
    """Load timeseries data for a specific location.

    Searches through tile parquet files to find the one containing the location_id.

    Args:
        config: DataConfig instance
        split: Split name
        location_id: Location ID to load
        tile_id: Pre-computed tile ID (optional)

    Returns:
        DataFrame with timeseries data, or None if not found
    """
    timeseries_dir = config.root / split / config.timeseries_subfolder
    if not timeseries_dir.exists():
        return None

    # Use provided tile_id or look it up
    if tile_id is None:
        try:
            lookup = load_location_lookup(config)
            loc_row = lookup[lookup[config.id_column] == location_id]
            if loc_row.empty:
                return None
            tile_id = loc_row[config.tile_col].iloc[0]
        except Exception:
            tile_id = None

    # Load the tile file
    if tile_id:
        tile_file = timeseries_dir / f"{tile_id}.parquet"
        if tile_file.exists():
            ts = pd.read_parquet(tile_file)
            ts_loc = ts[ts[config.id_column] == location_id]
            if not ts_loc.empty:
                return ts_loc

    # Fallback: search all tile files
    for tile_file in timeseries_dir.glob("*.parquet"):
        try:
            ts = pd.read_parquet(tile_file)
            if location_id in ts[config.id_column].values:
                return ts[ts[config.id_column] == location_id]
        except Exception:
            continue

    return None


def load_map_data_for_location(
    config: DataConfig,
    split: str,
    location_id: int,
) -> pd.Series | None:
    """Load all map-data variable values for a specific location.

    Reads each parquet file in the metrics subfolder (one file per variable)
    and extracts the value for the given location.

    Args:
        config: DataConfig instance
        split: Split name
        location_id: Location ID to find

    Returns:
        pandas Series with variable names as index and values as data,
        or None if no data found for the location
    """
    metrics_dir = config.root / split / config.metrics_subfolder
    if not metrics_dir.exists():
        return None

    var_files = sorted(metrics_dir.glob("*.parquet"))
    if not var_files:
        return None

    values = {}
    for var_file in var_files:
        variable = var_file.stem
        try:
            df = pd.read_parquet(var_file)
            if config.id_column not in df.columns or variable not in df.columns:
                continue
            loc_rows = df[df[config.id_column] == location_id]
            if loc_rows.empty:
                continue
            values[variable] = loc_rows.iloc[0][variable]
        except Exception as e:
            logger.warning(f"Error reading {var_file} for location {location_id}: {e}")
            continue

    return pd.Series(values) if values else None


def load_additional_data_for_location(
    config: DataConfig,
    split: str,
    location_id: int,
    tile_id: str | None = None,
) -> pd.Series | None:
    """Load additional data for a specific location.

    Generalized version of load_feature_importance_for_location that loads
    arbitrary per-location attributes from the additional_data subfolder.

    Args:
        config: DataConfig instance
        split: Split name
        location_id: Location ID to find
        tile_id: Pre-computed tile ID (optional)

    Returns:
        pandas Series with attribute names as index, values as data, or None
    """
    additional_base = config.root / split / config.additional_data_subfolder
    if not additional_base.exists():
        return None

    # Look up tile_id if not provided
    if tile_id is None:
        try:
            lookup = load_location_lookup(config)
            loc_row = lookup[lookup[config.id_column] == location_id]
            if loc_row.empty:
                return None
            tile_id = loc_row[config.tile_col].iloc[0]
        except Exception:
            return None

    # Load additional data tile
    tile_file = additional_base / f"{tile_id}.parquet"
    if not tile_file.exists():
        return None

    try:
        df = pd.read_parquet(tile_file)
        loc_row = df[df[config.id_column] == location_id]
        if loc_row.empty:
            return None

        # Extract attributes (all columns except id_column)
        attrs = loc_row.iloc[0].drop(config.id_column)
        return attrs

    except Exception as e:
        logger.warning(f"Error loading additional data for location {location_id}: {e}")
        return None


def get_timeseries_variables(config: DataConfig, split: str) -> list[str]:
    """Get list of numeric variable columns from timeseries files.

    Args:
        config: DataConfig instance
        split: Split name

    Returns:
        List of variable names available in timeseries data
    """
    ts_dir = config.root / split / config.timeseries_subfolder
    if not ts_dir.exists():
        return []

    ts_files = list(ts_dir.glob("*.parquet"))
    if not ts_files:
        return []

    pf = pq.ParquetFile(ts_files[0])
    columns = pf.schema.names
    exclude = {config.id_column, "time"}
    return sorted([c for c in columns if c not in exclude])


def generate_dummy_data(
    root: Path | str,
    n_locations: int = 100,
    n_tiles: int = 4,
    splits: list[str] | None = None,
    variables: list[str] | None = None,
    additional_variables: list[str] | None = None,
    seed: int = 42,
) -> DataConfig:
    """Generate dummy data for testing and development.

    Creates a complete data structure matching the real dataviewer format:
    - lookup.parquet with location_id, lat, lon, tile_id
    - <split>/metrics_global_plot/<variable>.parquet
    - <split>/additional_data/<tile>.parquet with per-location attributes
    - <split>/timeseries/<tile>.parquet with time, location_id, backscatter40, lai, swvl1, predictions

    Args:
        root: Root directory for the data
        n_locations: Number of locations to generate
        n_tiles: Number of tiles
        splits: List of split names (default: ["split_2020_2022", "split_2023_2024"])
        variables: Variable names for metrics_global_plot (default: ["rmse", "mae", "pearson"])
        additional_variables: Attribute columns for additional_data
            (default: ["elevation", "slope", "aspect", "green_cover"])
        seed: Random seed for reproducibility

    Returns:
        DataConfig for the generated data
    """

    rng = np.random.default_rng(seed)
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    if splits is None:
        splits = ["split_2020_2022", "split_2023_2024"]

    if variables is None:
        variables = ["rmse", "mae", "pearson"]

    if additional_variables is None:
        additional_variables = ["elevation", "slope", "aspect", "green_cover"]

    # Generate locations
    location_ids = np.arange(n_locations)
    tile_ids = np.arange(n_tiles)
    lats = rng.uniform(45, 55, n_locations)
    lons = rng.uniform(10, 20, n_locations)
    location_tile_ids = rng.choice(tile_ids, n_locations)

    lookup_df = pd.DataFrame(
        {
            "location_id": location_ids,
            "lat": lats,
            "lon": lons,
            "tile_id": location_tile_ids,
        }
    )
    lookup_df.to_parquet(root / "ers_tile_id_location_id.parquet", index=False)
    logger.info(f"Generated lookup table with {n_locations} locations")

    # Generate data for each split
    date_range = pd.date_range(start="2020-01-01", end="2023-12-31", freq="D")

    for split in splits:
        split_dir = root / split

        # Generate metrics_global_plot (one file per variable)
        metrics_dir = split_dir / "metrics_global_plot"
        metrics_dir.mkdir(parents=True, exist_ok=True)

        for var in variables:
            var_data = pd.DataFrame(
                {
                    "location_id": location_ids,
                    var: rng.normal(0.5, 0.2, n_locations),
                }
            )
            var_data.to_parquet(metrics_dir / f"{var}.parquet", index=False)

        # Generate additional_data (one file per tile with per-location attributes)
        additional_dir = split_dir / "additional_data"
        additional_dir.mkdir(parents=True, exist_ok=True)

        for tile_id in tile_ids:
            tile_locations = location_ids[location_tile_ids == tile_id]
            add_data = pd.DataFrame({"location_id": tile_locations})
            for col in additional_variables:
                if col == "elevation":
                    add_data[col] = rng.uniform(50, 2000, len(tile_locations))
                elif col == "slope":
                    add_data[col] = rng.uniform(0, 45, len(tile_locations))
                elif col == "aspect":
                    add_data[col] = rng.uniform(0, 360, len(tile_locations))
                elif col == "green_cover":
                    add_data[col] = rng.uniform(0, 100, len(tile_locations))
                else:
                    add_data[col] = rng.normal(0, 1, len(tile_locations))
            add_data.to_parquet(additional_dir / f"{tile_id}.parquet", index=False)

        # Generate timeseries
        ts_dir = split_dir / "timeseries"
        ts_dir.mkdir(parents=True, exist_ok=True)

        for tile_id in tile_ids:
            tile_locations = location_ids[location_tile_ids == tile_id]

            rows = []
            for loc_id in tile_locations:
                for date in date_range:
                    day_of_year = date.dayofyear
                    seasonal = np.sin(2 * np.pi * day_of_year / 365)
                    row = {
                        "location_id": loc_id,
                        "time": date,
                        "backscatter40": seasonal + rng.normal(0, 0.5),
                        "lai": 2 + seasonal + rng.normal(0, 0.3),
                        "swvl1": 0.3 + seasonal * 0.1 + rng.normal(0, 0.05),
                        "baseline": seasonal + rng.normal(0, 0.4),
                        "rf_depth5_n300_without_lagged_Core_Only_feat5": seasonal
                        + rng.normal(0, 0.3),
                        "rf_depth20_n300_with_lagged_Core_Short_Lags_feat17": seasonal
                        + rng.normal(0, 0.25),
                    }
                    rows.append(row)

            ts_df = pd.DataFrame(rows)
            ts_df.to_parquet(ts_dir / f"{tile_id}.parquet", index=False)

        logger.info(f"Generated data for split '{split}'")

    return DataConfig(root=root)


class DataIndex:
    """Index for discovering and accessing data."""

    def __init__(self, config: DataConfig) -> None:
        self.config = config
        self.splits = find_splits(config)
        self.locations: pd.DataFrame | None = None
        self._load_locations()

    def _load_locations(self) -> None:
        """Load location coordinates."""
        try:
            self.locations = load_location_coordinates(self.config)
        except Exception as e:
            logger.warning(f"Could not load locations: {e}")
            self.locations = None

    def get_locations_for_split(self, split: str) -> pd.DataFrame | None:
        """Get locations that have data for a specific split."""
        if self.locations is None:
            return None

        metrics_dir = self.config.root / split / self.config.metrics_subfolder
        if not metrics_dir.exists():
            return None

        location_ids = []
        for var_file in metrics_dir.glob("*.parquet"):
            try:
                df = pd.read_parquet(var_file, columns=[self.config.id_column])
                location_ids.extend(df[self.config.id_column].unique().tolist())
            except Exception:
                continue

        if not location_ids:
            return None

        return self.locations[
            self.locations[self.config.id_column].isin(set(location_ids))
        ]
