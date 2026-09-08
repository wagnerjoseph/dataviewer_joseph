# dataviewer_joseph

Interactive geospatial timeseries data viewer. It plots your Earth-observation data on a map, lets you click a location, and shows its timeseries, per-location values, and attributes — all from a set of parquet files, no coding required.

## Features

- **Interactive Map**: GeoViews map with clickable points and location highlighting
- **Timeseries Visualization**: Multi-panel timeseries, configurable interactively without code
- **Map Data Table**: All variable values for the selected location in one table
- **Additional Data Viewer**: Per-location attributes with selectable plot style
- **Auto-Discovery**: Automatically finds splits, variables, and locations from your data
- **Data Preparation Tool**: Convert raw data into the expected format easily

## Installation

Install the package into your project (any Python project using `uv`):

```bash
uv add git+https://github.com/wagnerjoseph/dataviewer_joseph.git
```

That's it — no need to clone the repository.

## Quick Start

The fastest way to see it working is with generated sample data. This opens the viewer in a **new browser tab**:

```python
from pathlib import Path
from dataviewer_joseph import generate_dummy_data, create_app, DataConfig

# Generate sample data
data_root = Path("/tmp/test_data")
generate_dummy_data(data_root, n_locations=100, n_tiles=4)

# Create and launch the app in your browser
app = create_app(DataConfig(root=data_root))
app.show()   # opens the viewer in a new browser tab
```

## Running the App

`app.show()` starts a local server and opens the viewer in a separate browser tab. This works the same way in a console script and in a notebook.

### From the console

Save the snippet above as `run.py` and run it:

```bash
python run.py
```

### From a notebook

The exact same `app.show()` works in a Jupyter notebook and opens a separate browser tab:

```python
from dataviewer_joseph import create_app, DataConfig, generate_dummy_data

data_root = generate_dummy_data("/tmp/test_data")  # returns a DataConfig
app = create_app(data_root)
app.show()
```

> **Note:** `.servable()` is only for serving a notebook via `panel serve` and does **not** launch a standalone viewer. Use `app.show()` instead.

### With your own data

Point the app at a prepared data folder and launch it:

```python
from dataviewer_joseph import create_app, DataConfig

app = create_app(DataConfig(root="/path/to/my/data/dataviewer_auto"))
app.show()
```

## Data Structure

The app reads a root folder containing a lookup table and numbered `split_*` subfolders. All column and folder names are configurable; this is the default layout:

```
data_root/
├── ers_tile_id_location_id.parquet    # location_id, lat, lon, tile_id
├── split_1/
│   ├── metrics_global_plot/           # per-variable map data
│   │   ├── variable_a.parquet         # location_id, variable_a
│   │   └── ...
│   ├── additional_data/               # per-location attributes
│   │   └── 0001.parquet               # location_id + attribute columns
│   └── timeseries/
│       └── 0001.parquet               # location_id, time, variable_A, ...
└── split_2/
    └── ...
```

## Preparing Your Data

The `prepare` module converts your raw data into the expected layout. This works in any project after installing the package:

```python
from dataviewer_joseph.prepare import prepare_dataviewer_data

out = prepare_dataviewer_data(
    lookup_dir="/path/to/lookup_tables",      # ers_tile_id_location_id.parquet
    map_data_dir="/path/to/map_data",         # split folders, no time column
    timeseries_dir="/path/to/timeseries",     # split folders, with time column
    additional_data_dir="/path/to/additional_data",  # optional
    output_dir="/path/to/output",
    output_name="dataviewer_auto",
)
print(out)   # path to the prepared data
```

## Using the Viewer

1. Choose a **Split** and **Variable** for the map.
2. Click a point on the map, or type a **Location ID**, to select a location.
3. The selected location shows its **timeseries**, a **table with all its variable values** from the map data, and its **additional data**.
4. Use the **Plot Style** dropdown to change how the additional data is rendered (bar, scatter, table, histogram, box).

## API Reference (brief)

```python
from dataviewer_joseph import DataConfig, DataIndex

config = DataConfig(root="/path/to/data")          # customize column/folder names here
index = DataIndex(config)                           # discovers splits & locations

print(index.splits)                                  # available splits
```

Main data loaders (all take `config`, `split`, `location_id`):

- `load_timeseries_for_location(...)` — timeseries rows
- `load_map_data_for_location(...)` — all variable values from the map data
- `load_additional_data_for_location(...)` — per-location attributes

## Development

For contributors working on the source repository.

```bash
# Clone and set up
git clone https://github.com/wagnerjoseph/dataviewer_joseph.git
cd dataviewer_joseph
uv sync
uv pip install -e .
```

Run the app with the included script and sample data:

```bash
uv run python scripts/run_app.py --show                  # dummy data
uv run python scripts/run_app.py --data /path/to/data --show
```

Generate dummy data and run tests/lint:

```bash
uv run python scripts/generate_dummy_data.py --output /tmp/test_data --locations 100
uv run pytest tests/ -v
uv run ruff check src/ tests/
```

See the `examples/` directory for complete example scripts.

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `uv run pytest`
5. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Contact

Joseph Wagner - joseph.wagner@geo.tuwien.ac.at

TU Wien, Institute of Geodesy and Geoinformation
