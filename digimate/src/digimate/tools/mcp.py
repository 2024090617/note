"""MCP (Model Context Protocol) client and tool proxy."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from digimate.core.types import ToolResult

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
CLIENT_INFO = {"name": "digimate", "version": "0.1.0"}


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    timeout: int = 30


@dataclass
class MCPToolInfo:
    server_name: str
    name: str
    description: str
    input_schema: Dict[str, Any]


class MCPConnection:
    """Persistent connection to a single MCP server subprocess."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._tools_cache: Optional[List[MCPToolInfo]] = None
        self._lock = threading.Lock()
        self._initialized = False

    def _ensure_started(self):
        if self._initialized and self._process and self._process.poll() is None:
            return
        self._start_process()
        self._handshake()

    def _start_process(self):
        cmd = [self.config.command] + self.config.args
        env = os.environ.copy()
        env.update(self.config.env)
        self._process = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
        )
        self._request_id = 0
        self._initialized = False

    def _handshake(self):
        rid = self._send_request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": CLIENT_INFO,
        })
        self._read_response(expected_id=rid)
        self._send_notification("notifications/initialized")
        self._initialized = True

    def close(self):
        if self._process:
            try:
                self._process.stdin.close()
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
            finally:
                self._process = None
                self._initialized = False

    def _send_request(self, method: str, params: Dict[str, Any]) -> int:
        self._request_id += 1
        msg = {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params}
        self._process.stdin.write(json.dumps(msg, separators=(",", ":")).encode() + b"\n")
        self._process.stdin.flush()
        return self._request_id

    def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None):
        msg: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params:
            msg["params"] = params
        self._process.stdin.write(json.dumps(msg, separators=(",", ":")).encode() + b"\n")
        self._process.stdin.flush()

    def _read_response(self, expected_id: Optional[int] = None) -> Dict[str, Any]:
        while True:
            line = self._process.stdout.readline()
            if not line:
                stderr = self._process.stderr.read().decode(errors="replace") if self._process.stderr else ""
                raise RuntimeError(f"MCP server '{self.config.name}' closed. stderr: {stderr}")
            try:
                msg = json.loads(line.decode().strip())
            except json.JSONDecodeError:
                continue
            if "id" not in msg:
                continue
            if expected_id is not None and msg["id"] != expected_id:
                continue
            if "error" in msg:
                err = msg["error"]
                raise RuntimeError(f"MCP error [{err.get('code')}]: {err.get('message')}")
            return msg

    def list_tools(self) -> List[MCPToolInfo]:
        if self._tools_cache is not None:
            return self._tools_cache
        with self._lock:
            if self._tools_cache is not None:
                return self._tools_cache
            self._ensure_started()
            rid = self._send_request("tools/list", {})
            resp = self._read_response(expected_id=rid)
            raw = resp.get("result", {}).get("tools", [])
            self._tools_cache = [
                MCPToolInfo(
                    server_name=self.config.name, name=t["name"],
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                ) for t in raw
            ]
            return self._tools_cache

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        with self._lock:
            self._ensure_started()
            rid = self._send_request("tools/call", {"name": tool_name, "arguments": arguments})
            resp = self._read_response(expected_id=rid)
            items = resp.get("result", {}).get("content", [])
            texts = []
            for item in items:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(item.get("text", ""))
                elif isinstance(item, dict):
                    texts.append(json.dumps(item, indent=2))
                else:
                    texts.append(str(item))
            return "\n".join(texts) if texts else json.dumps(resp.get("result", {}), indent=2)


class MCPManager:
    """Manages multiple MCP server connections."""

    def __init__(self):
        self._servers: Dict[str, MCPConnection] = {}
        self._all_tools_cache: Optional[List[MCPToolInfo]] = None

    @classmethod
    def from_config_file(cls, config_path: str) -> MCPManager:
        path = Path(config_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"MCP config not found: {config_path}")
        with open(path) as f:
            data = json.load(f)
        mgr = cls()
        for name, sdata in data.get("mcpServers", {}).items():
            mgr.add_server(MCPServerConfig(
                name=name, command=sdata.get("command", ""),
                args=sdata.get("args", []), env=sdata.get("env", {}),
                timeout=sdata.get("timeout", 30),
            ))
        return mgr

    def add_server(self, config: MCPServerConfig):
        self._servers[config.name] = MCPConnection(config)
        self._all_tools_cache = None

    def list_servers(self) -> List[str]:
        return list(self._servers.keys())

    def close_all(self):
        for conn in self._servers.values():
            try:
                conn.close()
            except Exception:
                pass

    def list_tools(self, server: Optional[str] = None) -> List[MCPToolInfo]:
        if server:
            conn = self._servers.get(server)
            return conn.list_tools() if conn else []
        if self._all_tools_cache is not None:
            return self._all_tools_cache
        all_t: List[MCPToolInfo] = []
        for conn in self._servers.values():
            try:
                all_t.extend(conn.list_tools())
            except Exception as e:
                logger.warning("MCP list_tools failed: %s", e)
        self._all_tools_cache = all_t
        return all_t

    def call_tool(self, server: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        conn = self._servers.get(server)
        if not conn:
            raise ValueError(f"MCP server '{server}' not found. Available: {self.list_servers()}")
        return conn.call_tool(tool_name, arguments)

    def get_tools_summary(self) -> str:
        tools = self.list_tools()
        if not tools:
            return ""
        lines = ["<available_mcp_tools>"]
        by_srv: Dict[str, List[MCPToolInfo]] = {}
        for t in tools:
            by_srv.setdefault(t.server_name, []).append(t)
        for srv, ts in by_srv.items():
            lines.append(f'  <server name="{srv}">')
            for t in ts:
                lines.append(f"    <tool>")
                lines.append(f"      <name>{t.name}</name>")
                lines.append(f"      <description>{t.description}</description>")
                schema = t.input_schema
                if schema:
                    props = schema.get("properties", {})
                    req = schema.get("required", [])
                    params = []
                    for pn, pi in props.items():
                        r = " (required)" if pn in req else ""
                        params.append(f'        <param name="{pn}" type="{pi.get("type", "any")}"{r}>'
                                      f'{pi.get("description", "")}</param>')
                    if params:
                        lines.append("      <params>")
                        lines.extend(params)
                        lines.append("      </params>")
                lines.append(f"    </tool>")
            lines.append(f"  </server>")
        lines.append("</available_mcp_tools>")
        return "\n".join(lines)


def make_mcp_tools(mcp_manager: MCPManager):
    """Return MCP tool functions for the agent."""

    def mcp_list_tools(server: str = "") -> ToolResult:
        try:
            tools = mcp_manager.list_tools(server or None)
            lines = [f"[{t.server_name}] {t.name}: {t.description}" for t in tools]
            return ToolResult(True, "\n".join(lines) or "No MCP tools available")
        except Exception as e:
            return ToolResult(False, "", str(e))

    def mcp_call_tool(server: str, tool: str, arguments: Optional[Dict[str, Any]] = None) -> ToolResult:
        try:
            result = mcp_manager.call_tool(server, tool, arguments or {})
            return ToolResult(True, result)
        except Exception as e:
            return ToolResult(False, "", str(e))

    return {
        "mcp_list_tools": (mcp_list_tools, False),
        "mcp_call_tool":  (mcp_call_tool, False),
    }
