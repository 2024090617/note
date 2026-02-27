"""MCP client — subprocess-based JSON-RPC over stdio.

Implements the MCP (Model Context Protocol) client side:
- Starts MCP servers as subprocesses
- Uses JSON-RPC 2.0 with newline-delimited framing
- Supports initialize handshake, tools/list, tools/call
- Manages multiple server connections via MCPManager
"""

import json
import logging
import os
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# MCP protocol version
PROTOCOL_VERSION = "2024-11-05"
CLIENT_INFO = {"name": "llm-service-agent", "version": "0.1.0"}


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""

    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    timeout: int = 30


@dataclass
class MCPToolInfo:
    """Metadata for a tool exposed by an MCP server."""

    server_name: str
    name: str
    description: str
    input_schema: Dict[str, Any]


class MCPConnection:
    """
    Persistent connection to an MCP server subprocess.

    Manages the lifecycle of a single MCP server process and provides
    synchronous methods for listing and calling tools.

    Protocol flow:
        1. Start server subprocess
        2. Send initialize request → receive capabilities
        3. Send notifications/initialized
        4. Ready for tools/list and tools/call
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._tools_cache: Optional[List[MCPToolInfo]] = None
        self._lock = threading.Lock()
        self._initialized = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _ensure_started(self):
        """Start the server process and complete the MCP handshake."""
        if self._initialized and self._process and self._process.poll() is None:
            return

        self._start_process()
        self._handshake()

    def _start_process(self):
        """Launch the MCP server as a subprocess."""
        cmd = [self.config.command] + self.config.args
        env = os.environ.copy()
        env.update(self.config.env)

        logger.debug("Starting MCP server %s: %s", self.config.name, " ".join(cmd))

        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        self._request_id = 0
        self._initialized = False

    def _handshake(self):
        """Perform the MCP initialize / initialized handshake."""
        # 1. Send initialize request
        req_id = self._send_request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        )
        resp = self._read_response(expected_id=req_id)

        server_caps = resp.get("result", {})
        logger.debug(
            "MCP server %s initialized (protocol=%s, caps=%s)",
            self.config.name,
            server_caps.get("protocolVersion"),
            list(server_caps.get("capabilities", {}).keys()),
        )

        # 2. Send initialized notification
        self._send_notification("notifications/initialized")
        self._initialized = True

    def close(self):
        """Shut down the server subprocess."""
        if self._process:
            try:
                self._process.stdin.close()
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
            finally:
                self._process = None
                self._initialized = False

    # ------------------------------------------------------------------
    # JSON-RPC transport
    # ------------------------------------------------------------------

    def _send_request(self, method: str, params: Dict[str, Any]) -> int:
        """Send a JSON-RPC request.  Returns the request id."""
        self._request_id += 1
        msg = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        raw = json.dumps(msg, separators=(",", ":")).encode() + b"\n"
        self._process.stdin.write(raw)
        self._process.stdin.flush()
        return self._request_id

    def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None):
        """Send a JSON-RPC notification (no id, no response expected)."""
        msg: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params:
            msg["params"] = params
        raw = json.dumps(msg, separators=(",", ":")).encode() + b"\n"
        self._process.stdin.write(raw)
        self._process.stdin.flush()

    def _read_response(self, expected_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Read a JSON-RPC response, skipping server-initiated notifications.

        If *expected_id* is given, keeps reading until a response with that
        id arrives (or the process ends).
        """
        while True:
            line = self._process.stdout.readline()
            if not line:
                stderr_out = ""
                if self._process.stderr:
                    stderr_out = self._process.stderr.read().decode(errors="replace")
                raise RuntimeError(
                    f"MCP server '{self.config.name}' closed unexpectedly. stderr: {stderr_out}"
                )
            try:
                msg = json.loads(line.decode().strip())
            except json.JSONDecodeError:
                # Skip non-JSON lines (e.g. log output)
                continue

            # Skip notifications (no "id" field) — they are server-initiated
            if "id" not in msg:
                logger.debug("MCP notification from %s: %s", self.config.name, msg.get("method"))
                continue

            if expected_id is not None and msg["id"] != expected_id:
                logger.debug("Skipping unexpected response id %s (want %s)", msg["id"], expected_id)
                continue

            # Check for JSON-RPC error
            if "error" in msg:
                err = msg["error"]
                raise RuntimeError(
                    f"MCP server '{self.config.name}' error: "
                    f"[{err.get('code')}] {err.get('message')}"
                )

            return msg

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_tools(self) -> List[MCPToolInfo]:
        """List all tools exposed by this MCP server (cached)."""
        if self._tools_cache is not None:
            return self._tools_cache

        with self._lock:
            if self._tools_cache is not None:
                return self._tools_cache

            self._ensure_started()
            req_id = self._send_request("tools/list", {})
            resp = self._read_response(expected_id=req_id)

            tools_raw = resp.get("result", {}).get("tools", [])
            self._tools_cache = [
                MCPToolInfo(
                    server_name=self.config.name,
                    name=t["name"],
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                )
                for t in tools_raw
            ]
            logger.info(
                "MCP server '%s' exposes %d tools", self.config.name, len(self._tools_cache)
            )
            return self._tools_cache

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Call a tool on this MCP server.

        Returns the text content of the result.
        """
        with self._lock:
            self._ensure_started()
            req_id = self._send_request(
                "tools/call",
                {"name": tool_name, "arguments": arguments},
            )
            resp = self._read_response(expected_id=req_id)

            result = resp.get("result", {})
            content_items = result.get("content", [])

            texts: List[str] = []
            for item in content_items:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        texts.append(item.get("text", ""))
                    else:
                        texts.append(json.dumps(item, indent=2))
                else:
                    texts.append(str(item))

            return "\n".join(texts) if texts else json.dumps(result, indent=2)


class MCPManager:
    """
    Manages multiple MCP server connections.

    Typical usage::

        manager = MCPManager.from_config_file("mcp.json")
        tools = manager.list_tools()             # all servers
        result = manager.call_tool("monitoring", "search_splunk_logs", {...})
        manager.close_all()
    """

    def __init__(self):
        self._servers: Dict[str, MCPConnection] = {}
        self._all_tools_cache: Optional[List[MCPToolInfo]] = None

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_config_file(cls, config_path: str) -> "MCPManager":
        """
        Load MCP servers from a JSON config file.

        Expected format (compatible with Claude Desktop / Cursor)::

            {
                "mcpServers": {
                    "server-name": {
                        "command": "executable",
                        "args": ["--flag"],
                        "env": {"KEY": "value"},
                        "timeout": 30
                    }
                }
            }
        """
        path = Path(config_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"MCP config not found: {config_path}")

        with open(path) as f:
            data = json.load(f)

        manager = cls()
        servers = data.get("mcpServers", {})
        for name, sdata in servers.items():
            cfg = MCPServerConfig(
                name=name,
                command=sdata.get("command", ""),
                args=sdata.get("args", []),
                env=sdata.get("env", {}),
                timeout=sdata.get("timeout", 30),
            )
            manager.add_server(cfg)

        logger.info("Loaded %d MCP server(s) from %s", len(manager._servers), path)
        return manager

    @classmethod
    def from_dict(cls, servers_dict: Dict[str, Dict[str, Any]]) -> "MCPManager":
        """
        Create from an inline dictionary.

        Keys are server names, values are dicts with command/args/env/timeout.
        """
        manager = cls()
        for name, sdata in servers_dict.items():
            cfg = MCPServerConfig(
                name=name,
                command=sdata.get("command", ""),
                args=sdata.get("args", []),
                env=sdata.get("env", {}),
                timeout=sdata.get("timeout", 30),
            )
            manager.add_server(cfg)
        return manager

    # ------------------------------------------------------------------
    # Server management
    # ------------------------------------------------------------------

    def add_server(self, config: MCPServerConfig):
        """Register an MCP server (connection is lazy — starts on first use)."""
        self._servers[config.name] = MCPConnection(config)
        self._all_tools_cache = None  # invalidate

    def list_servers(self) -> List[str]:
        """Return configured server names."""
        return list(self._servers.keys())

    def close_all(self):
        """Shut down all server subprocesses."""
        for conn in self._servers.values():
            try:
                conn.close()
            except Exception as e:
                logger.warning("Error closing MCP server: %s", e)

    # ------------------------------------------------------------------
    # Tool discovery & invocation
    # ------------------------------------------------------------------

    def list_tools(self, server: Optional[str] = None) -> List[MCPToolInfo]:
        """
        List tools from one or all servers.

        Args:
            server: Specific server name, or None for all.
        """
        if server:
            conn = self._servers.get(server)
            if not conn:
                return []
            return conn.list_tools()

        # All servers — use cache
        if self._all_tools_cache is not None:
            return self._all_tools_cache

        all_tools: List[MCPToolInfo] = []
        for name, conn in self._servers.items():
            try:
                all_tools.extend(conn.list_tools())
            except Exception as e:
                logger.warning("Failed to list tools from MCP server '%s': %s", name, e)

        self._all_tools_cache = all_tools
        return all_tools

    def call_tool(self, server: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Call a tool on a specific MCP server.

        Args:
            server: Server name (as defined in config).
            tool_name: Name of the tool to invoke.
            arguments: Tool arguments dict.

        Returns:
            Text result from the tool.

        Raises:
            ValueError: If server not found.
            RuntimeError: If the MCP call fails.
        """
        conn = self._servers.get(server)
        if not conn:
            available = ", ".join(self.list_servers()) or "(none)"
            raise ValueError(
                f"MCP server '{server}' not found. Available servers: {available}"
            )
        return conn.call_tool(tool_name, arguments)

    def get_tools_summary(self) -> str:
        """
        Get a human-readable summary of all MCP tools for prompt injection.

        Returns XML block suitable for the system prompt.
        """
        tools = self.list_tools()
        if not tools:
            return ""

        lines = ["<available_mcp_tools>"]
        # Group by server
        by_server: Dict[str, List[MCPToolInfo]] = {}
        for t in tools:
            by_server.setdefault(t.server_name, []).append(t)

        for srv_name, srv_tools in by_server.items():
            lines.append(f'  <server name="{srv_name}">')
            for t in srv_tools:
                lines.append(f"    <tool>")
                lines.append(f"      <name>{t.name}</name>")
                lines.append(f"      <description>{t.description}</description>")
                # Compact schema — only include required and properties keys
                schema = t.input_schema
                if schema:
                    props = schema.get("properties", {})
                    required = schema.get("required", [])
                    params = []
                    for pname, pinfo in props.items():
                        req = " (required)" if pname in required else ""
                        ptype = pinfo.get("type", "any")
                        pdesc = pinfo.get("description", "")
                        params.append(f"        <param name=\"{pname}\" type=\"{ptype}\"{req}>{pdesc}</param>")
                    if params:
                        lines.append("      <params>")
                        lines.extend(params)
                        lines.append("      </params>")
                lines.append(f"    </tool>")
            lines.append(f"  </server>")

        lines.append("</available_mcp_tools>")
        return "\n".join(lines)
