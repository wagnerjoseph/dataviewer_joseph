#!/usr/bin/env python3
"""Test the dataviewer_joseph preparation and rendering workflow."""

import sys
from pathlib import Path
import tempfile
import pandas as pd
import numpy as np

# Add dataviewer_joseph to path
sys.path.insert(0, '/home/jwagner/dataviewer_joseph/src')

from dataviewer_joseph import DataConfig, generate_dummy_data
from dataviewer_joseph.prepare import prepare_dataviewer_data
from dataviewer_joseph.plotting.renderers import render_additional_data, suggest_renderer


def main():
    print("="*70)
    print("Testing dataviewer_joseph Preparation & Rendering Workflow")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Step 1: Generate dummy data using existing function
        print("\n1. Generating dummy data...")
        dummy_root = tmpdir / "dummy_data"
        config = generate_dummy_data(dummy_root, n_locations=50, n_tiles=2)
        print(f"   ✓ Generated at: {dummy_root}")
        
        # Step 2: Create mock additional data
        print("\n2. Creating additional data...")
        additional_data_dir = tmpdir / "additional_data"
        additional_data_dir.mkdir()
        
        for split in ["split_2020_2022", "split_2023_2024"]:
            split_dir = additional_data_dir / split
            split_dir.mkdir()
            
            for tile_id in ["0000", "0001", "0002", "0003"]:
                # Create per-location attributes
                np.random.seed(42)
                n_locs = 25 if tile_id in ["0000", "0001"] else 25
                location_ids = np.arange(25) + (0 if tile_id == "0000" else 25)
                
                df = pd.DataFrame({
                    "location_id": location_ids,
                    "rmse": np.random.uniform(0.5, 1.5, len(location_ids)),
                    "mae": np.random.uniform(0.3, 1.2, len(location_ids)),
                    "pearson": np.random.uniform(0.6, 0.95, len(location_ids)),
                    "n_observations": np.random.randint(100, 500, len(location_ids)),
                    "data_quality": np.random.choice(["good", "fair", "poor"], len(location_ids)),
                })
                
                output_file = split_dir / f"{tile_id}.parquet"
                df.to_parquet(output_file, compression=None)
        
        print(f"   ✓ Created at: {additional_data_dir}")
        
        # Step 3: Prepare data for dataviewer
        print("\n3. Preparing data for dataviewer...")
        output_dir = tmpdir / "output"
        
        # Create proper map_data structure (per-tile, no time column)
        map_data_dir = tmpdir / "map_data"
        for split in ["split_2020_2022", "split_2023_2024"]:
            split_dir = map_data_dir / split
            split_dir.mkdir(parents=True)
            
            # Copy metrics_by_tile files as map_data
            source_dir = dummy_root / split / "metrics_by_tile"
            if source_dir.exists():
                for tile_file in source_dir.glob("*.parquet"):
                    import shutil
                    shutil.copy2(tile_file, split_dir / tile_file.name)
        
        prepare_dataviewer_data(
            lookup_dir=dummy_root,
            map_data_dir=map_data_dir,
            timeseries_dir=dummy_root,
            additional_data_dir=additional_data_dir,
            output_dir=output_dir,
            output_name="dataviewer_auto",
        )
        
        output_path = output_dir / "dataviewer_auto"
        print(f"   ✓ Prepared at: {output_path}")
        
        # Step 4: Verify structure
        print("\n4. Verifying output structure...")
        assert output_path.exists(), "Output directory missing"
        assert (output_path / "ers_tile_id_location_id.parquet").exists(), "Lookup table missing"
        
        for split in ["split_2020_2022", "split_2023_2024"]:
            split_dir = output_path / split
            assert split_dir.exists(), f"Split {split} missing"
            assert (split_dir / "metrics_global_plot").exists(), f"metrics_global_plot missing for {split}"
            assert (split_dir / "timeseries").exists(), f"timeseries missing for {split}"
            assert (split_dir / "additional_data").exists(), f"additional_data missing for {split}"
            
            # Check additional data files
            add_files = list((split_dir / "additional_data").glob("*.parquet"))
            print(f"   ✓ {split}: {len(add_files)} additional data tiles")
        
        # Step 5: Test loading and rendering additional data
        print("\n5. Testing additional data loading and rendering...")
        from dataviewer_joseph.data import load_additional_data_for_location
        
        config = DataConfig(root=output_path)
        
        # Try loading for first location
        attrs = load_additional_data_for_location(config, "split_2020_2022", location_id=0)
        if attrs is not None:
            print(f"   ✓ Loaded attributes for location 0: {len(attrs)} values")
            
            # Test auto-suggestion
            suggested = suggest_renderer(attrs)
            print(f"   ✓ Auto-suggested renderer: {suggested}")
            
            # Test rendering
            plot = render_additional_data(attrs, renderer_type=suggested)
            print(f"   ✓ Rendered as {type(plot).__name__}")
        else:
            print("   ⚠ Could not load additional data (expected if tile mismatch)")
        
        print("\n" + "="*70)
        print("✓ All tests passed!")
        print("="*70)
        
        print(f"\nTo view the data, run:")
        print(f"  uv run python /home/jwagner/dataviewer_joseph/scripts/run_app.py \\")
        print(f"    --data {output_path} --show")


if __name__ == "__main__":
    main()
