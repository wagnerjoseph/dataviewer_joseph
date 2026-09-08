#!/usr/bin/env python3
"""
Quick Start: Test dataviewer_joseph with your data

This script demonstrates how to use the new preparation tool and renderer.

Run with: uv run python scripts/quick_start.py
"""

from pathlib import Path


def main():
    print("="*70)
    print("dataviewer_joseph - Quick Start Guide")
    print("="*70)
    
    # =============================================================================
    # STEP 1: Prepare Your Data
    # =============================================================================
    print("\nSTEP 1: Prepare your data")
    print("-" * 70)
    print("""
Organize your data into these folders:

    /path/to/your_data/
    ├── lookup_tables/
    │   └── ers_tile_id_location_id.parquet
    ├── map_data/
    │   ├── split_1991_2015__2016_2023/
    │   │   ├── 0001.parquet  (no time column)
    │   │   └── ...
    │   └── split_1991_2007__2008_2015/
    ├── timeseries/
    │   ├── split_1991_2015__2016_2023/
    │   │   ├── 0001.parquet  (has time column)
    │   │   └── ...
    │   └── split_1991_2007__2008_2015/
    └── additional_data/  (optional - per-location attributes)
        ├── split_1991_2015__2016_2023/
        │   ├── 0001.parquet
        │   └── ...
        └── split_1991_2007__2008_2015/

Then run the preparation script:

    uv run python scripts/prepare_data.py \\
        --lookup /path/to/your_data/lookup_tables \\
        --map-data /path/to/your_data/map_data \\
        --timeseries /path/to/your_data/timeseries \\
        --additional-data /path/to/your_data/additional_data \\
        --output /path/to/output \\
        --name dataviewer_auto
    """)
    
    # =============================================================================
    # STEP 2: Launch the Dataviewer
    # =============================================================================
    print("\nSTEP 2: Launch the dataviewer")
    print("-" * 70)
    print("""
After preparation, launch the app:

    uv run python scripts/run_app.py \\
        --data /path/to/output/dataviewer_auto \\
        --show
    
Or in Python:

    from dataviewer_joseph import DataConfig, create_app
    
    config = DataConfig(root=Path("/path/to/output/dataviewer_auto"))
    app = create_app(config)
    app.show()
    """)
    
    # =============================================================================
    # STEP 3: Use the App
    # =============================================================================
    print("\nSTEP 3: Use the app")
    print("-" * 70)
    print("""
1. Select a split from the dropdown
2. Select a variable to display on the map
3. Click a location on the map (or enter Location ID)
4. View:
   - Timeseries (top)
   - Metrics table (bottom left)
   - Feature importance (bottom middle)
   - Additional data with selectable renderer (bottom right)

5. Use the "Plot Style" dropdown to change how additional data is rendered:
   - bar: Best for ranked numeric values
   - scatter: Best for comparing attributes
   - table: Best for mixed types
   - histogram: Best for distributions
   - box: Best for statistical summaries
    """)
    
    # =============================================================================
    # EXAMPLE: Your Data
    # =============================================================================
    print("\nEXAMPLE: Using your backscatter analysis data")
    print("-" * 70)
    
    # Check if your data exists
    your_data_path = Path("/home/jwagner/Desktop/data/long-term-backscatter-analysis-data/dataviewer")
    
    if your_data_path.exists():
        print(f"✓ Found existing data at: {your_data_path}")
        print(f"\nYou can launch it directly:")
        print(f"  uv run python scripts/run_app.py --data {your_data_path} --show")
    else:
        print(f"⚠ Data not found at: {your_data_path}")
        print("You'll need to prepare your data first using the preparation script.")
    
    print("\n" + "="*70)
    print("For more details, see:")
    print("  - README.md - Full documentation")
    print("  - IMPLEMENTATION.md - Technical details")
    print("  - scripts/test_prepare_and_render.py - Working example")
    print("="*70)


if __name__ == "__main__":
    main()
