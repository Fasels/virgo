import json

from app.services.agent_event_publisher import (
    AgentEventRegistry,
    RegistryAgentEventPublisher,
    encode_agent_event,
    encode_heartbeat,
)


def test_agent_heartbeat_matches_android_keepalive_contract():
    assert encode_heartbeat() == ": ping\n\n"


def test_agent_inbound_message_event_contains_required_client_fields():
    event = encode_agent_event(
        "inbound_message",
        account_id="acct_1",
        conversation_id="conv_1",
        message_id="msg_1",
        sim_card_id="sim_1",
        text_content="Hello",
        state="Received",
        created_at=1800000000000,
    )

    assert event.startswith("id: msg_1\n")
    assert "\nevent: inbound_message\n" in event
    assert event.endswith("\n\n")
    payload = json.loads(event.split("data: ", 1)[1].splitlines()[0])
    assert payload == {
        "conversationId": "conv_1",
        "messageId": "msg_1",
        "accountId": "acct_1",
        "simCardId": "sim_1",
        "textContent": "Hello",
        "state": "Received",
        "createdAt": 1800000000000,
    }


def test_agent_inbound_message_event_rejects_empty_required_ids():
    for kwargs in (
        {"conversation_id": "", "message_id": "msg_1"},
        {"conversation_id": "conv_1", "message_id": ""},
    ):
        try:
            encode_agent_event(
                "inbound_message",
                account_id="acct_1",
                sim_card_id=None,
                **kwargs,
            )
        except ValueError as error:
            assert "conversation_id and message_id are required" in str(error)
        else:
            raise AssertionError("empty required ids should be rejected")


def test_registry_agent_event_publisher_delivers_full_inbound_payload():
    registry = AgentEventRegistry(heartbeat_seconds=0.01)
    connection = registry.register("acct_1")
    publisher = RegistryAgentEventPublisher(registry)

    publisher.publish_inbound_message(
        "acct_1",
        "msg_1",
        "conv_1",
        "sim_1",
        text_content="Hello",
        state="Received",
        created_at=1800000000000,
    )

    stream = registry.stream(connection)
    event = next(stream)
    stream.close()
    payload = json.loads(event.split("data: ", 1)[1].splitlines()[0])
    assert payload["messageId"] == "msg_1"
    assert payload["conversationId"] == "conv_1"
    assert payload["textContent"] == "Hello"
    assert payload["state"] == "Received"
    assert payload["createdAt"] == 1800000000000
