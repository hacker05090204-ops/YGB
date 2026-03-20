from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class AgentMessage:
    sender: str
    recipient: str
    topic: str
    payload: Dict[str, Any]


@dataclass
class RegisteredAgent:
    agent_id: str
    role: str
    handler: Callable[[AgentMessage], Dict[str, Any]]
    subscriptions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentRegistry:
    def __init__(self):
        self._agents: Dict[str, RegisteredAgent] = {}

    def register(self, agent: RegisteredAgent) -> None:
        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> Optional[RegisteredAgent]:
        return self._agents.get(agent_id)

    def list_agents(self) -> List[RegisteredAgent]:
        return list(self._agents.values())

    def route(self, message: AgentMessage) -> Dict[str, Any]:
        agent = self.get(message.recipient)
        if agent is None:
            raise KeyError(f"Unknown agent: {message.recipient}")
        return agent.handler(message)

    def subscribers(self, topic: str) -> List[RegisteredAgent]:
        return [agent for agent in self._agents.values() if topic in agent.subscriptions]
