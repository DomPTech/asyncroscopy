"""Abstract base class for LLM Tango devices."""

import json
from abc import abstractmethod
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any, Callable, Iterable, Self

import tango
from tango.server import Device, attribute, command, device_property
from asyncroscopy.instruments.instrument import CombinedMeta


@dataclass
class ProviderConfig:
    model_provider: str = "openai"
    chat_model_name: str = "gpt-4o"
    api_key: str = ""
    api_base: str = ""
    temperature: float = 0.7
    reasoning: bool = False
    metadata: dict[str, Any] | None = None


@dataclass
class Agent:
    name: str
    system_prompt: str
    tools: list[str]
    model: ProviderConfig
    description: str = ""
    metadata: dict[str, Any] | None = None
    
    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Deserialize an Agent from a plain dict, handling nested ProviderConfig."""
        if "model" in data and isinstance(data["model"], dict):
            data = {**data, "model": ProviderConfig(**data["model"])}
        return cls(**data)

@dataclass
class MCPConfig:
    name: str
    transport: str = "http"

    # Stdio transport options
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    # URL-based transport options
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)

    metadata: dict[str, Any] | None = None


class BaseLLM(Device, metaclass=CombinedMeta):
    startup_mcps = device_property(dtype=(str,), default_value=(), doc="List of JSON-serialized MCPConfigs for startup.")
    startup_agents = device_property(dtype=(str,), default_value=(), doc="List of JSON-serialized Agent configs for startup.")

    max_steps = attribute(label="Max Steps", dtype=int, access=tango.AttrWriteType.READ_WRITE)

    green_mode = tango.GreenMode.Asyncio

    async def init_device(self) -> None:
        await Device.init_device(self)
        self.set_state(tango.DevState.INIT)

        self._max_steps = 5

        # Registries
        self._agents: dict[str, Agent] = {}
        self._tools: dict[str, Any] = {}
        self._mcp_clients: dict[str, MCPConfig] = {}

        try:
            await self._init_device_impl()

            for mcp_json in self.startup_mcps:
                try:
                    mcp_cfg = MCPConfig(**json.loads(mcp_json))
                    await self._connect_mcp(mcp_cfg)
                except Exception as e:
                    self.error_stream(f"Failed to parse/connect MCP: {e}")

            for agent_json in self.startup_agents:
                try:
                    agent = Agent.from_dict(json.loads(agent_json))
                    if self._spawn_agent(agent):
                        self._agents[agent.name] = agent
                        self.info_stream(f"Spawned startup agent: {agent.name}")
                except Exception as e:
                    self.error_stream(f"Failed to parse/spawn startup agent: {e}")

            self.set_state(tango.DevState.ON)
        except Exception as e:
            self.set_state(tango.DevState.FAULT)
            self.set_status(f"Initialization failed: {e}")
            self.error_stream(f"Failed to start: {e}")

    async def delete_device(self) -> None:
        for agent in self._agents.values():
            self._despawn_agent(agent)
        for mcp_config in self._mcp_clients.values():
            await self._disconnect_mcp(mcp_config)

    @abstractmethod
    async def _init_device_impl(self) -> None:
        """Subclass-specific initialization, called before MCP/agent setup."""
        pass

    def read_max_steps(self) -> int:
        return self._max_steps

    def write_max_steps(self, value: int) -> None:
        if value < 1:
            raise ValueError("max_steps must be at least 1.")
        self._max_steps = value

    @attribute(dtype=(str,), max_dim_x=100)
    def agents(self) -> list[str]:
        """Names of all currently registered agents."""
        return list(self._agents.keys())

    @attribute(dtype=(str,), max_dim_x=256)
    def available_tools(self) -> list[str]:
        """Names of all tools currently loaded from connected MCP servers."""
        return list(self._tools.keys())

    @attribute(dtype=(str,), max_dim_x=256)
    def mcp_connections(self) -> list[str]:
        """Details of active MCP connections."""
        return list(self._mcp_clients.keys())

    @command(dtype_in=str, dtype_out=str)
    async def Query(self, prompt: str) -> str:
        """Query the LLM and return the response."""
        self.set_state(tango.DevState.RUNNING)
        try:
            return await self._run_query(prompt)
        except Exception as e:
            self.error_stream(f"Query error: {e}")
            return str(e)
        finally:
            if self.get_state() == tango.DevState.RUNNING:
                self.set_state(tango.DevState.ON)

    @command(dtype_in=str, dtype_out=bool)
    async def ConnectMCP(self, config: str) -> bool:
        """Connect to an MCP server. Accepts a JSON-serialized MCPConfig."""
        try:
            mcp_cfg = MCPConfig(**json.loads(config))
        except Exception as e:
            self.error_stream(f"Failed to parse MCP config: {e}")
            return False
        success = await self._connect_mcp(mcp_cfg)
        if success:
            self._mcp_clients[mcp_cfg.name] = mcp_cfg
            self.info_stream(f"Connected to MCP server: {mcp_cfg.name}")
        return success

    @command(dtype_in=str, dtype_out=bool)
    async def DisconnectMCP(self, name: str) -> bool:
        """Disconnect from an MCP server by name."""
        try:
            mcp_config = self._mcp_clients.get(name)
            if not mcp_config:
                self.error_stream(f"MCP server {name} not found")
                return False
            success = await self._disconnect_mcp(mcp_config)
            if success:
                del self._mcp_clients[name]
                self.info_stream(f"Disconnected from MCP server: {name}")
            return success
        except Exception as e:
            self.error_stream(f"Failed to disconnect MCP: {e}")
            return False
    
    @command(dtype_in=str, dtype_out=bool)
    async def SpawnAgent(self, config: str) -> bool:
        """Spawn a new agent from a JSON-serialized Agent config."""
        try:
            agent = Agent.from_dict(json.loads(config))
            success = self._spawn_agent(agent)
            if success:
                self._agents[agent.name] = agent
            return success
        except Exception as e:
            self.error_stream(f"Failed to spawn agent: {e}")
            return False

    @abstractmethod
    async def _run_query(self, prompt: str) -> str:
        pass

    @abstractmethod
    async def _connect_mcp(self, config: MCPConfig) -> bool:
        pass

    @abstractmethod
    async def _disconnect_mcp(self, config: MCPConfig) -> bool:
        pass

    @abstractmethod
    def _spawn_agent(self, agent: Agent) -> bool:
        pass

    @abstractmethod
    def _despawn_agent(self, agent: Agent) -> bool:
        pass

    @staticmethod
    def _filter_tools(
        items: Iterable[Any],
        patterns: str | Iterable[str],
        key: str | Callable[[Any], str] | None = None,
        case_sensitive: bool = False,
        exclude: bool = False,
    ) -> list[Any]:
        """
        Filter tool objects by glob pattern against a derived string key.

        Args:
            items: Tool objects to filter.
            patterns: One or more glob patterns (e.g. ``["web_*", "*_tool"]``).
            key: Attribute name, accessor function, or None for auto-detection.
            case_sensitive: Match case when False (default).
            exclude: Invert — return items that do NOT match any pattern.

        Returns:
            Filtered list of tool objects.
        """
        if isinstance(patterns, str):
            patterns = [patterns]

        def _extract_key(obj: Any) -> str:
            if callable(key):
                val = key(obj)
            elif isinstance(key, str):
                val = (
                    getattr(obj, key, None)
                    if hasattr(obj, key)
                    else (obj.get(key) if isinstance(obj, dict) else getattr(obj, key, str(obj)))
                )
            else:
                if hasattr(obj, "name") and isinstance(obj.name, str):
                    val = obj.name
                elif hasattr(obj, "id") and isinstance(obj.id, str):
                    val = obj.id
                elif isinstance(obj, dict) and "name" in obj:
                    val = obj["name"]
                else:
                    val = str(obj)
            val_str = str(val)
            return val_str if case_sensitive else val_str.lower()

        target_patterns = [p if case_sensitive else p.lower() for p in patterns]

        return [
            item for item in items
            if any(fnmatch(_extract_key(item), pat) for pat in target_patterns) != exclude
        ]
