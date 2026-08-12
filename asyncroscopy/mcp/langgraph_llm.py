"""Tango device wrapping a LangGraph agent swarm connected to MCP servers."""

import operator
import re
import sys
import time
import asyncio
import subprocess
import urllib.request
import urllib.error
import json
from typing import Annotated, Sequence, TypedDict

import tango
from tango.server import device_property

from asyncroscopy.mcp.llm import BaseLLM, Agent, MCPConfig

try:
    from langchain.chat_models import init_chat_model
    from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
    from langchain.agents import create_agent
    from langchain_mcp_adapters.client import MultiServerMCPClient

    from langgraph.graph import END, START, StateGraph
except ImportError:
    print("Missing dependencies! Please run:")
    print("uv sync --extra agent")
    sys.exit(1)


class AgentState(TypedDict):
    """State dictionary for each Agent node in the swarm graph."""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    next_agent: str
    current_task: str


class LangGraphLLM(BaseLLM):
    auto_pull_model = device_property(dtype=bool, default_value=True, doc="Automatically pull the Ollama model if not already downloaded.")

    green_mode = tango.GreenMode.Asyncio

    async def _init_device_impl(self) -> None:
        self._mcp_client = MultiServerMCPClient({})
        self._model = None  # Set per-agent via agent.model; shared model for the supervisor

    async def _run_query(self, prompt: str) -> str:
        return await self._run_swarm(prompt)

    async def ensure_ollama_running(self, model_name: str, host: str = "http://localhost:11434", timeout: int = 10) -> None:
        """Check if Ollama server is running, starting it and downloading the model if necessary."""

        def _sync_check() -> None:
            tags_url = f"{host.rstrip('/')}/api/tags"
            try:
                with urllib.request.urlopen(tags_url, timeout=1):
                    return
            except (urllib.error.URLError, TimeoutError, ConnectionRefusedError):
                pass
            
            if self.auto_pull_model: # Run command to download the model if it is not already
                print(f"[SYSTEM]: Ensuring model '{model_name}' is pulled (this may take a while if it is not already downloaded)...")
                try:
                    subprocess.run(
                        ["ollama", "pull", model_name],
                        check=True,
                        stderr=subprocess.DEVNULL
                    )
                except subprocess.CalledProcessError as e:
                    raise RuntimeError(f"Failed to pull Ollama model {model_name}: {e}")

            try:
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
            except FileNotFoundError:
                raise RuntimeError("Ollama binary not found on PATH.")

            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    with urllib.request.urlopen(tags_url, timeout=1):
                        return
                except (urllib.error.URLError, TimeoutError, ConnectionRefusedError):
                    time.sleep(0.5)

            raise RuntimeError(f"Ollama endpoint '{tags_url}' did not respond.")

        await asyncio.to_thread(_sync_check)

    async def _connect_mcp(self, config: MCPConfig) -> bool:
        """Connect to an MCP server and load its tools into the shared tool registry."""
        try:
            server_id = config.name
            # MultiServerMCPClient expects a dict of server configs keyed by name
            self._mcp_client.connections[server_id] = {
                k: v for k, v in {
                    "transport": config.transport,
                    "command": config.command,
                    "args": config.args or None,
                    "env": config.env or None,
                    "url": config.url,
                    "headers": config.headers or None,
                }.items() if v is not None
            }

            print(f"\n[SYSTEM]: Added MCP server '{server_id}'. Fetching tools...")
            tools = await self._mcp_client.get_tools()
            # Tools are stored as a list; index by name for the base registry
            self._tools = {t.name: t for t in tools}
            print(f"[SYSTEM]: Connected. Loaded {len(self._tools)} tools.")
        except Exception as e:
            self.error_stream(f"Failed to connect to MCP server: {e}")
            return False

        return True

    async def _disconnect_mcp(self, config: MCPConfig) -> bool:
        """Disconnect from an MCP server."""
        try:
            await self._mcp_client.close()
        except Exception as e:
            self.error_stream(f"Failed to disconnect from MCP server: {e}")
            return False
        return True

    def _spawn_agent(self, agent: Agent) -> bool:
        """Register a new agent in the swarm. Model initialization is deferred to query time."""
        try:
            print(f"\n[SYSTEM]: Registered agent '{agent.name}'")
            return True
        except Exception as e:
            self.error_stream(f"Failed to spawn agent: {e}")
            return False

    async def _init_model(self, agent: Agent):
        """Construct a LangChain chat model from the agent's ProviderConfig."""
        cfg = agent.model
        if cfg.model_provider == "ollama":
            # Ensure the model is available locally
            await self.ensure_ollama_running(cfg.chat_model_name)
            
            from langchain_ollama import ChatOllama
            return ChatOllama(
                model=cfg.local_model_name or cfg.chat_model_name,
                temperature=cfg.temperature,
                reasoning=cfg.reasoning,
            )

        model_kwargs = {
            "model": cfg.chat_model_name,
            "model_provider": cfg.model_provider,
            "temperature": cfg.temperature,
        }
        if cfg.api_key:
            model_kwargs["api_key"] = cfg.api_key
        if cfg.api_base:
            model_kwargs["api_base"] = cfg.api_base
        if cfg.metadata:
            model_kwargs |= cfg.metadata
        return init_chat_model(**model_kwargs)

    def _get_agent_tools(self, agent: Agent) -> list:
        """Return the tool objects permitted for this agent based on its glob patterns."""
        if "*" in agent.tools:
            return list(self._tools.values())
        return self._filter_tools(self._tools.values(), agent.tools)

    def _build_agent_executor(self, agent: Agent):
        """Bind this agent's allowed tools and construct its ReAct executor."""
        model = self._init_model(agent)
        agent_tools = self._get_agent_tools(agent)
        print(f"[SYSTEM]: Binding {len(agent_tools)} tools to {agent.name}")
        return create_agent(model=model, tools=agent_tools, system_prompt=agent.system_prompt)

    def _extract_json(self, text: str) -> str:
        """Strip markdown code fences (```json ... ``` or ``` ... ```) if present."""
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            return match.group(1)
        return text.strip()

    def _parse_routing_decision(self, content: str, valid_options: list[str], fallback: str) -> tuple[str, str]:
        """Parse a supervisor response's {'next': ...} decision with a fallback."""
        try:
            decision = json.loads(self._extract_json(content))
            next_agent = decision.get("next", fallback)
            subtask = decision.get("task", "")

            return next_agent if next_agent in valid_options else fallback, subtask
        except Exception as e:
            print(f"[SUPERVISOR ERROR]: {e}")
            return fallback, ""

    async def _stream_agent(self, agent_executor, messages, agent_label: str = "") -> str:
        """Run a create_agent executor while streaming tokens and tool calls to stdout."""
        prefix = f"[{agent_label}] " if agent_label else ""
        start_time = time.time()
        first_token_received = False
        final_content = ""

        async for event in agent_executor.astream_events({"messages": messages}, version="v2"):
            kind = event["event"]

            if kind == "on_chat_model_start":
                # A new generation round is starting (could be a tool-call round or the final answer)
                start_time = time.time()
                first_token_received = False

            elif kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if not first_token_received:
                    ttft = time.time() - start_time
                    print(f"\n{prefix}[DIAGNOSTIC]: Time to first token: {ttft:.2f}s")
                    print(f"{prefix}[GENERATION]: ", end="")
                    first_token_received = True
                if chunk.content:
                    print(chunk.content, end="")
                    sys.stdout.flush()

            elif kind == "on_chat_model_end":
                output = event["data"]["output"]
                tool_calls = getattr(output, "tool_calls", None) or []
                if not tool_calls:
                    # This round produced no tool calls, so it's the final answer
                    final_content = (output.content or "").strip()
                print()

            elif kind == "on_tool_start":
                tool_name = event["name"]
                tool_input = event["data"].get("input")
                print(f"{prefix}[EXECUTING TOOL]: {tool_name}({tool_input})")

            elif kind == "on_tool_end":
                output = event["data"].get("output")
                print(f"{prefix}[TOOL RESULT]: {output}")

        if final_content:
            print(f"{prefix}[FINAL ANSWER RETURNED]:\n{final_content}\n{'=' * 50}")
        return final_content

    async def _run_swarm(self, prompt: str) -> str:
        """Run the agent swarm with a given prompt, returning the final response."""
        agents = list(self._agents.values())

        if not agents:
            return "Swarm Error: No agents available. Use SpawnAgent to create at least one worker before querying."

        # Single-agent shortcut — no supervisor overhead needed
        if len(agents) == 1:
            agent = agents[0]
            agent_executor = self._build_agent_executor(agent)
            print(f"\n[{agent.name}] is working...")
            return await self._stream_agent(
                agent_executor, [HumanMessage(content=prompt)], agent_label=agent.name
            )

        builder = StateGraph(AgentState)
        agent_names = [a.name for a in agents]
        options = agent_names + ["FINISH"]

        def create_agent_node(agent: Agent):
            agent_executor = self._build_agent_executor(agent)

            async def node(state: AgentState):
                task = state.get("current_task", "Execute assigned tool.")
                print(f"\n[{agent.name}] assigned task: '{task}'")
                content = await self._stream_agent(agent_executor, [HumanMessage(content=task)], agent_label=agent.name)
                print(f"[{agent.name}] finished.\n")
                return {
                    "messages": [HumanMessage(content=f"[{agent.name}]: {content}", name=agent.name)]
                }
            return node

        for agent in agents:
            builder.add_node(agent.name, create_agent_node(agent))

        agent_roster = "\n".join(
            f"- {a.name}: {a.description or a.system_prompt}" for a in agents
        )

        # Supervisor needs its own model instance; use the first agent's config as default
        supervisor_model = self._init_model(agents[0])

        async def supervisor_node(state: AgentState):
            print("\n[Supervisor] Evaluating routing...")

            has_delegated = len(state["messages"]) > 1

            if not has_delegated:
                # First turn forces subagent routing
                instructions = (
                    f"Below are the available agents and what each is for:\n{agent_roster}\n\n"
                    "Based on the conversation, decide which agent should act next to progress the user's request.\n"
                    "Only output FINISH if the user's request has been fully and concretely answered — "
                    "not if an agent asked a question or said it couldn't complete the task; in that case, "
                    "route to a different agent who might be able to help instead."
                )
                valid_options, fallback = agent_names, agent_names[0]
            else:
                # Later turns either do normal routing or FINISH
                instructions = (
                    f"Active agents: {agent_names}.\n"
                    "Based on the conversation, decide who should act next.\n"
                    "If the user's request is fully resolved, output FINISH."
                )
                valid_options, fallback = options, "FINISH"

            sys_prompt = SystemMessage(
                content=(
                    f"You are the Swarm Supervisor. {instructions}\n"
                    "Respond with JSON containing two keys:\n"
                    f"1. 'next': One of {options}\n"
                    "2. 'task': The exact, isolated sub-task that ONLY this specific agent should perform right now. "
                    "Do NOT include steps intended for other agents.\n\n"
                    "Example output:\n"
                    '{"next": "image", "task": "Acquire a scanned HAADF image."}'
                )
            )
            response = await supervisor_model.ainvoke([sys_prompt] + list(state["messages"]))
            next_agent, subtask = self._parse_routing_decision(response.content, valid_options, fallback)
            if next_agent == "FINISH":
                print("[Supervisor] Decision: FINISH\n")

            return {
                "next_agent": next_agent,
                "current_task": subtask,
            }

        builder.add_node("Supervisor", supervisor_node)
        builder.add_edge(START, "Supervisor")

        for name in agent_names:
            builder.add_edge(name, "Supervisor")

        def route(state: AgentState) -> str:
            return "FINISH" if state["next_agent"] == "FINISH" else state["next_agent"]

        mapping = {name: name for name in agent_names}
        mapping["FINISH"] = END
        builder.add_conditional_edges("Supervisor", route, mapping)

        graph = builder.compile()

        print(f"\n{'='*50}\n[NEW REQUEST]: {prompt}\n{'=' * 50}")

        last_response = None
        async for chunk in graph.astream(
            {"messages": [HumanMessage(content=prompt)]},
            config={"recursion_limit": self._max_steps}
        ):
            for node_name, state_update in chunk.items():
                if node_name != "Supervisor" and "messages" in state_update:
                    msg = state_update["messages"][-1]
                    last_response = msg.content

        return last_response if last_response is not None else "Swarm Error: No agent produced a response before routing finished."

# ----------------------------------------------------------------------
# Server entry point
# ----------------------------------------------------------------------

if __name__ == "__main__":
    LangGraphLLM.run_server()