from datetime import datetime, timezone
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from app.application import create_app
from app.config import Settings
from app.services.agent_event_publisher import AgentEventRegistry


def test_inbound_conversation_copies_area_from_receiving_sim(clean_database):
    marker = clean_database.track_push_token("pytest-agent-area-" + uuid4().hex)
    sender = clean_database.track_phone("+86" + str(uuid4().int)[:11])
    inbox_id = clean_database.track_message_key("agent-area:" + uuid4().hex)
    recipient = "+8613900000000"
    app = create_app(
        Settings(clean_database.dsn, "registration-secret", "business-secret")
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        registration = client.post(
            "/mobile/v1/device",
            headers={"Authorization": "Bearer registration-secret"},
            json={
                "name": "agent-area-phone",
                "pushToken": marker,
                "simCards": [
                    {
                        "slotIndex": 0,
                        "simNumber": 1,
                        "phoneNumber": recipient,
                    }
                ],
            },
        ).json()
        clean_database.track(registration["id"])
        with psycopg.connect(clean_database.dsn) as connection:
            connection.execute(
                "UPDATE sim_cards SET areas = %s WHERE device_id = %s AND sim_number = 1",
                ("south", registration["id"]),
            )
            connection.commit()

        response = client.post(
            "/mobile/v1/inbox",
            headers={"Authorization": f"Bearer {registration['token']}"},
            json={
                "id": inbox_id,
                "type": "SMS",
                "sender": sender,
                "recipient": recipient,
                "simNumber": 1,
                "subscriptionId": 3,
                "receivedAt": datetime.now(timezone.utc).isoformat(),
                "textMessage": {"text": "area hello"},
                "dataMessage": None,
            },
        )

    assert response.status_code == 201
    with psycopg.connect(clean_database.dsn) as connection:
        area = connection.execute(
            "SELECT areas FROM conversations WHERE id = %s",
            (response.json()["conversationId"],),
        ).fetchone()[0]
    assert area == "south"


def test_outbound_conversation_copies_area_from_selected_sim(clean_database):
    marker = clean_database.track_push_token("pytest-agent-outbound-area-" + uuid4().hex)
    phone = clean_database.track_phone("+86" + str(uuid4().int)[:11])
    key = clean_database.track_message_key("agent-outbound-area:" + uuid4().hex)
    app = create_app(
        Settings(clean_database.dsn, "registration-secret", "business-secret")
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        registration = client.post(
            "/mobile/v1/device",
            headers={"Authorization": "Bearer registration-secret"},
            json={
                "name": "agent-outbound-area-phone",
                "pushToken": marker,
                "simCards": [{"slotIndex": 0, "simNumber": 1}],
            },
        ).json()
        clean_database.track(registration["id"])
        with psycopg.connect(clean_database.dsn) as connection:
            connection.execute(
                "UPDATE sim_cards SET areas = %s WHERE device_id = %s AND sim_number = 1",
                ("north", registration["id"]),
            )
            connection.commit()

        response = client.post(
            "/api/v1/messages",
            headers={
                "Authorization": "Bearer business-secret",
                "Idempotency-Key": key,
            },
            json={"phoneNumbers": [phone], "text": "area outbound"},
        )

    assert response.status_code == 201
    with psycopg.connect(clean_database.dsn) as connection:
        area = connection.execute(
            "SELECT areas FROM conversations WHERE id = %s",
            (response.json()["conversationId"],),
        ).fetchone()[0]
    assert area == "north"


def test_inbound_message_publishes_only_to_matching_agent_area(clean_database):
    marker = clean_database.track_push_token("pytest-agent-event-" + uuid4().hex)
    sender = clean_database.track_phone("+86" + str(uuid4().int)[:11])
    inbox_id = clean_database.track_message_key("agent-event:" + uuid4().hex)
    registry = AgentEventRegistry(heartbeat_seconds=0.01)
    app = create_app(
        Settings(clean_database.dsn, "registration-secret", "business-secret"),
        agent_event_registry=registry,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        registration = client.post(
            "/mobile/v1/device",
            headers={"Authorization": "Bearer registration-secret"},
            json={
                "name": "agent-event-phone",
                "pushToken": marker,
                "simCards": [{"slotIndex": 0, "simNumber": 1}],
            },
        ).json()
        clean_database.track(registration["id"])
        with psycopg.connect(clean_database.dsn) as connection:
            connection.execute(
                "UPDATE sim_cards SET areas = %s WHERE device_id = %s AND sim_number = 1",
                ("north", registration["id"]),
            )
            connection.commit()

        north = registry.register("north")
        south = registry.register("south")
        response = client.post(
            "/mobile/v1/inbox",
            headers={"Authorization": f"Bearer {registration['token']}"},
            json={
                "id": inbox_id,
                "type": "SMS",
                "sender": sender,
                "recipient": None,
                "simNumber": 1,
                "subscriptionId": 3,
                "receivedAt": datetime.now(timezone.utc).isoformat(),
                "textMessage": {"text": "north event"},
                "dataMessage": None,
            },
        )

    assert response.status_code == 201
    north_stream = registry.stream(north)
    south_stream = registry.stream(south)
    north_event = next(north_stream)
    south_event = next(south_stream)
    north_stream.close()
    south_stream.close()
    assert "event: inbound_message\n" in north_event
    assert f'"conversationId":"{response.json()["conversationId"]}"' in north_event
    assert f'"messageId":"{response.json()["id"]}"' in north_event
    assert '"areas":"north"' in north_event
    assert south_event.startswith(": ping ")
