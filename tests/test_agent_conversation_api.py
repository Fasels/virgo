from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from app.application import create_app
from app.config import Settings
from app.security import hash_password


def insert_account(connection, account_id, username, password_hash, area):
    connection.execute(
        """
        INSERT INTO accounts(id, username, password_hash, areas, status)
        VALUES(%s, %s, %s, %s, 'ACTIVE')
        """,
        (account_id, username, password_hash, area),
    )
    return account_id


def bind_account_sim(connection, account_id, sim_id):
    connection.execute(
        """
        INSERT INTO account_sim_cards(account_id, sim_card_id)
        VALUES(%s, %s)
        """,
        (account_id, sim_id),
    )


def _insert_conversation_fixture(connection, clean_database, area: str):
    suffix = uuid4().hex
    now = 1_800_000_000_000
    device_id = clean_database.track(f"dev_agent_{suffix}")
    sim_id = f"sim_agent_{suffix}"
    phone = clean_database.track_phone("+86" + str(uuid4().int)[:11])
    contact_id = f"contact_agent_{suffix}"
    conversation_id = f"conv_agent_{suffix}"
    message_id = clean_database.track_message_key(f"msg-agent-{suffix}")
    connection.execute(
        """
        INSERT INTO devices(id, name, token_hash, login, enabled, status, last_seen_at)
        VALUES(%s, %s, %s, %s, TRUE, 'online', %s)
        """,
        (device_id, "agent phone", f"token_{suffix}", f"login_{suffix}", now),
    )
    connection.execute(
        """
        INSERT INTO sim_cards(id, device_id, slot_index, sim_number, areas)
        VALUES(%s, %s, 0, 1, %s)
        """,
        (sim_id, device_id, area),
    )
    connection.execute(
        """
        INSERT INTO contacts(id, phone_number, normalized_phone_number, source)
        VALUES(%s, %s, %s, 'MANUAL')
        """,
        (contact_id, phone, phone),
    )
    connection.execute(
        """
        INSERT INTO conversations(
            id, external_phone_number, contact_id, device_id, sim_card_id,
            sim_number, areas, status, unread_count, last_message_preview,
            last_message_direction, last_message_at, created_at, updated_at
        )
        VALUES(%s, %s, %s, %s, %s, 1, %s, 'OPEN', 3, %s, 'INBOUND', %s, %s, %s)
        """,
        (
            conversation_id,
            phone,
            contact_id,
            device_id,
            sim_id,
            area,
            f"{area} hello",
            now,
            now,
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO messages(
            id, conversation_id, direction, message_type, text_content,
            from_phone_number, to_phone_number, state, device_id, sim_card_id,
            sim_number, idempotency_key, received_at, created_at, updated_at
        )
        VALUES(%s, %s, 'INBOUND', 'SMS', %s, %s, NULL, 'Received', %s, %s, 1, %s, %s, %s, %s)
        """,
        (
            message_id,
            conversation_id,
            f"{area} message",
            phone,
            device_id,
            sim_id,
            message_id,
            now,
            now,
            now,
        ),
    )
    return conversation_id, message_id, sim_id


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/agent/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["token"]


def test_agent_conversation_list_returns_only_bound_sim_conversations(clean_database):
    north_user = "north_" + uuid4().hex
    south_user = "south_" + uuid4().hex
    password = "correct-password"
    with psycopg.connect(clean_database.dsn) as connection:
        north_account = insert_account(
            connection,
            "acct_" + uuid4().hex,
            north_user,
            hash_password(password),
            "same-area",
        )
        insert_account(
            connection,
            "acct_" + uuid4().hex,
            south_user,
            hash_password(password),
            "same-area",
        )
        north_conversation, _, north_sim = _insert_conversation_fixture(
            connection, clean_database, "same-area"
        )
        south_conversation, _, _ = _insert_conversation_fixture(
            connection, clean_database, "same-area"
        )
        bind_account_sim(connection, north_account, north_sim)
        connection.commit()

    app = create_app(Settings(clean_database.dsn, "registration-secret", "business-secret"))
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _login(client, north_user, password)
        response = client.get(
            "/agent/v1/conversations",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()]
    assert ids == [north_conversation]
    assert south_conversation not in ids


def test_agent_can_search_conversations_by_contact_phone(clean_database):
    username = "search_" + uuid4().hex
    password = "correct-password"
    suffix = uuid4().hex
    now = 1_800_000_000_000
    device_id = clean_database.track(f"dev_search_{suffix}")
    contact_phone = clean_database.track_phone("+86" + str(uuid4().int)[:11])
    contact_id = f"contact_search_{suffix}"
    sim_a = f"sim_search_a_{suffix}"
    sim_b = f"sim_search_b_{suffix}"
    sim_hidden = f"sim_search_hidden_{suffix}"
    conversation_a = f"conv_search_a_{suffix}"
    conversation_b = f"conv_search_b_{suffix}"
    conversation_hidden = f"conv_search_hidden_{suffix}"
    with psycopg.connect(clean_database.dsn) as connection:
        account_id = insert_account(
            connection,
            "acct_" + uuid4().hex,
            username,
            hash_password(password),
            "north",
        )
        connection.execute(
            """
            INSERT INTO devices(id, name, token_hash, login, enabled, status, last_seen_at)
            VALUES(%s, %s, %s, %s, TRUE, 'online', %s)
            """,
            (device_id, "agent phone", f"token_{suffix}", f"login_{suffix}", now),
        )
        for sim_id, sim_number, service_phone in (
            (sim_a, 1, "+8613800000001"),
            (sim_b, 2, "+8613800000002"),
            (sim_hidden, 3, "+8613800000003"),
        ):
            connection.execute(
                """
                INSERT INTO sim_cards(
                    id, device_id, slot_index, sim_number, phone_number, areas
                )
                VALUES(%s, %s, %s, %s, %s, 'north')
                """,
                (sim_id, device_id, sim_number - 1, sim_number, service_phone),
            )
        bind_account_sim(connection, account_id, sim_a)
        bind_account_sim(connection, account_id, sim_b)
        connection.execute(
            """
            INSERT INTO contacts(
                id, phone_number, normalized_phone_number, remark, source, areas
            )
            VALUES(%s, %s, %s, %s, 'MANUAL', 'north')
            """,
            (contact_id, contact_phone, contact_phone, "VIP customer"),
        )
        for conversation_id, sim_id, sim_number in (
            (conversation_a, sim_a, 1),
            (conversation_b, sim_b, 2),
            (conversation_hidden, sim_hidden, 3),
        ):
            connection.execute(
                """
                INSERT INTO conversations(
                    id, external_phone_number, contact_id, device_id, sim_card_id,
                    sim_number, areas, status, created_at, updated_at
                )
                VALUES(%s, %s, %s, %s, %s, %s, 'north', 'OPEN', %s, %s)
                """,
                (
                    conversation_id,
                    contact_phone,
                    contact_id,
                    device_id,
                    sim_id,
                    sim_number,
                    now,
                    now,
                ),
            )
        connection.commit()

    app = create_app(Settings(clean_database.dsn, "registration-secret", "business-secret"))
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _login(client, username, password)
        response = client.get(
            "/agent/v1/conversation-search",
            params={"phoneNumber": contact_phone[-6:]},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json() == [
        {
            "contactPhoneNumber": contact_phone,
            "remark": "VIP customer",
            "servicePhoneNumber": "+8613800000001",
            "conversationId": conversation_a,
        },
        {
            "contactPhoneNumber": contact_phone,
            "remark": "VIP customer",
            "servicePhoneNumber": "+8613800000002",
            "conversationId": conversation_b,
        },
        {
            "contactPhoneNumber": contact_phone,
            "remark": "VIP customer",
            "servicePhoneNumber": "+8613800000003",
            "conversationId": conversation_hidden,
        },
    ]


def test_agent_message_history_allows_unbound_sim_access(clean_database):
    username = "north_" + uuid4().hex
    password = "correct-password"
    with psycopg.connect(clean_database.dsn) as connection:
        insert_account(
            connection,
            "acct_" + uuid4().hex,
            username,
            hash_password(password),
            "south",
        )
        south_conversation, message_id, _ = _insert_conversation_fixture(
            connection, clean_database, "south"
        )
        connection.commit()

    app = create_app(Settings(clean_database.dsn, "registration-secret", "business-secret"))
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _login(client, username, password)
        response = client.get(
            f"/agent/v1/conversations/{south_conversation}/messages",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()[0]["id"] == message_id
    assert response.json()[0]["conversationId"] == south_conversation


def test_agent_can_mark_matching_conversation_read(clean_database):
    username = "north_" + uuid4().hex
    password = "correct-password"
    with psycopg.connect(clean_database.dsn) as connection:
        insert_account(
            connection,
            "acct_" + uuid4().hex,
            username,
            hash_password(password),
            "north",
        )
        account_id = connection.execute(
            "SELECT id FROM accounts WHERE username = %s",
            (username,),
        ).fetchone()[0]
        conversation_id, _, sim_id = _insert_conversation_fixture(
            connection, clean_database, "north"
        )
        bind_account_sim(connection, account_id, sim_id)
        connection.commit()

    app = create_app(Settings(clean_database.dsn, "registration-secret", "business-secret"))
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _login(client, username, password)
        response = client.patch(
            f"/agent/v1/conversations/{conversation_id}/read",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    with psycopg.connect(clean_database.dsn) as connection:
        unread_count = connection.execute(
            "SELECT unread_count FROM conversations WHERE id = %s",
            (conversation_id,),
        ).fetchone()[0]
    assert unread_count == 0


def test_agent_can_mark_unbound_conversation_read(clean_database):
    username = "north_" + uuid4().hex
    password = "correct-password"
    with psycopg.connect(clean_database.dsn) as connection:
        insert_account(
            connection,
            "acct_" + uuid4().hex,
            username,
            hash_password(password),
            "north",
        )
        conversation_id, _, _ = _insert_conversation_fixture(
            connection, clean_database, "south"
        )
        connection.commit()

    app = create_app(Settings(clean_database.dsn, "registration-secret", "business-secret"))
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _login(client, username, password)
        response = client.patch(
            f"/agent/v1/conversations/{conversation_id}/read",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    with psycopg.connect(clean_database.dsn) as connection:
        unread_count = connection.execute(
            "SELECT unread_count FROM conversations WHERE id = %s",
            (conversation_id,),
        ).fetchone()[0]
    assert unread_count == 0


def test_agent_can_reply_to_matching_conversation_route(clean_database):
    username = "north_" + uuid4().hex
    password = "correct-password"
    key = clean_database.track_message_key("agent-reply:" + uuid4().hex)
    with psycopg.connect(clean_database.dsn) as connection:
        account_id = insert_account(
            connection,
            "acct_" + uuid4().hex,
            username,
            hash_password(password),
            "north",
        )
        conversation_id, _, sim_id = _insert_conversation_fixture(
            connection, clean_database, "north"
        )
        bind_account_sim(connection, account_id, sim_id)
        route = connection.execute(
            """
            SELECT external_phone_number, device_id, sim_card_id, sim_number
            FROM conversations
            WHERE id = %s
            """,
            (conversation_id,),
        ).fetchone()
        connection.commit()

    app = create_app(Settings(clean_database.dsn, "registration-secret", "business-secret"))
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _login(client, username, password)
        response = client.post(
            f"/agent/v1/conversations/{conversation_id}/messages",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": key,
            },
            json={"text": "客服回复"},
        )

    assert response.status_code == 201
    with psycopg.connect(clean_database.dsn) as connection:
        message = connection.execute(
            """
            SELECT direction, conversation_id, to_phone_number, device_id,
                   sim_card_id, sim_number, state
            FROM messages
            WHERE id = %s
            """,
            (response.json()["id"],),
        ).fetchone()
    assert message == (
        "OUTBOUND",
        conversation_id,
        route[0],
        route[1],
        route[2],
        route[3],
        "Pending",
    )


def test_agent_reply_requires_idempotency_key(clean_database):
    username = "north_" + uuid4().hex
    password = "correct-password"
    with psycopg.connect(clean_database.dsn) as connection:
        insert_account(
            connection,
            "acct_" + uuid4().hex,
            username,
            hash_password(password),
            "north",
        )
        account_id = connection.execute(
            "SELECT id FROM accounts WHERE username = %s",
            (username,),
        ).fetchone()[0]
        conversation_id, _, sim_id = _insert_conversation_fixture(
            connection, clean_database, "north"
        )
        bind_account_sim(connection, account_id, sim_id)
        connection.commit()

    app = create_app(Settings(clean_database.dsn, "registration-secret", "business-secret"))
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _login(client, username, password)
        response = client.post(
            f"/agent/v1/conversations/{conversation_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "客服回复"},
        )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"
