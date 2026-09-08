#!/usr/bin/env python3
"""API usage example: Load data and create plots programmatically."""

import matplotlib.pyplot as plt
from pathlib import Path

from dataviewer_joseph import (
    DataConfig,
    DataIndex,
    create_interactive_map,
    generate_dummy_data,
    load_map_variable,
    load_timeseries_for_location,
    plot_location_timeseries,
)

# Generate dummy data
data_root = Path("/tmp/dataviewer_api_example")
print(f"Generating dummy data at {data_root}...")
generate_dummy_data(data_root, n_locations=50, n_tiles=2)

# Create configuration and index
config = DataConfig(root=data_root)
index = DataIndex(config)

print(f"\nAvailable splits: {index.splits}")
print(f"Map variables: {index.map_variables}")
print(f"Timeseries variables: {index.timeseries_variables}")

# Example 1: Load and display map data
print("\n--- Example 1: Map Data ---")
split = index.splits[0]
variable = index.map_variables[0]

print(f"Loading map data for {split}/{variable}...")
map_data = load_map_variable(config, split, variable)

if isinstance(map_data, dict):
    # Combine all tiles
    import pandas as pd

    map_df = pd.concat(map_data.values(), ignore_index=True)
else:
    map_df = map_data

print(f"Loaded {len(map_df)} locations")
print(f"Columns: {map_df.columns.tolist()}")

# Create interactive map
print("Creating interactive map...")
map_plot = create_interactive_map(
    data=map_df,
    variable=variable,
    width=800,
    height=600,
    cmap="RdYlBu_r",
)
print(f"Map created: {type(map_plot)}")

# Example 2: Load and plot timeseries
print("\n--- Example 2: Timeseries Data ---")
location_id = index.locations["location_id"].iloc[0]
print(f"Loading timeseries for location {location_id}...")

ts_data = load_timeseries_for_location(config, split, location_id)
print(f"Loaded {len(ts_data)} time points")
print(f"Columns: {ts_data.columns.tolist()}")

# Plot timeseries
print("Creating timeseries plot...")
fig = plot_location_timeseries(
    data=ts_data,
    variables=index.timeseries_variables[:2],  # Plot first 2 variables
    location_id=location_id,
    split_name=split,
)
print(f"Figure created: {type(fig)}")

# Save the figure
output_path = data_root / "timeseries_example.png"
fig.savefig(output_path, dpi=150, bbox_inches="tight")
print(f"Figure saved to {output_path}")

plt.close(fig)

# Example 3: Custom plotting with multiple variables
print("\n--- Example 3: Custom Plotting ---")
print("Creating custom timeseries with all variables...")

fig2 = plot_location_timeseries(
    data=ts_data,
    variables=index.timeseries_variables,  # All variables
    location_id=location_id,
    split_name=split,
)

output_path2 = data_root / "timeseries_all_vars.png"
fig2.savefig(output_path2, dpi=150, bbox_inches="tight")
print(f"Figure saved to {output_path2}")

plt.close(fig2)

print("\nDone! Check the output files:")
print(f"  - {output_path}")
print(f"  - {output_path2}")
