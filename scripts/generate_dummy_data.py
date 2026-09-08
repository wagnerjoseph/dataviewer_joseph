#!/usr/bin/env python3
"""Generate dummy data for testing and development."""

import argparse
from pathlib import Path

from dataviewer_joseph.data import generate_dummy_data


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate dummy data for dataviewer_joseph testing"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("/tmp/dataviewer_test_data"),
        help="Output directory for the data",
    )
    parser.add_argument(
        "--locations",
        "-n",
        type=int,
        default=100,
        help="Number of locations to generate",
    )
    parser.add_argument(
        "--tiles",
        "-t",
        type=int,
        default=4,
        help="Number of tiles",
    )
    parser.add_argument(
        "--splits",
        "-s",
        type=str,
        nargs="+",
        default=None,
        help="Split names (default: split_2020_2022 split_2023_2024)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility",
    )

    args = parser.parse_args()

    print(f"Generating dummy data in {args.output}")
    print(f"  Locations: {args.locations}")
    print(f"  Tiles: {args.tiles}")
    print(f"  Splits: {args.splits or 'default'}")
    print(f"  Seed: {args.seed}")

    config = generate_dummy_data(
        root=args.output,
        n_locations=args.locations,
        n_tiles=args.tiles,
        splits=args.splits,
        seed=args.seed,
    )

    print(f"\nData generated successfully!")
    print(f"Lookup file: {config.lookup_path}")
    for split in config.root.iterdir():
        if split.is_dir() and not split.name.startswith("."):
            print(f"  Split: {split.name}")


if __name__ == "__main__":
    main()
