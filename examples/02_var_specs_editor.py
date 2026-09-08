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

    # Get timeseries variables
    ts_variables = ["backscatter40", "lai", "swvl1", "baseline"]
    print(f"Timeseries variables: {ts_variables}")

    # Create var_specs editor
    editor = VarSpecEditor(available_variables=ts_variables)

    # Add some default variables
    editor.add_var("backscatter40")
    editor.add_var("lai")
    editor.add_var("swvl1")

    # Configure the first variable
    editor._var_widgets[0]["label"].value = "Backscatter [dB]"
    editor._var_widgets[0]["color"].value = "#0000ff"
    editor._var_widgets[0]["line_width"].value = 2.0

    # Configure the second variable
    editor._var_widgets[1]["label"].value = "Leaf Area Index"
    editor._var_widgets[1]["color"].value = "#00aa00"

    # Configure the third variable as overlay on the first
    editor._var_widgets[2]["add_to"].value = "backscatter40"
    editor._var_widgets[2]["add_second_axis"].value = True
    editor._var_widgets[2]["color"].value = "#aa00aa"

    # Collect var_specs
    var_specs = editor.to_var_specs()
    print(f"\nGenerated var_specs:")
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

    # Show the figure (optional)
    # import matplotlib.pyplot as plt
    # plt.show()

    print("\nDone!")
    print("\nTo use the interactive editor in the app:")
    print("1. Run: python scripts/run_app.py --show")
    print("2. Expand the 'Timeseries Configuration' accordion")
    print("3. Add/remove variables and configure via widgets")
    print("4. Click a location on the map to see the plot")


if __name__ == "__main__":
    main()
