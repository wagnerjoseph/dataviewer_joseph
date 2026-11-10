#!/usr/bin/env python3
"""API usage example: Load data and create plots programmatically."""

from pathlib import Path

from dataviewer_joseph import (
    DataConfig,
    DataIndex,
    generate_dummy_data,
    get_variable_names,
    load_timeseries_for_location,
    load_variable_data,
)
from dataviewer_joseph.plotting import plot_location_timeseries


def main() -> None:
    # Generate dummy data
    data_root = Path("/tmp/dataviewer_api_example")
    print(f"Generating dummy data at {data_root}...")
    generate_dummy_data(data_root, n_locations=50, n_tiles=2)

    # Create configuration and index
    config = DataConfig(root=data_root)
    index = DataIndex(config)

    print(f"\nAvailable splits: {index.splits}")

    # Example 1: Load map data
    print("\n--- Example 1: Map Data ---")
    split = index.splits[0]
    variables = get_variable_names(config, split)
    print(f"Map variables: {variables}")
    variable = variables[0]

    print(f"Loading map data for {split}/{variable}...")
    map_data = load_variable_data(config, split, variable)
    print(f"Loaded {len(map_data)} locations")
    print(f"Columns: {map_data.columns.tolist()}")

    # Example 2: Load and plot timeseries
    print("\n--- Example 2: Timeseries Data ---")
    location_id = index.locations["location_id"].iloc[0]
    print(f"Loading timeseries for location {location_id}...")

    ts_data = load_timeseries_for_location(config, split, location_id)
    print(f"Loaded {len(ts_data)} time points")
    print(f"Columns: {ts_data.columns.tolist()}")

    print("Creating timeseries plot...")
    var_specs = [
        {"name": "backscatter40", "label": "Backscatter"},
        {"name": "lai", "label": "LAI"},
        {"name": "swvl1", "label": "Soil Moisture"},
    ]
    figs = plot_location_timeseries(
        data=ts_data,
        location_ids=[location_id],
        var_specs=var_specs,
    )
    print(f"Created {len(figs)} figure(s)")

    # Save the figure
    output_path = data_root / "timeseries_example.png"
    figs[0].savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Figure saved to {output_path}")
    print("\nDone!")


if __name__ == "__main__":
    main()
