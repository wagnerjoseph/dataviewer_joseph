#!/usr/bin/env python3
"""CLI for preparing dataviewer_joseph data.

Usage:
    uv run python scripts/prepare_data.py \
        --lookup /path/to/lookup_tables \
        --map-data /path/to/map_data \
        --timeseries /path/to/timeseries \
        --additional-data /path/to/additional_data \
        --output /path/to/output \
        --name dataviewer_auto
"""

import argparse
import logging
import sys
from pathlib import Path

from dataviewer_joseph.prepare import prepare_dataviewer_data


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Prepare data for dataviewer_joseph",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Prepare with all data types
    uv run python scripts/prepare_data.py \\
        --lookup /data/lookup_tables \\
        --map-data /data/map_data \\
        --timeseries /data/timeseries \\
        --additional-data /data/additional_data \\
        --output /data/output \\
        --name dataviewer_auto

    # Prepare without additional data
    uv run python scripts/prepare_data.py \\
        --lookup /data/lookup \\
        --map-data /data/map \\
        --timeseries /data/ts \\
        --output /data
        """,
    )
    
    parser.add_argument(
        "--lookup",
        "-l",
        type=Path,
        required=True,
        help="Directory containing lookup table parquet (ers_tile_id_location_id.parquet)",
    )
    
    parser.add_argument(
        "--map-data",
        "-m",
        type=Path,
        required=True,
        help="Directory with split subfolders containing map data (no time column)",
    )
    
    parser.add_argument(
        "--timeseries",
        "-t",
        type=Path,
        required=True,
        help="Directory with split subfolders containing timeseries data (has time column)",
    )
    
    parser.add_argument(
        "--additional-data",
        "-a",
        type=Path,
        default=None,
        help="Optional: Directory with split subfolders containing per-location attributes",
    )
    
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("/tmp/dataviewer_output"),
        help="Output directory base (default: /tmp/dataviewer_output)",
    )
    
    parser.add_argument(
        "--name",
        "-n",
        type=str,
        default="dataviewer_auto",
        help="Output folder name (default: dataviewer_auto)",
    )
    
    parser.add_argument(
        "--id-column",
        type=str,
        default="location_id",
        help="Location identifier column name (default: location_id)",
    )
    
    parser.add_argument(
        "--exclude-columns",
        type=str,
        nargs="+",
        default=None,
        help="Columns to exclude from metrics_global_plot (default: tile_id lat lon)",
    )
    
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    
    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stdout,
    )
    
    # Run preparation
    try:
        output_path = prepare_dataviewer_data(
            lookup_dir=args.lookup,
            map_data_dir=args.map_data,
            timeseries_dir=args.timeseries,
            output_dir=args.output,
            additional_data_dir=args.additional_data,
            output_name=args.name,
            id_column=args.id_column,
            exclude_columns=args.exclude_columns,
        )
        
        print(f"\n✓ Success! Data prepared at: {output_path}")
        print(f"\nTo run the dataviewer:")
        print(f"  uv run python scripts/run_app.py --data {output_path} --show")
        
    except FileNotFoundError as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
