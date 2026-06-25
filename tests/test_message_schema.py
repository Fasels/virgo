from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.message import (
    MessageCreateRequest,
    MessageCreateResponse,
    request_digest,
    to_utc_millis,
)


def test_message_request_normalizes_single_phone_and_defaults():
    request = MessageCreateRequest.model_validate(
        {"phoneNumbers": ["+86 (139) 0000-0000"], "text": " hello "}
    )

    assert request.phone_numbers == ["+8613900000000"]
    assert request.text == "hello"
    assert request.with_delivery_report is True
    assert request.priority == 0


@pytest.mark.parametrize(
    "body",
    [
        {"phoneNumbers": [], "text": "hello"},
        {"phoneNumbers": ["1", "2"], "text": "hello"},
        {"phoneNumbers": ["not-phone"], "text": "hello"},
        {"phoneNumbers": ["+86139"], "text": "   "},
        {"phoneNumbers": ["+86139"], "priority": 128, "text": "hello"},
        {"phoneNumbers": ["+86139"], "priority": True, "text": "hello"},
        {"phoneNumbers": ["+86139"], "withDeliveryReport": 1, "text": "hello"},
        {"phoneNumbers": ["+86139"], "metadata": [], "text": "hello"},
    ],
)
def test_message_request_rejects_invalid_payloads(body):
    with pytest.raises(ValidationError):
        MessageCreateRequest.model_validate(body)


def test_message_request_requires_timezone_aware_dates():
    with pytest.raises(ValidationError):
        MessageCreateRequest.model_validate(
            {
                "phoneNumbers": ["+86139"],
                "text": "hello",
                "validUntil": "2030-01-01T00:00:00",
            }
        )


def test_message_request_rejects_schedule_after_valid_until():
    with pytest.raises(ValidationError, match="scheduleAt"):
        MessageCreateRequest.model_validate(
            {
                "phoneNumbers": ["+86139"],
                "text": "hello",
                "scheduleAt": "2030-01-02T00:00:00Z",
                "validUntil": "2030-01-01T00:00:00Z",
            }
        )


def test_message_request_uses_android_aliases_and_ignores_unknown_fields():
    request = MessageCreateRequest.model_validate(
        {
            "phoneNumbers": ["+86139"],
            "text": "hello",
            "deviceId": "dev_1",
            "simNumber": 1,
            "withDeliveryReport": False,
            "conversationId": "conv_1",
            "future": "ignored",
        }
    )

    dumped = request.model_dump(by_alias=True)
    assert dumped["deviceId"] == "dev_1"
    assert dumped["simNumber"] == 1
    assert dumped["withDeliveryReport"] is False
    assert dumped["conversationId"] == "conv_1"
    assert "future" not in dumped


def test_request_digest_is_stable_and_changes_with_content():
    first = MessageCreateRequest.model_validate(
        {
            "phoneNumbers": ["+86 13900000000"],
            "text": "hello",
            "metadata": {"b": 2, "a": 1},
            "validUntil": "2030-01-01T08:00:00+08:00",
        }
    )
    same = MessageCreateRequest.model_validate(
        {
            "metadata": {"a": 1, "b": 2},
            "text": "hello",
            "phoneNumbers": ["+8613900000000"],
            "validUntil": "2030-01-01T00:00:00Z",
        }
    )
    changed = MessageCreateRequest.model_validate(
        {"phoneNumbers": ["+8613900000000"], "text": "changed"}
    )

    assert request_digest(first) == request_digest(same)
    assert request_digest(first) != request_digest(changed)


def test_utc_millis_and_response_aliases():
    occurred_at = datetime(2030, 1, 1, tzinfo=timezone.utc)
    response = MessageCreateResponse(
        id="msg_1",
        state="Pending",
        deviceId="dev_1",
        simNumber=1,
        conversationId="conv_1",
        createdAt="2030-01-01T00:00:00.000Z",
    )

    assert to_utc_millis(occurred_at) == 1_893_456_000_000
    assert response.model_dump(by_alias=True)["deviceId"] == "dev_1"
