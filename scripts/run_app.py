#!/usr/bin/env python3
"""Run the dataviewer_joseph application."""

import argparse
from pathlib import Path

from dataviewer_joseph import DataConfig, create_app, generate_dummy_data


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run the dataviewer_joseph application"
    )
    parser.add_argument(
        "--data",
        "-d",
        type=Path,
        default=None,
        help="Path to data directory (default: generate dummy data)",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=5000,
        help="Port to serve the app on",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Open the app in a browser",
    )

    args = parser.parse_args()

    if args.data is None:
        # Generate dummy data
        print("No data directory specified, generating dummy data...")
        data_path = Path("/tmp/dataviewer_demo_data")
        generate_dummy_data(data_path, n_locations=100, n_tiles=4)
        print(f"Dummy data generated at {data_path}")
    else:
        data_path = args.data

    # Create configuration
    config = DataConfig(root=data_path)

    # Create the app
    print(f"\nStarting dataviewer_joseph app...")
    print(f"Data directory: {data_path}")
    app = create_app(config)

    # Serve the app
    if args.show:
        app.show()
    else:
        app.servable()
        print(f"App served at http://localhost:{args.port}")


if __name__ == "__main__":
    main()
