"""Serving utilities for dataviewer_joseph.

Provides :func:`serve_app`, which mirrors the ``--port`` / ``--address`` /
``--allow-websocket-origin`` options of ``scripts/run_app.py`` from Python code.
It builds the Bokeh WebSocket origin allowlist (auto-including the machine's
short hostname), prints where the app can be reached, and serves it.
"""

import socket
from collections.abc import Iterable

import panel as pn


def local_ip() -> str | None:
    """Return the machine's primary outbound LAN IP, or None if unavailable."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def is_loopback(address: str) -> bool:
    """Return True if the bind address only serves the local machine."""
    if address == "0.0.0.0":
        return False
    return address in ("localhost", "127.0.0.1", "::1")


def build_websocket_origins(
    port: int,
    address: str = "localhost",
    extra: Iterable[str] | None = None,
    host: str | None = None,
) -> list[str]:
    """Build the Bokeh WebSocket origin allowlist.

    Always includes ``localhost``, ``127.0.0.1``, the bind ``address``, and the
    machine's short hostname, plus any explicit ``extra`` origins (deduplicated,
    preserving order).

    Args:
        port: The port the app is served on
        address: The bind address
        extra: Optional extra origins to allow (e.g. a LAN IP)
        host: Override the hostname used (default: ``socket.gethostname()``)

    Returns:
        Deduplicated list of allowed origins
    """
    host = host or socket.gethostname()
    origins = [
        f"localhost:{port}",
        f"127.0.0.1:{port}",
        f"{address}:{port}",
    ]
    if host:
        origins.append(f"{host}:{port}")
    for origin in extra or []:
        origins.append(origin)
    return list(dict.fromkeys(origins))


def serve_app(
    app,
    port: int = 5000,
    address: str = "localhost",
    allow_websocket_origin: Iterable[str] | None = None,
    show: bool = False,
    host: str | None = None,
) -> None:
    """Serve the app, printing where it can be reached.

    Mirrors ``scripts/run_app.py`` but callable from Python code. The machine's
    short hostname is automatically an allowed WebSocket origin.

    Args:
        app: The Panel application object (from :func:`create_app`)
        port: Port to serve on
        address: Address to bind ('localhost', '0.0.0.0', a hostname, or IP)
        allow_websocket_origin: Extra WebSocket origins to allow (e.g. LAN IPs)
        show: Whether to open the app in a browser
        host: Override the hostname used for the URL / origin
    """
    websocket_origins = build_websocket_origins(
        port, address, allow_websocket_origin, host
    )
    host = host or socket.gethostname()

    print(f"\nApp served at http://{address}:{port}")
    print(f"  Local access:   http://localhost:{port}")
    if host:
        print(f"  Hostname:       http://{host}:{port}")
    if is_loopback(address):
        print(
            "  Network:        local only (use address='0.0.0.0' to share "
            "with others on the network)"
        )
    else:
        ip = local_ip()
        if ip:
            print(f"  Others on network: http://{ip}:{port}")
        else:
            print(
                "  Others on network: run 'hostname -I' to find your IP "
                "and share http://<ip>:{port}"
            )

    pn.serve(
        app,
        port=port,
        address=address,
        websocket_origin=websocket_origins,
        show=show,
    )
