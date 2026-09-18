#!/usr/bin/env python3
"""Run the dataviewer_joseph application."""

import argparse
from pathlib import Path

from dataviewer_joseph import DataConfig, create_app, generate_dummy_data, serve_app


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
        "--address",
        "--host",
        type=str,
        default="localhost",
        help="Address/host to bind the server to. Use '127.0.0.1' or "
        "'localhost' for local-only access, '0.0.0.0' to allow others on the "
        "network, or a hostname like 'jwagner' (default: localhost)",
    )
    parser.add_argument(
        "--allow-websocket-origin",
        action="append",
        default=None,
        metavar="HOST:PORT",
        help="Add an allowed WebSocket origin (e.g. '127.0.0.1:3000', "
        "'jwagner:3000'). Repeat for each origin. Bokeh only accepts live "
        "connections from allowed origins, so this is needed when the page is "
        "reached through an address other than localhost.",
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
    print("\nStarting dataviewer_joseph app...")
    print(f"Data directory: {data_path}")
    app = create_app(config)

    # Serve the app (blocks until the server is stopped)
    serve_app(
        app,
        port=args.port,
        address=args.address,
        allow_websocket_origin=args.allow_websocket_origin,
        show=args.show,
    )


if __name__ == "__main__":
    main()
