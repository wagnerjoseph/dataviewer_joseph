# dataviewer_joseph

Interactive geospatial timeseries data viewer for Earth observation data with integrated ML model evaluation.

## Features

- **Interactive Map**: GeoViews-based map with OSM basemap, clickable points, and highlight markers
- **Timeseries Visualization**: Multi-panel timeseries via `plotting_joseph` with configurable `var_specs`
- **Interactive var_specs Editor**: Configure timeseries plots without code - add variables, overlays, secondary axes, thresholds, seasons, correlations via Panel widgets
- **Map Data Table**: All variable values for the selected location in a single table
- **Additional Data Viewer**: Per-location attributes with selectable renderer (bar, scatter, table, histogram, box)
- **Auto-Discovery**: Automatically discovers splits, variables, and locations from parquet files
- **Data Preparation Tool**: CLI to prepare data from raw inputs into dataviewer-ready format

## Installation

Install the package directly from GitHub (no need to clone the repository):

```bash
uv add git+https://github.com/wagnerjoseph/dataviewer_joseph.git
```

For development (editable install with the repo cloned locally):

```bash
git clone https://github.com/wagnerjoseph/dataviewer_joseph.git
cd dataviewer_joseph
uv sync
uv pip install -e .
```

## Quick Start

### Using Dummy Data

```python
from pathlib import Path
from dataviewer_joseph import generate_dummy_data, create_app, DataConfig

# Generate sample data
data_root = Path("/tmp/test_data")
generate_dummy_data(data_root, n_locations=100, n_tiles=4)

# Create and launch the app in your browser
config = DataConfig(root=data_root)
app = create_app(config)
app.show()   # opens the viewer in a new browser tab
```

`app.show()` starts a local server and opens the viewer in your default browser. (`.servable()` is only for embedding in Jupyter notebooks and does not launch a standalone viewer.)

### Running the App

```bash
# Serve the app
panel serve scripts/run_app.py --show

# Or with custom data
python scripts/run_app.py --data /path/to/data/dataviewer
```

## Data Structure

The app expects data in the following structure (all column/subfolder names are configurable):

```
data_root/
├── ers_tile_id_location_id.parquet    # location_id, lat, lon, tile_id
├── split_1/
│   ├── metrics_global_plot/           # per-variable map data
│   │   ├── variable_a.parquet         # location_id, variable_a
│   │   ├── variable_b.parquet         # location_id, variable_b
│   │   └── ...
│   ├── additional_data/               # per-location attributes
│   │   ├── 0001.parquet               # location_id + attribute columns
│   │   └── ...
│   └── timeseries/
│       ├── 0001.parquet               # location_id, time, variable_A, variable_B, ...
│       └── ...
└── split_2/
    └── ...
```

## Data Preparation

Use the included preparation script to convert your raw data into the dataviewer format:

```bash
uv run python scripts/prepare_data.py \
    --lookup /path/to/lookup_tables \
    --map-data /path/to/map_data \
    --timeseries /path/to/timeseries \
    --additional-data /path/to/additional_data \
    --output /path/to/output \
    --name dataviewer_auto
```

### Input Folders

- **`--lookup`**: Directory containing `ers_tile_id_location_id.parquet` (location_id, lat, lon, tile_id)
- **`--map-data`**: Directory with split subfolders containing tile parquet files **without** time column (for map visualization)
- **`--timeseries`**: Directory with split subfolders containing tile parquet files **with** time column
- **`--additional-data`** (optional): Directory with split subfolders containing per-location attribute files

All folders should have matching split subfolder names (e.g., `split_1991_2015__2016_2023/`).

### Output Structure

The script creates `dataviewer_auto/` with:
- Lookup table copied to root
- Map data split into `metrics_global_plot/` (one file per variable)
- Timeseries copied to `timeseries/` (per tile)
- Additional data copied to `additional_data/` (per tile)

### Example

```bash
# Prepare data from your raw inputs
uv run python scripts/prepare_data.py \
    --lookup /data/lookup \
    --map-data /data/map \
    --timeseries /data/ts \
    --additional-data /data/attrs \
    --output /data/output

# Run the dataviewer with prepared data
uv run python scripts/run_app.py --data /data/output/dataviewer_auto --show
```

## Using the var_specs Editor

The var_specs editor lets you configure timeseries plots interactively:

1. **Add Variables**: Click "Add Variable" to add a new panel
2. **Configure Each Variable**:
   - **Name**: Select the data column to plot
   - **Label**: Display label for y-axis
   - **Color**: Line color
   - **Line Width/Alpha**: Styling
   - **Plot Style**: line, points, or both
   - **Show Seasons**: Overlay JJA/DJF markers
   - **Interpolate**: Interpolate NaN values
3. **Overlays**: Set "Overlay On" to add a variable to an existing panel
4. **Secondary Axis**: Check "Add Second Y-Axis" for overlays
5. **Thresholds**: Set lower/upper threshold values and colors for shading
6. **Correlation**: Check "Show Correlation" to display Pearson+Spearman correlation

The editor generates a `var_specs` list that is passed to `plotting_joseph.plot_time_series`.

## Additional Data Renderer

When you select a location, per-location attributes from the `additional_data/` folder are displayed with a selectable plot style:

### Available Renderers

- **bar**: Horizontal bar chart (best for ranked numeric values)
- **scatter**: Scatter plot (best for comparing multiple numeric attributes)
- **table**: Key-value table (best for mixed types or detailed inspection)
- **histogram**: Distribution histogram (best for single numeric attribute with many values)
- **box**: Box plot (best for statistical summary)

### Usage

1. Select a location on the map or enter Location ID
2. Use the "Plot Style" dropdown to choose how to visualize the additional data
3. The renderer auto-suggests the best plot type based on data characteristics:
   - Numeric data with few values → bar chart
   - Many numeric values → histogram
   - Mixed types → table

### Data Format

Additional data files should be parquet with:
- `location_id` column
- One or more attribute columns (any type)

Example:
```
location_id | attribute1 | attribute2 | attribute3
123         | 0.85       | 15.2       | "forest"
456         | 0.92       | 12.1       | "urban"
```

## API Reference

### Data Loading

```python
from dataviewer_joseph import (
    DataConfig,
    DataIndex,
    find_splits,
    get_variable_names,
    load_timeseries_for_location,
    load_map_data_for_location,
    load_additional_data_for_location,
    get_timeseries_variables,
)

config = DataConfig(root="/path/to/data")
index = DataIndex(config)

# Discover available splits
print(index.splits)

# Get timeseries variables for var_specs editor
ts_vars = get_timeseries_variables(config, "split_1")

# Load timeseries for a location
ts_data = load_timeseries_for_location(config, "split_1", location_id=123)

# Load all map-data variable values for a location
map_values = load_map_data_for_location(config, "split_1", location_id=123)
```

### var_specs Editor

```python
from dataviewer_joseph import VarSpecEditor

# Create editor with available variables
editor = VarSpecEditor(available_variables=["backscatter40", "lai", "swvl1"])
editor.add_var("backscatter40")
editor.add_var("lai")

# Configure via widgets
editor._var_widgets[0]["label"].value = "Backscatter [dB]"
editor._var_widgets[0]["color"].value = "#0000ff"

# Collect var_specs for plotting
var_specs = editor.to_var_specs()
```

### Plotting

```python
from dataviewer_joseph.plotting import (
    plot_location_timeseries,
    create_map_data_table,
)

# Plot timeseries with var_specs
figs = plot_location_timeseries(
    data=ts_data,
    location_ids=[123],
    var_specs=var_specs,
)

# Map data table (all variables for a location)
map_table = create_map_data_table(map_values)
```

### Configuration

```python
from dataviewer_joseph import DataConfig

# Default schema
config = DataConfig(root="/path/to/data")

# Custom schema
config = DataConfig(
    root="/path/to/data",
    id_column="location_id",
    lookup_file="ers_tile_id_location_id.parquet",
    metrics_subfolder="metrics_global_plot",
    timeseries_subfolder="timeseries",
    additional_data_subfolder="additional_data",
)
```

## Development

### Running Tests

```bash
uv run pytest tests/ -v
```

### Code Quality

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

### Generating Dummy Data

```bash
uv run python scripts/generate_dummy_data.py --output /tmp/test_data --locations 100
```

## Examples

See the `examples/` directory for complete examples:

- `examples/01_basic_app.py` - Basic app usage with dummy data
- `examples/02_var_specs_editor.py` - Interactive var_specs configuration

## Dependencies

- `panel` - Web application framework
- `holoviews` - Declarative objects for data visualization
- `geoviews` - Geospatial extensions for HoloViews
- `bokeh` - Interactive visualization library
- `pandas` - Data manipulation
- `numpy` - Numerical computing
- `matplotlib` - Plotting
- `pyarrow` - Fast parquet I/O
- `plotting_joseph` - Multi-panel timeseries plotting with var_specs

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `uv run pytest`
5. Submit a pull request

## Contact

Joseph Wagner - joseph.wagner@geo.tuwien.ac.at

TU Wien, Institute of Geodesy and Geoinformation
