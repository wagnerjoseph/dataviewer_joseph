"""Data preparation for dataviewer_joseph.

Prepares data from raw input folders into the dataviewer_auto/ structure:
- Lookup table: copied as-is
- Map data (no time): split into metrics_global_plot (per-variable) + metrics_by_tile (per-tile)
- Timeseries (has time): copied per-tile
- Additional data (per-location attributes): copied per-tile
"""

import logging
import shutil
from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)


def discover_splits(
    map_data_dir: Path,
    timeseries_dir: Path,
) -> list[str]:
    """Discover splits that exist in both map_data and timeseries directories.
    
    Args:
        map_data_dir: Directory with split subfolders containing map data tiles
        timeseries_dir: Directory with split subfolders containing timeseries tiles
        
    Returns:
        List of split names present in both directories
        
    Warns about splits missing from either directory.
    """
    map_splits = {d.name for d in map_data_dir.iterdir() if d.is_dir() and not d.name.startswith(".")}
    ts_splits = {d.name for d in timeseries_dir.iterdir() if d.is_dir() and not d.name.startswith(".")}
    
    # Warn about mismatches
    missing_in_map = ts_splits - map_splits
    missing_in_ts = map_splits - ts_splits
    
    if missing_in_map:
        logger.warning(f"Splits found in timeseries but not in map_data: {missing_in_map}")
    if missing_in_ts:
        logger.warning(f"Splits found in map_data but not in timeseries: {missing_in_ts}")
    
    # Return intersection
    common_splits = sorted(map_splits & ts_splits)
    
    if not common_splits:
        raise ValueError(
            f"No common splits found between map_data and timeseries. "
            f"map_data has: {map_splits}, timeseries has: {ts_splits}"
        )
    
    return common_splits


def copy_lookup_table(
    lookup_dir: Path,
    output_dir: Path,
    lookup_filename: str = "ers_tile_id_location_id.parquet",
) -> Path:
    """Copy lookup table to output directory.
    
    Args:
        lookup_dir: Directory containing lookup table
        output_dir: Output directory root
        lookup_filename: Name of lookup table file
        
    Returns:
        Path to copied lookup table
        
    Raises:
        FileNotFoundError: If lookup table not found
    """
    lookup_path = lookup_dir / lookup_filename
    if not lookup_path.exists():
        # Try to find any parquet file in the directory
        parquet_files = list(lookup_dir.glob("*.parquet"))
        if parquet_files:
            lookup_path = parquet_files[0]
            logger.info(f"Using {lookup_path.name} as lookup table")
        else:
            raise FileNotFoundError(f"Lookup table not found in {lookup_dir}")
    
    output_path = output_dir / lookup_filename
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(lookup_path, output_path)
    logger.info(f"Copied lookup table to {output_path}")
    return output_path


def process_map_data(
    split_dir: Path,
    output_split_dir: Path,
    id_column: str = "location_id",
    exclude_columns: Optional[list[str]] = None,
) -> dict[str, int]:
    """Process map data (no time column) for one split.
    
    Creates:
    - metrics_global_plot/<variable>.parquet (one file per variable)
    - metrics_by_tile/<tile_id>.parquet (copy of original tile files)
    
    Args:
        split_dir: Input split directory with tile parquet files
        output_split_dir: Output split directory
        id_column: Location identifier column name
        exclude_columns: Columns to exclude from metrics_global_plot
        
    Returns:
        Dict mapping variable names to number of locations processed
    """
    if exclude_columns is None:
        exclude_columns = ["tile_id", "lat", "lon"]
    
    metrics_global_dir = output_split_dir / "metrics_global_plot"
    metrics_by_tile_dir = output_split_dir / "metrics_by_tile"
    
    metrics_global_dir.mkdir(parents=True, exist_ok=True)
    metrics_by_tile_dir.mkdir(parents=True, exist_ok=True)
    
    # Get all tile files
    tile_files = sorted(split_dir.glob("*.parquet"))
    if not tile_files:
        logger.warning(f"No parquet files found in {split_dir}")
        return {}
    
    # Discover all variable columns from all tiles
    all_variables = set()
    tile_variable_map = {}  # tile_id -> list of variables
    
    for tile_file in tile_files:
        tile_id = tile_file.stem
        try:
            # Read schema without loading data
            pf = pq.ParquetFile(tile_file)
            columns = pf.schema.names
            
            # Exclude id_column and exclude_columns
            variables = [c for c in columns if c != id_column and c not in exclude_columns]
            tile_variable_map[tile_id] = variables
            all_variables.update(variables)
        except Exception as e:
            logger.warning(f"Could not read schema from {tile_file}: {e}")
            continue
    
    if not all_variables:
        logger.warning(f"No variable columns found in {split_dir}")
        return {}
    
    logger.info(f"Found {len(all_variables)} variables across {len(tile_files)} tiles")
    
    # Process each variable: combine across all tiles
    results = {}
    for var_name in sorted(all_variables):
        rows = []
        for tile_file in tile_files:
            try:
                df = pd.read_parquet(tile_file)
                if var_name in df.columns and id_column in df.columns:
                    rows.append(df[[id_column, var_name]])
            except Exception as e:
                logger.warning(f"Error reading {tile_file} for variable {var_name}: {e}")
                continue
        
        if rows:
            combined = pd.concat(rows, ignore_index=True)
            # Remove duplicates (keep first)
            combined = combined.drop_duplicates(subset=[id_column], keep="first")
            # Drop NaN values
            combined = combined.dropna(subset=[var_name])
            
            output_file = metrics_global_dir / f"{var_name}.parquet"
            combined.to_parquet(output_file, compression=None, index=False)
            results[var_name] = len(combined)
            logger.debug(f"  Created {var_name}.parquet with {len(combined)} locations")
    
    # Copy tile files to metrics_by_tile (as-is, no compression)
    for tile_file in tile_files:
        tile_id = tile_file.stem
        output_file = metrics_by_tile_dir / f"{tile_id}.parquet"
        shutil.copy2(tile_file, output_file)
    
    logger.info(f"Processed map data for split {output_split_dir.name}: {len(results)} variables")
    return results


def process_timeseries(
    split_dir: Path,
    output_split_dir: Path,
    lookup_path: Path,
    id_column: str = "location_id",
    tile_column: str = "tile_id",
) -> int:
    """Process timeseries data (has time column) for one split.
    
    Copies tile files and ensures location_id ↔ tile_id consistency via lookup table.
    
    Args:
        split_dir: Input split directory with tile parquet files
        output_split_dir: Output split directory
        lookup_path: Path to lookup table
        id_column: Location identifier column name
        tile_column: Tile identifier column name in lookup table
        
    Returns:
        Number of tiles processed
    """
    timeseries_dir = output_split_dir / "timeseries"
    timeseries_dir.mkdir(parents=True, exist_ok=True)
    
    # Load lookup table
    try:
        lookup = pd.read_parquet(lookup_path)
        location_tile_map = lookup.set_index(id_column)[tile_column].to_dict()
    except Exception as e:
        logger.warning(f"Could not load lookup table: {e}. Proceeding without tile validation.")
        location_tile_map = {}
    
    # Get all tile files
    tile_files = sorted(split_dir.glob("*.parquet"))
    if not tile_files:
        logger.warning(f"No timeseries parquet files found in {split_dir}")
        return 0
    
    tiles_processed = 0
    for tile_file in tile_files:
        tile_id = tile_file.stem
        try:
            df = pd.read_parquet(tile_file)
            
            # Validate location_id ↔ tile_id consistency if we have lookup
            if location_tile_map and id_column in df.columns:
                # Check if all locations in this tile match the expected tile_id
                mismatched = []
                for loc_id in df[id_column].unique():
                    expected_tile = location_tile_map.get(loc_id)
                    if expected_tile and expected_tile != tile_id:
                        mismatched.append((loc_id, expected_tile))
                
                if mismatched:
                    logger.warning(
                        f"Tile {tile_id}: {len(mismatched)} locations have mismatched tile_id in lookup. "
                        f"First few: {mismatched[:3]}"
                    )
            
            # Copy to output (no compression for speed)
            output_file = timeseries_dir / f"{tile_id}.parquet"
            df.to_parquet(output_file, compression=None, index=False)
            tiles_processed += 1
            
        except Exception as e:
            logger.warning(f"Error processing timeseries tile {tile_file}: {e}")
            continue
    
    logger.info(f"Processed {tiles_processed} timeseries tiles for split {output_split_dir.name}")
    return tiles_processed


def process_additional_data(
    split_dir: Path,
    output_split_dir: Path,
    id_column: str = "location_id",
) -> int:
    """Process additional data (per-location attributes) for one split.
    
    Copies tile files to additional_data folder.
    
    Args:
        split_dir: Input split directory with tile parquet files
        output_split_dir: Output split directory
        id_column: Location identifier column name
        
    Returns:
        Number of tiles processed
    """
    additional_data_dir = output_split_dir / "additional_data"
    additional_data_dir.mkdir(parents=True, exist_ok=True)
    
    # Get all tile files
    tile_files = sorted(split_dir.glob("*.parquet"))
    if not tile_files:
        logger.warning(f"No additional data parquet files found in {split_dir}")
        return 0
    
    tiles_processed = 0
    for tile_file in tile_files:
        tile_id = tile_file.stem
        try:
            df = pd.read_parquet(tile_file)
            
            # Validate that id_column exists
            if id_column not in df.columns:
                logger.warning(f"Tile {tile_file} missing {id_column} column, skipping")
                continue
            
            # Copy to output (no compression)
            output_file = additional_data_dir / f"{tile_id}.parquet"
            df.to_parquet(output_file, compression=None, index=False)
            tiles_processed += 1
            
        except Exception as e:
            logger.warning(f"Error processing additional data tile {tile_file}: {e}")
            continue
    
    logger.info(f"Processed {tiles_processed} additional data tiles for split {output_split_dir.name}")
    return tiles_processed


def prepare_dataviewer_data(
    lookup_dir: Path,
    map_data_dir: Path,
    timeseries_dir: Path,
    output_dir: Path,
    additional_data_dir: Optional[Path] = None,
    output_name: str = "dataviewer_auto",
    id_column: str = "location_id",
    exclude_columns: Optional[list[str]] = None,
) -> Path:
    """Prepare data for dataviewer_joseph.
    
    Args:
        lookup_dir: Directory containing lookup table parquet
        map_data_dir: Directory with split subfolders containing map data (no time)
        timeseries_dir: Directory with split subfolders containing timeseries data (has time)
        output_dir: Base output directory
        additional_data_dir: Optional directory with split subfolders containing per-location attributes
        output_name: Name of output subfolder (default: "dataviewer_auto")
        id_column: Location identifier column name
        exclude_columns: Columns to exclude from metrics_global_plot
        
    Returns:
        Path to created output directory
        
    Raises:
        ValueError: If no common splits found or required directories missing
    """
    output_path = output_dir / output_name
    logger.info(f"Preparing dataviewer data...")
    logger.info(f"  Lookup: {lookup_dir}")
    logger.info(f"  Map data: {map_data_dir}")
    logger.info(f"  Timeseries: {timeseries_dir}")
    if additional_data_dir:
        logger.info(f"  Additional data: {additional_data_dir}")
    logger.info(f"  Output: {output_path}")
    
    # Validate inputs
    if not lookup_dir.exists():
        raise FileNotFoundError(f"Lookup directory not found: {lookup_dir}")
    if not map_data_dir.exists():
        raise FileNotFoundError(f"Map data directory not found: {map_data_dir}")
    if not timeseries_dir.exists():
        raise FileNotFoundError(f"Timeseries directory not found: {timeseries_dir}")
    if additional_data_dir and not additional_data_dir.exists():
        logger.warning(f"Additional data directory not found: {additional_data_dir}")
        additional_data_dir = None
    
    # Discover splits
    splits = discover_splits(map_data_dir, timeseries_dir)
    logger.info(f"Found {len(splits)} common splits: {splits}")
    
    # Copy lookup table
    copy_lookup_table(lookup_dir, output_path)
    
    # Process each split
    for split_name in splits:
        logger.info(f"\nProcessing split: {split_name}")
        output_split_dir = output_path / split_name
        
        # Map data
        map_split_dir = map_data_dir / split_name
        if map_split_dir.exists():
            process_map_data(
                map_split_dir,
                output_split_dir,
                id_column=id_column,
                exclude_columns=exclude_columns,
            )
        else:
            logger.warning(f"Map data split {split_name} not found, skipping")
        
        # Timeseries
        ts_split_dir = timeseries_dir / split_name
        if ts_split_dir.exists():
            process_timeseries(
                ts_split_dir,
                output_split_dir,
                lookup_path=output_path / "ers_tile_id_location_id.parquet",
                id_column=id_column,
            )
        else:
            logger.warning(f"Timeseries split {split_name} not found, skipping")
        
        # Additional data (optional)
        if additional_data_dir:
            add_split_dir = additional_data_dir / split_name
            if add_split_dir.exists():
                process_additional_data(
                    add_split_dir,
                    output_split_dir,
                    id_column=id_column,
                )
            else:
                logger.warning(f"Additional data split {split_name} not found, skipping")
    
    logger.info(f"\n✓ Data preparation complete: {output_path}")
    return output_path
