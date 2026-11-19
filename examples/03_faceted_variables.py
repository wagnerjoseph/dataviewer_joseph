#!/usr/bin/env python3
"""Faceted example: dataset using the optional variable-grouping UI.

Generate dummy data whose variable names follow the example facet
vocabulary (e.g. ``lai_deviation_year``, ``swvl1_deviation_month``,
``rho_bias_lai_year``, ``prediction_linear``) and open the viewer with
it. The app then shows:

- **Map picker**: filter dropdowns for group / scale / model / metric
  (independent, interchangeable) narrowing the variable list.
- **Timeseries config**: the var_spec editor's per-variable facet chains
  (one dropdown per facet instead of one big variable dropdown).

Run from the repository root:

    uv run python examples/03_faceted_variables.py
"""

from pathlib import Path

from dataviewer_joseph import create_app, generate_dummy_data

data_root = Path("/tmp/dataviewer_faceted_example")

print(f"Generating faceted dummy data at {data_root}...")
config = generate_dummy_data(
    data_root,
    n_locations=200,
    n_tiles=2,
    faceted=True,
)
print(f"Facet vocabulary enabled: {config.facet_vocab}")

print("\nCreating app...")
app = create_app(config)
print("  - map filter dropdowns: Group, Scale, Model, Metric")
print("  - timeseries config: per-variable facet chains in the editor")
print("\nOpening app in browser...")
app.show()

# Or serve it programmatically:
# app.servable()
# print("App served at http://localhost:5000")
