# dataviewer_joseph

Interactive geospatial timeseries data viewer. It plots your Earth-observation data on a map, lets you click a location, and shows its timeseries, per-location values, and attributes — all from a set of parquet files, no coding required.

## Features

- **Interactive Map**: GeoViews map with clickable points and location highlighting.
  Clicks are snapped to the nearest location (within 50 km by default).
- **Timeseries Visualization**: Multi-panel timeseries, configurable interactively without code
- **Map Data Table**: All variable values for the selected location in one table
- **Additional Data Viewer**: Per-location attributes with auto-selected rendering
- **Auto-Discovery**: Automatically finds splits, variables, and locations from your data
- **Data Preparation Tool**: Convert raw data into the expected format easily
- **Variable Groups (optional)**: When a `facet_vocab` is configured, the map
  variable picker gains independent filter dropdowns (e.g. group, timescale,
  model) and the timeseries config offers per-variable facet selectors,
  making large flat variable lists easy to navigate

## Installation

Install the package into your project (any Python project using `uv`):

```bash
uv add git+https://github.com/wagnerjoseph/dataviewer_joseph.git
```

That's it — no need to clone the repository.

---

## Run from the command line (bash)

This is the quickest way to open the viewer. The `scripts/run_app.py` launcher lives in the repository, so **clone the repo first**:

```bash
git clone https://github.com/wagnerjoseph/dataviewer_joseph.git
cd dataviewer_joseph

# plotting_joseph is pulled from git (not PyPI), so uv sync resolves it automatically.
uv sync
```

### Quick start with dummy data

Generates sample data and opens the viewer in a new browser tab:

```bash
uv run python scripts/run_app.py --show
```

### With your own data

```bash
uv run python scripts/run_app.py --data /path/to/my/data/dataviewer_auto --show
```

### Choosing the host and port

By default the app serves on `http://localhost:5000`. Control where it is served from with `--port` and `--address` (alias `--host`):

```bash
# Local only
uv run python scripts/run_app.py

# Accessible to others on your network (0.0.0.0 binds to all interfaces)
uv run python scripts/run_app.py --address 0.0.0.0

# All parameters
uv run python scripts/run_app.py \
    --data /path/to/my/data/dataviewer_auto \
    --port 3000 \
    --address 0.0.0.0 \
    --allow-websocket-origin 192.168.1.23:3000 \
    --show
```

If a hostname does not resolve, find your LAN IP with `hostname -I` and pass it instead, e.g. `--address 192.168.1.23`.

### Accessing from other machines

The **machine's short hostname is allowed automatically** as a WebSocket origin,
so `http://jwagner:3000` works out of the box. Just bind the server to all
interfaces and pick a port:

```bash
uv run python scripts/run_app.py --data /path/to/data --port 3000 --address 0.0.0.0
```

Others on the same network then open `http://jwagner:3000` (or your LAN IP). To
find your LAN IP:

```bash
hostname -I        # e.g. 192.168.1.23
```

Verify from another device on the same network (not the serving machine):

```bash
ping jwagner                            # does the hostname reach the IP?
curl -s -o /dev/null -w "%{http_code}\n" http://jwagner:3000    # expect 200
```

If a colleague reaches you through a different name/IP that is **not** your
hostname (e.g. a direct IP), add it explicitly with `--allow-websocket-origin`
(repeatable):

```bash
uv run python scripts/run_app.py --data /path/to/data --port 3000 --address 0.0.0.0 \
    --allow-websocket-origin 192.168.1.23:3000
```

### Preparing data from bash

Convert raw data into the expected `dataviewer_auto` layout:

```bash
uv run python scripts/prepare_data.py \
    --lookup /path/to/lookup_tables \
    --map-data /path/to/map_data \
    --timeseries /path/to/timeseries \
    --additional-data /path/to/additional_data \
    --output /path/to/output
```

This creates `/path/to/output/dataviewer_auto/` (including a `config/` folder for saved var configs — see below).

---

## Run from code (Python)

This works in **any** `uv` project after installing the package — no clone required.

### Quick start with dummy data

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

### With your own data

First convert your raw data into the expected layout with the `prepare` module:

```python
from dataviewer_joseph.prepare import prepare_dataviewer_data

out = prepare_dataviewer_data(
    lookup_dir="/path/to/lookup_tables",      # ers_tile_id_location_id.parquet
    map_data_dir="/path/to/map_data",         # tiles, no time column
    timeseries_dir="/path/to/timeseries",     # tiles, with time column
    additional_data_dir="/path/to/additional_data",  # optional
    output_dir="/path/to/output",
    output_name="dataviewer_auto",
)
print(out)   # path to the prepared data
```

The map/timeseries tiles can be inside `split_*` subfolders, **or** placed directly in the folders (treated as a single split — that works too).

Then point the app at the prepared folder and launch it:

```python
from dataviewer_joseph import create_app, DataConfig

app = create_app(DataConfig(root="/path/to/my/data/dataviewer_auto"))
app.show()
```

You can also serve the app programmatically instead of opening a browser:

```python
from dataviewer_joseph import create_app, DataConfig

app = create_app(DataConfig(root="/path/to/my/data/dataviewer_auto"))
app.servable()   # serve via `panel serve app.py`
```

For full control over where the app is served (the same options as the bash
`run_app.py`), use `serve_app` — the machine's short hostname is automatically
an allowed WebSocket origin, so `http://jwagner:3000` works out of the box:

```python
from dataviewer_joseph import create_app, DataConfig, serve_app

app = create_app(DataConfig(root="/path/to/my/data/dataviewer_auto"))

# Local only
serve_app(app, port=3000, address="localhost")

# Accessible to others on your network (0.0.0.0 binds to all interfaces),
# plus any extra WebSocket origins you need:
serve_app(
    app,
    port=3000,
    address="0.0.0.0",
    allow_websocket_origin=["192.168.1.23:3000"],
    show=True,
)
```

### Data Structure

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

### Variable groups (optional)

Dense datasets often store many variables flat in one split (e.g.
`lai_deviation_year`, `swvl1_deviation_month`, `rho_bias_lai_year`,
`prediction_linear`). The viewer can group them when you describe how names are
structured — **only when you configure it**, otherwise nothing changes.

Set `facet_vocab` on `DataConfig` (each facet maps to the token values that
identify it in column names; names are split on `_`, values come from the data):

```python
from dataviewer_joseph import create_app, DataConfig

app = create_app(DataConfig(
    root="/path/to/my/data/dataviewer_auto",
    facet_vocab={
        "group": ["lai", "swvl1"],   # first token group
        "scale": ["year", "month"],  # timescale token
        "model": ["linear", "tree", "ridge"],  # model token
    },
))
app.show()
```

When vocabulary tokens appear in the variable names:

- **Map picker**: independent filter dropdowns (one per detected facet, plus an
  auto-derived "metric" facet for any leftover token) narrow the Variable list.
  They are interchangeable — pick any combination in any order, no hierarchy.
  If the filters fully determine one variable it is selected automatically.
- **Timeseries config** (the floating Config panel): inside each timeseries
  variable row the single flat dropdown is replaced by one small selector per
  facet (group, scale, model, metric — in the order of `facet_vocab`, plus an
  "Other" picker for columns outside the scheme, e.g. `backscatter40`). Every
  selector has "All"; the row's variable applies automatically as soon as the
  combination leaves exactly one column ("n variables match — pick more" /
  "No variable matches" notes guide you). Saved var configs populate the
  selectors from the stored variable names, so nothing is lost on import.

Without `facet_vocab` (or when no name matches it) the app shows the plain flat
lists exactly as before.

To try it with example data, generate faceted dummy data (same snippet,
nothing else to configure — the vocabulary comes with it):

```python
from dataviewer_joseph import create_app, generate_dummy_data

config = generate_dummy_data("/tmp/dataviewer_faceted", n_locations=200, n_tiles=2, faceted=True)
create_app(config).show()
```

or from bash:

```bash
uv run python scripts/generate_dummy_data.py --output /tmp/dataviewer_faceted --faceted
uv run python scripts/run_app.py --data /tmp/dataviewer_faceted --show
```

`faceted=True` (and the CLI `--faceted` flag) write the vocabulary into a
`dataviewer_meta.json` next to the data, so plain `DataConfig(root)` — including
the `run_app.py` command — enables the grouping automatically.
(`examples/03_faceted_variables.py` is the same in script form.)

### Reusing a timeseries var config

The exact timeseries plotting (variables, colors, overlays, thresholds) is driven
by a **var config**. You can export it, edit it, and reuse it:

- **In the app:** open the **Config** panel. Use **Download var config** to save the
  current timeseries setup as a `.json` file, and **Upload var config** to load a
  saved one (the plot updates immediately).
- **Automatic saving:** every **Download var config** click also writes a copy into
  the data's `config/` folder (`var_config_<timestamp>.json`), so your setup is
  backed up next to the data — no extra step needed. `prepare_dataviewer_data`
  always creates this `config/` folder for you.
- **Automatic loading:** when the viewer starts it **imports the most recent config**
  from that folder, so a saved setup is automatically applied the next time you
  open the data.
- **For a new analysis:** pass a saved `var_specs` list to `create_app` so a fresh
  session starts with the exact same timeseries configuration (this takes
  precedence over the auto-imported config):

```python
import json
from dataviewer_joseph import create_app, DataConfig

with open("var_config.json") as f:
    saved = json.load(f)["var_specs"]

app = create_app(DataConfig(root="/path/to/my/data/dataviewer_auto"), var_specs=saved)
app.show()
```

See the `examples/` directory for complete example scripts:
- `examples/01_basic_app.py` — create and display the app
- `examples/02_var_specs_editor.py` — configure var_specs interactively and plot them
- `examples/02_api_usage.py` — load data and create plots programmatically
- `examples/03_faceted_variables.py` — grouped variable demo (facets)

---

## Development (using bash)

For contributors working on the source repository.

```bash
# Clone and set up
git clone https://github.com/wagnerjoseph/dataviewer_joseph.git
cd dataviewer_joseph

# plotting_joseph is pulled from git (not PyPI), so uv sync resolves it automatically.
uv sync
uv pip install -e .
```

Run the app with the included script and sample data:

```bash
uv run python scripts/run_app.py --show                  # dummy data
uv run python scripts/run_app.py --data /path/to/data --show
```

Control where the server is served from:

```bash
uv run python scripts/run_app.py --data /path/to/data --port 3000 --show     # http://localhost:3000
uv run python scripts/run_app.py --data /path/to/data --port 3000 --address 0.0.0.0  # accessible to others
uv run python scripts/run_app.py --data /path/to/data --port 3000 --address jwagner   # http://jwagner:3000
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
