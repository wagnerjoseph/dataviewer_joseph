"""Tests for serving utilities (serve_app and helpers)."""

from dataviewer_joseph.serve import (
    build_websocket_origins,
    is_loopback,
    local_ip,
)


class TestBuildWebsocketOrigins:
    def test_includes_defaults_and_hostname(self):
        origins = build_websocket_origins(port=3000, address="0.0.0.0", host="jwagner")
        assert "localhost:3000" in origins
        assert "127.0.0.1:3000" in origins
        assert "0.0.0.0:3000" in origins
        assert "jwagner:3000" in origins

    def test_includes_extra_origins(self):
        origins = build_websocket_origins(
            port=3000,
            address="0.0.0.0",
            host="jwagner",
            extra=["192.168.1.23:3000", "otherhost:3000"],
        )
        assert "192.168.1.23:3000" in origins
        assert "otherhost:3000" in origins

    def test_deduplicates(self):
        origins = build_websocket_origins(
            port=3000,
            address="0.0.0.0",
            host="jwagner",
            extra=["localhost:3000", "jwagner:3000"],
        )
        assert origins.count("localhost:3000") == 1
        assert origins.count("jwagner:3000") == 1
        assert origins == list(dict.fromkeys(origins))


class TestIsLoopback:
    def test_loopback_addresses(self):
        assert is_loopback("localhost") is True
        assert is_loopback("127.0.0.1") is True
        assert is_loopback("::1") is True

    def test_non_loopback(self):
        assert is_loopback("0.0.0.0") is False
        assert is_loopback("jwagner") is False
        assert is_loopback("192.168.1.23") is False


class TestLocalIp:
    def test_returns_string_or_none(self):
        # local_ip should not raise; it returns an IP string or None.
        ip = local_ip()
        assert ip is None or isinstance(ip, str)
