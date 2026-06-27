from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from queue import Empty, Queue
from threading import Event, Lock
from typing import Iterator


_CLOSE = object()


def encode_agent_event(
    event_name: str,
    *,
    areas: str,
    conversation_id: str,
    message_id: str,
) -> str:
    encoded_id = json.dumps(message_id, ensure_ascii=False)[1:-1]
    data = json.dumps(
        {
            "conversationId": conversation_id,
            "messageId": message_id,
            "areas": areas,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"id: {encoded_id}\nevent: {event_name}\ndata: {data}\n\n"


def encode_heartbeat() -> str:
    occurred_at = (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    return f": ping {occurred_at}\n\n"


@dataclass(slots=True)
class AgentEventConnection:
    areas: str
    events: Queue[object] = field(default_factory=Queue)
    closed: Event = field(default_factory=Event)

    def close(self) -> None:
        if not self.closed.is_set():
            self.closed.set()
            self.events.put(_CLOSE)


class AgentEventRegistry:
    def __init__(self, *, heartbeat_seconds: float = 20):
        if heartbeat_seconds <= 0:
            raise ValueError("heartbeat_seconds must be positive")
        self._heartbeat_seconds = heartbeat_seconds
        self._connections: dict[str, AgentEventConnection] = {}
        self._lock = Lock()

    def register(self, areas: str) -> AgentEventConnection:
        connection = AgentEventConnection(areas)
        with self._lock:
            previous = self._connections.get(areas)
            self._connections[areas] = connection
        if previous is not None:
            previous.close()
        return connection

    def unregister(self, connection: AgentEventConnection) -> None:
        with self._lock:
            if self._connections.get(connection.areas) is connection:
                del self._connections[connection.areas]
        connection.close()

    def publish(
        self,
        event_name: str,
        *,
        areas: str,
        conversation_id: str,
        message_id: str,
    ) -> bool:
        with self._lock:
            connection = self._connections.get(areas)
            if connection is None or connection.closed.is_set():
                return False
            connection.events.put(
                encode_agent_event(
                    event_name,
                    areas=areas,
                    conversation_id=conversation_id,
                    message_id=message_id,
                )
            )
            return True

    def stream(self, connection: AgentEventConnection) -> Iterator[str]:
        try:
            while not connection.closed.is_set():
                try:
                    item = connection.events.get(timeout=self._heartbeat_seconds)
                except Empty:
                    yield encode_heartbeat()
                    continue
                if item is _CLOSE:
                    return
                yield str(item)
        finally:
            self.unregister(connection)


class RegistryAgentEventPublisher:
    def __init__(self, registry: AgentEventRegistry):
        self._registry = registry

    def publish_inbound_message(
        self,
        areas: str,
        message_id: str,
        conversation_id: str,
    ) -> None:
        self._registry.publish(
            "inbound_message",
            areas=areas,
            message_id=message_id,
            conversation_id=conversation_id,
        )


class NoOpAgentEventPublisher:
    def publish_inbound_message(
        self,
        areas: str,
        message_id: str,
        conversation_id: str,
    ) -> None:
        return None
