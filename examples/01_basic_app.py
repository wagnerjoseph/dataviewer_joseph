#!/usr/bin/env python3
"""Basic example: Create and display the dataviewer_joseph app."""

from pathlib import Path

from dataviewer_joseph import DataConfig, create_app, generate_dummy_data, DataIndex

# Generate dummy data for demonstration
data_root = Path("/tmp/dataviewer_example_data")
print(f"Generating dummy data at {data_root}...")
generate_dummy_data(data_root, n_locations=100, n_tiles=4)

# Create configuration
config = DataConfig(root=data_root)

# Discover available data
index = DataIndex(config)
print(f"\nDiscovered {len(index.splits)} splits: {index.splits}")
print(f"Locations: {len(index.locations)}")

# Create the app
print("\nCreating app...")
print("The app includes:")
print("  - Interactive map with OSM basemap")
print("  - Split and variable selectors")
print("  - Location ID input (or click on map)")
print("  - Timeseries via plotting_joseph with var_specs editor")
print("  - Feature importance bar charts")
print("  - Metrics comparison table")
app = create_app(config)

# Display the app (opens in browser)
print("\nOpening app in browser...")
print("(Expand 'Timeseries Configuration' to configure var_specs interactively)")
app.show()

# Or serve it programmatically:
# app.servable()
# print("App served at http://localhost:5000")
