from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
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

    def send(
        self,
        sender: str,
        recipient: str,
        topic: str,
        payload: Dict[str, Any],
        *,
        correlation_id: str = "",
        thread_id: str = "",
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        message = AgentMessage(
            sender=sender,
            recipient=recipient,
            topic=topic,
            payload=payload,
            correlation_id=correlation_id,
            thread_id=thread_id,
            metadata=dict(metadata or {}),
        )
        self.message_log.append(message)
        return self.registry.route(message)

    def broadcast(self, sender: str, topic: str, payload: Dict[str, Any]) -> OrchestratorResult:
        result = OrchestratorResult()
        for agent in self.registry.subscribers(topic):
            message = AgentMessage(
                sender=sender,
                recipient=agent.agent_id,
                topic=topic,
                payload=payload,
            )
            self.message_log.append(message)
            response = self.registry.route(message)
            result.broadcast.append({"agent_id": agent.agent_id, "response": response})
        return result

    def route_by_capability(
        self,
        sender: str,
        capability: str,
        topic: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        candidates = self.registry.find_by_capability(capability)
        if not candidates:
            raise KeyError(f"Unknown capability: {capability}")
        target = candidates[0]
        return self.send(
            sender=sender,
            recipient=target.agent_id,
            topic=topic,
            payload=payload,
            metadata={"capability": capability},
        )

    def send_parallel(
        self,
        sender: str,
        recipients: List[str],
        topic: str,
        payload: Dict[str, Any],
        *,
        max_workers: int | None = None,
    ) -> OrchestratorResult:
        result = OrchestratorResult()
        if not recipients:
            return result

        workers = max_workers or min(len(recipients), 8)
        with ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="agent-orch") as executor:
            future_map = {
                executor.submit(self.send, sender, recipient, topic, payload): recipient
                for recipient in recipients
            }
            for future in as_completed(future_map):
                recipient = future_map[future]
                response = future.result()
                result.responses.append({"agent_id": recipient, "response": response})
        return result
