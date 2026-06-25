import json

from app.services.sse import SseConnectionRegistry, encode_message_enqueued
from app.services.message_publisher import RegistryMessageEnqueuedPublisher


def test_message_event_uses_android_contract():
    assert encode_message_enqueued("msg_1") == (
        "id: msg_1\n"
        "event: MessageEnqueued\n"
        'data: {"messageId":"msg_1"}\n\n'
    )


def test_message_event_json_escapes_untrusted_identifier():
    message_id = 'msg_"line\n'
    event = encode_message_enqueued(message_id)

    assert event.startswith("id: msg_\\\"line\\n\n")
    data = event.split("data: ", 1)[1].splitlines()[0]
    assert json.loads(data) == {"messageId": message_id}


def test_publish_targets_only_the_registered_device():
    registry = SseConnectionRegistry(heartbeat_seconds=0.01)
    first = registry.register("dev_1")
    second = registry.register("dev_2")

    assert registry.publish_message("dev_1", "msg_1") is True
    first_stream = registry.stream(first)
    second_stream = registry.stream(second)
    assert next(first_stream).startswith("id: msg_1\n")
    assert next(second_stream).startswith(": ping ")
    first_stream.close()
    second_stream.close()


def test_publish_without_connection_is_a_successful_no_op():
    registry = SseConnectionRegistry()

    assert registry.publish_message("dev_missing", "msg_1") is False


def test_registry_message_publisher_delivers_to_registry():
    registry = SseConnectionRegistry(heartbeat_seconds=0.01)
    connection = registry.register("dev_1")
    publisher = RegistryMessageEnqueuedPublisher(registry)

    publisher.publish("dev_1", "msg_1")

    stream = registry.stream(connection)
    assert next(stream).startswith("id: msg_1\n")
    stream.close()


def test_new_connection_replaces_old_and_old_cleanup_preserves_new():
    registry = SseConnectionRegistry(heartbeat_seconds=0.01)
    old = registry.register("dev_1")
    new = registry.register("dev_1")

    assert list(registry.stream(old)) == []
    registry.unregister(old)
    assert registry.publish_message("dev_1", "msg_1") is True
    new_stream = registry.stream(new)
    assert next(new_stream).startswith("id: msg_1\n")
    new_stream.close()


def test_idle_connection_emits_sse_comment_heartbeat():
    registry = SseConnectionRegistry(heartbeat_seconds=0.001)
    connection = registry.register("dev_1")
    stream = registry.stream(connection)

    heartbeat = next(stream)

    assert heartbeat.startswith(": ping ")
    assert heartbeat.endswith("Z\n\n")
    stream.close()


def test_closing_stream_unregisters_connection():
    registry = SseConnectionRegistry(heartbeat_seconds=0.001)
    connection = registry.register("dev_1")
    stream = registry.stream(connection)
    next(stream)

    stream.close()

    assert registry.publish_message("dev_1", "msg_1") is False
