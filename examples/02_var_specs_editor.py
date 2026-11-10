#!/usr/bin/env python3
"""Example: Using the interactive var_specs editor."""

from pathlib import Path

from dataviewer_joseph import (
    DataConfig,
    DataIndex,
    VarSpecEditor,
    generate_dummy_data,
    load_timeseries_for_location,
)
from dataviewer_joseph.plotting import plot_location_timeseries


def main() -> None:
    """Main entry point."""
    # Generate dummy data
    data_root = Path("/tmp/dataviewer_varspec_example")
    print(f"Generating dummy data at {data_root}...")
    generate_dummy_data(data_root, n_locations=50, n_tiles=2)

    # Create configuration and index
    config = DataConfig(root=data_root)
    index = DataIndex(config)

    print(f"\nAvailable splits: {index.splits}")

    # Timeseries variables of the dummy data
    ts_variables = ["backscatter40", "lai", "swvl1", "baseline"]
    print(f"Timeseries variables: {ts_variables}")

    # Create var_specs editor and load a configuration
    editor = VarSpecEditor(available_variables=ts_variables)
    editor.from_var_specs(
        [
            {"name": "backscatter40", "label": "Backscatter [dB]", "color": "#0000ff"},
            {"name": "lai", "label": "Leaf Area Index", "color": "#00aa00"},
            {
                "name": "swvl1",
                "label": "Soil Moisture",
                "color": "#aa00aa",
                "add_to": "backscatter40",
                "add_second_axis": True,
            },
        ]
    )

    # Collect var_specs (what the app sends to plotting_joseph)
    var_specs = editor.to_var_specs()
    print("\nGenerated var_specs:")
    for i, spec in enumerate(var_specs):
        print(f"  {i+1}. {spec['name']} -> {spec.get('add_to', 'new panel')}")

    # Load timeseries for a location
    location_id = index.locations["location_id"].iloc[0]
    print(f"\nLoading timeseries for location {location_id}...")

    ts_data = load_timeseries_for_location(config, "split_2020_2022", location_id)
    print(f"Loaded {len(ts_data)} time points")

    # Plot timeseries with var_specs
    print("Creating timeseries plot...")
    figs = plot_location_timeseries(
        data=ts_data,
        location_ids=[location_id],
        var_specs=var_specs,
    )

    # Save the figure
    output_path = data_root / "timeseries_varspec_example.png"
    figs[0].savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Figure saved to {output_path}")

    print("\nDone!")
    print("\nTo use the interactive editor in the app:")
    print("1. Run: python scripts/run_app.py --show")
    print("2. Open the 'Config' panel (cog button on the map)")
    print("3. Add/remove variables and configure via widgets")
    print("4. Click a location on the map to see the plot")


if __name__ == "__main__":
    main()
