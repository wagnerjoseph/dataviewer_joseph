#!/usr/bin/env python3
"""Run the dataviewer_joseph application."""

import argparse
import socket
from pathlib import Path

import panel as pn

from dataviewer_joseph import DataConfig, create_app, generate_dummy_data


def _local_ip() -> str | None:
    """Return the machine's primary outbound LAN IP, or None if unavailable."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def _is_loopback(address: str) -> bool:
    """Return True if the bind address only serves the local machine."""
    if address == "0.0.0.0":
        return False
    return address in ("localhost", "127.0.0.1", "::1")


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

    # Build the WebSocket origin allowlist. Bokeh refuses live connections from
    # origins it doesn't know about, so always allow the bound address plus
    # localhost/127.0.0.1, the machine's short hostname, and any origins the
    # user supplied explicitly.
    websocket_origins = [
        f"localhost:{args.port}",
        f"127.0.0.1:{args.port}",
        f"{args.address}:{args.port}",
    ]
    host = socket.gethostname()
    if host:
        websocket_origins.append(f"{host}:{args.port}")
    for origin in args.allow_websocket_origin or []:
        websocket_origins.append(origin)

    # Remove duplicates while preserving order.
    websocket_origins = list(dict.fromkeys(websocket_origins))

    host = socket.gethostname()

    # Where the app can be reached.
    print(f"\nApp served at http://{args.address}:{args.port}")
    print(f"  Local access:   http://localhost:{args.port}")
    if host:
        print(f"  Hostname:       http://{host}:{args.port}")
    if _is_loopback(args.address):
        print(
            "  Network:        local only (use --address 0.0.0.0 to share "
            "with others on the network)"
        )
    else:
        local_ip = _local_ip()
        if local_ip:
            print(f"  Others on network: http://{local_ip}:{args.port}")
        else:
            print(
                "  Others on network: run 'hostname -I' to find your IP and "
                "share http://<ip>:{port}"
            )

    # Serve the app (blocks until the server is stopped)
    pn.serve(
        app,
        port=args.port,
        address=args.address,
        websocket_origin=websocket_origins,
        show=args.show,
    )


if __name__ == "__main__":
    main()
