from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .registry import AgentMessage, AgentRegistry


@dataclass
class OrchestratorResult:
    responses: List[Dict[str, Any]] = field(default_factory=list)
    broadcast: List[Dict[str, Any]] = field(default_factory=list)


class AgentOrchestrator:
    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self.message_log: List[AgentMessage] = []

    def send(self, sender: str, recipient: str, topic: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        message = AgentMessage(sender=sender, recipient=recipient, topic=topic, payload=payload)
        self.message_log.append(message)
        return self.registry.route(message)

    def broadcast(self, sender: str, topic: str, payload: Dict[str, Any]) -> OrchestratorResult:
        result = OrchestratorResult()
        for agent in self.registry.subscribers(topic):
            message = AgentMessage(sender=sender, recipient=agent.agent_id, topic=topic, payload=payload)
            self.message_log.append(message)
            response = self.registry.route(message)
            result.broadcast.append({"agent_id": agent.agent_id, "response": response})
        return result
