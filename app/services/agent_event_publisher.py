from dataclasses import dataclass, field
import json
from queue import Empty, Queue
from threading import Event, Lock
from typing import Iterator


_CLOSE = object()


def encode_agent_event(
    event_name: str,
    *,
    account_id: str,
    conversation_id: str,
    message_id: str,
    sim_card_id: str | None = None,
    text_content: str | None = None,
    state: str = "Received",
    created_at: int | None = None,
) -> str:
    if not conversation_id or not message_id:
        raise ValueError("conversation_id and message_id are required")
    encoded_id = json.dumps(message_id, ensure_ascii=False)[1:-1]
    data = json.dumps(
        {
            "conversationId": conversation_id,
            "messageId": message_id,
            "accountId": account_id,
            "simCardId": sim_card_id,
            "textContent": text_content,
            "state": state,
            "createdAt": created_at,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"id: {encoded_id}\nevent: {event_name}\ndata: {data}\n\n"


def encode_heartbeat() -> str:
    return ": ping\n\n"


@dataclass(slots=True)
class AgentEventConnection:
    account_id: str
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

    def register(self, account_id: str) -> AgentEventConnection:
        connection = AgentEventConnection(account_id)
        with self._lock:
            previous = self._connections.get(account_id)
            self._connections[account_id] = connection
        if previous is not None:
            previous.close()
        return connection

    def unregister(self, connection: AgentEventConnection) -> None:
        with self._lock:
            if self._connections.get(connection.account_id) is connection:
                del self._connections[connection.account_id]
        connection.close()

    def publish(
        self,
        event_name: str,
        *,
        account_id: str,
        conversation_id: str,
        message_id: str,
        sim_card_id: str | None = None,
        text_content: str | None = None,
        state: str = "Received",
        created_at: int | None = None,
    ) -> bool:
        with self._lock:
            connection = self._connections.get(account_id)
            if connection is None or connection.closed.is_set():
                return False
            connection.events.put(
                encode_agent_event(
                    event_name,
                    account_id=account_id,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    sim_card_id=sim_card_id,
                    text_content=text_content,
                    state=state,
                    created_at=created_at,
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
        account_id: str,
        message_id: str,
        conversation_id: str,
        sim_card_id: str | None,
        text_content: str | None = None,
        state: str = "Received",
        created_at: int | None = None,
    ) -> None:
        self._registry.publish(
            "inbound_message",
            account_id=account_id,
            message_id=message_id,
            conversation_id=conversation_id,
            sim_card_id=sim_card_id,
            text_content=text_content,
            state=state,
            created_at=created_at,
        )


class NoOpAgentEventPublisher:
    def publish_inbound_message(
        self,
        account_id: str,
        message_id: str,
        conversation_id: str,
        sim_card_id: str | None,
        text_content: str | None = None,
        state: str = "Received",
        created_at: int | None = None,
    ) -> None:
        return None
