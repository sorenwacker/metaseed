"""MCP server process manager.

Manages starting and stopping the MCP server as a background process.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Self

logger = logging.getLogger(__name__)


@dataclass
class MCPServerStatus:
    """Status of the MCP server."""

    running: bool
    transport: str | None = None
    host: str | None = None
    port: int | None = None
    pid: int | None = None
    error: str | None = None


class MCPServerManager:
    """Manages the MCP server process.

    Provides methods to start, stop, and check status of the MCP server
    running as a background process.
    """

    _instance: MCPServerManager | None = None
    _lock = threading.Lock()

    def __new__(cls) -> MCPServerManager:
        """Singleton pattern to ensure only one manager exists."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self: Self) -> None:
        """Initialize the manager."""
        if self._initialized:
            return

        self._process: subprocess.Popen | None = None
        self._transport: str | None = None
        self._host: str | None = None
        self._port: int | None = None
        self._initialized = True

    def start(
        self: Self,
        transport: str = "streamable-http",
        host: str = "127.0.0.1",
        port: int = 8001,
    ) -> MCPServerStatus:
        """Start the MCP server.

        Args:
            transport: Transport type ("stdio" or "streamable-http").
            host: Host for HTTP transport.
            port: Port for HTTP transport.

        Returns:
            Status after attempting to start.
        """
        if self.is_running():
            return self.status()

        # Kill any orphaned process on the port
        if self._check_port_in_use(port):
            logger.warning("Port %d is already in use, killing orphaned process", port)
            self.kill_orphaned(port)
            time.sleep(0.5)

        try:
            # Build command using the metaseed entry point
            # Find the metaseed script in the same directory as python
            import shutil

            metaseed_cmd = shutil.which("metaseed")
            if metaseed_cmd is None:
                # Fall back to running via python -c
                cmd = [
                    sys.executable,
                    "-c",
                    "from metaseed.cli import app; app()",
                    "mcp",
                    "--transport",
                    "http" if transport == "streamable-http" else transport,
                    "--host",
                    host,
                    "--port",
                    str(port),
                ]
            else:
                cmd = [
                    metaseed_cmd,
                    "mcp",
                    "--transport",
                    "http" if transport == "streamable-http" else transport,
                    "--host",
                    host,
                    "--port",
                    str(port),
                ]

            logger.info("Starting MCP server: %s", " ".join(cmd))

            # Start process
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self._transport = transport
            self._host = host
            self._port = port

            # Give it a moment to start
            time.sleep(0.5)

            # Check if it's still running
            if self._process.poll() is not None:
                # Process exited, get error
                _, stderr = self._process.communicate()
                self._process = None
                return MCPServerStatus(
                    running=False,
                    error=f"Server failed to start: {stderr}",
                )

            logger.info("MCP server started on %s:%d (pid=%d)", host, port, self._process.pid)

            return self.status()

        except Exception as e:
            logger.exception("Failed to start MCP server")
            return MCPServerStatus(running=False, error=str(e))

    def stop(self: Self) -> MCPServerStatus:
        """Stop the MCP server.

        Returns:
            Status after attempting to stop.
        """
        if self._process is None:
            return MCPServerStatus(running=False)

        try:
            logger.info("Stopping MCP server (pid=%d)", self._process.pid)
            self._process.terminate()

            # Wait for graceful shutdown
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("MCP server did not stop gracefully, killing")
                self._process.kill()
                self._process.wait()

            self._process = None
            self._transport = None
            self._host = None
            self._port = None

            return MCPServerStatus(running=False)

        except Exception as e:
            logger.exception("Failed to stop MCP server")
            return MCPServerStatus(running=False, error=str(e))

    def is_running(self: Self, port: int = 8001) -> bool:
        """Check if the server is running.

        Checks the internal process reference, port availability, and whether
        the MCP server is actually responding.
        """
        host = self._host or "127.0.0.1"

        # First check our process reference
        if self._process is not None:
            if self._process.poll() is None:
                # Process is running, verify it's responding
                if self._check_mcp_responding(host, port):
                    return True
                # Process running but not responding - might be starting up
                return True
            # Process has exited
            self._process = None

        # Check if port is in use AND MCP is responding
        if self._check_port_in_use(port):
            if self._check_mcp_responding(host, port):
                return True

        return False

    def _check_port_in_use(self: Self, port: int) -> int | None:
        """Check if port is in use and return PID if so.

        Args:
            port: Port to check.

        Returns:
            PID of process using the port, or None if port is free.
        """
        import socket

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                result = s.connect_ex(("127.0.0.1", port))
                if result == 0:
                    # Port is in use - try to get PID via lsof
                    try:
                        result = subprocess.run(
                            ["lsof", "-ti", f":{port}"],
                            capture_output=True,
                            text=True,
                            timeout=2,
                            check=False,
                        )
                        if result.returncode == 0 and result.stdout.strip():
                            return int(result.stdout.strip().split()[0])
                    except (subprocess.TimeoutExpired, ValueError):
                        pass
                    return -1  # Port in use but can't get PID
        except OSError:
            pass
        return None

    def _check_mcp_responding(self: Self, host: str, port: int) -> bool:
        """Check if MCP server is actually responding.

        Makes a quick HTTP request to verify the server is working.

        Args:
            host: Host to check.
            port: Port to check.

        Returns:
            True if server responds, False otherwise.
        """
        import urllib.error
        import urllib.request

        try:
            url = f"http://{host}:{port}/mcp"
            req = urllib.request.Request(url, method="GET")  # noqa: S310
            with urllib.request.urlopen(req, timeout=2):  # noqa: S310
                return True
        except urllib.error.HTTPError as e:
            # MCP server returns various HTTP errors for invalid requests
            # but if we get ANY HTTP response, the server is running
            return e.code in (400, 405, 406, 415)
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def kill_orphaned(self: Self, port: int = 8001) -> bool:
        """Kill any orphaned MCP server on the given port.

        Args:
            port: Port to check for orphaned servers.

        Returns:
            True if an orphaned process was killed.
        """
        pid = self._check_port_in_use(port)
        if pid and pid > 0:
            try:
                import os
                import signal

                logger.info("Killing orphaned MCP server on port %d (pid=%d)", port, pid)
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.5)
                # Check if it's still there
                if self._check_port_in_use(port):
                    os.kill(pid, signal.SIGKILL)
                return True
            except (OSError, ProcessLookupError):
                pass
        return False

    def status(self: Self, port: int = 8001) -> MCPServerStatus:
        """Get current server status.

        Args:
            port: Port to check for running server.

        Returns:
            Current status of the MCP server.
        """
        if not self.is_running(port):
            return MCPServerStatus(running=False)

        # Use stored values if we have them, otherwise use defaults
        return MCPServerStatus(
            running=True,
            transport=self._transport or "streamable-http",
            host=self._host or "127.0.0.1",
            port=self._port or port,
            pid=self._process.pid if self._process else None,
        )

    def get_connection_url(self: Self, port: int = 8001) -> str | None:
        """Get the connection URL for the running server.

        Args:
            port: Default port if we lost the reference.

        Returns:
            URL string or None if not running.
        """
        if not self.is_running(port):
            return None

        # Use stored values or defaults
        host = self._host or "127.0.0.1"
        actual_port = self._port or port
        transport = self._transport or "streamable-http"

        if transport == "streamable-http":
            return f"http://{host}:{actual_port}"

        return None


# Global instance
_manager: MCPServerManager | None = None


def get_mcp_manager() -> MCPServerManager:
    """Get the global MCP server manager instance."""
    global _manager
    if _manager is None:
        _manager = MCPServerManager()
    return _manager
