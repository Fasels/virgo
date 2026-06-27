from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from app.application import create_app
from app.config import Settings
from app.security import hash_password


def _insert_account(connection, username: str, password: str, area: str) -> None:
    connection.execute(
        """
        INSERT INTO accounts(id, username, password_hash, areas, status)
        VALUES(%s, %s, %s, %s, 'ACTIVE')
        """,
        ("acct_" + uuid4().hex, username, hash_password(password), area),
    )


def _insert_contact(connection, clean_database, area: str, remark: str | None = None):
    suffix = uuid4().hex
    phone = clean_database.track_phone("+86" + str(uuid4().int)[:11])
    contact_id = f"contact_agent_contact_{suffix}"
    now = 1_800_000_000_000
    connection.execute(
        """
        INSERT INTO contacts(
            id, display_name, phone_number, normalized_phone_number, remark,
            status, source, last_contact_at, created_at, updated_at, areas
        )
        VALUES(%s, %s, %s, %s, %s, 'NORMAL', 'MANUAL', %s, %s, %s, %s)
        """,
        (
            contact_id,
            f"{area} contact",
            phone,
            phone,
            remark,
            now,
            now,
            now,
            area,
        ),
    )
    return contact_id, phone


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["token"]


def test_agent_contact_list_returns_only_matching_area(clean_database):
    username = "north_contact_" + uuid4().hex
    password = "correct-password"
    area = "north_" + uuid4().hex[:12]
    other_area = "south_" + uuid4().hex[:12]
    with psycopg.connect(clean_database.dsn) as connection:
        _insert_account(connection, username, password, area)
        north_contact, north_phone = _insert_contact(
            connection, clean_database, area, "north remark"
        )
        south_contact, _ = _insert_contact(
            connection, clean_database, other_area, "south remark"
        )
        connection.commit()

    app = create_app(Settings(clean_database.dsn, "registration-secret", "business-secret"))
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _login(client, username, password)
        response = client.get(
            "/api/v1/contacts",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    contacts = response.json()
    assert [item["id"] for item in contacts] == [north_contact]
    assert contacts[0]["phoneNumber"] == north_phone
    assert contacts[0]["remark"] == "north remark"
    assert contacts[0]["areas"] == area
    assert south_contact not in [item["id"] for item in contacts]


def test_agent_can_update_matching_contact_remark(clean_database):
    username = "remark_contact_" + uuid4().hex
    password = "correct-password"
    area = "north_" + uuid4().hex[:12]
    with psycopg.connect(clean_database.dsn) as connection:
        _insert_account(connection, username, password, area)
        contact_id, _ = _insert_contact(connection, clean_database, area, None)
        connection.commit()

    app = create_app(Settings(clean_database.dsn, "registration-secret", "business-secret"))
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _login(client, username, password)
        response = client.patch(
            f"/api/v1/contacts/{contact_id}/remark",
            headers={"Authorization": f"Bearer {token}"},
            json={"remark": "VIP customer"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    with psycopg.connect(clean_database.dsn) as connection:
        remark = connection.execute(
            "SELECT remark FROM contacts WHERE id = %s",
            (contact_id,),
        ).fetchone()[0]
    assert remark == "VIP customer"


def test_agent_can_clear_matching_contact_remark(clean_database):
    username = "clear_contact_" + uuid4().hex
    password = "correct-password"
    area = "north_" + uuid4().hex[:12]
    with psycopg.connect(clean_database.dsn) as connection:
        _insert_account(connection, username, password, area)
        contact_id, _ = _insert_contact(
            connection, clean_database, area, "old remark"
        )
        connection.commit()

    app = create_app(Settings(clean_database.dsn, "registration-secret", "business-secret"))
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _login(client, username, password)
        response = client.patch(
            f"/api/v1/contacts/{contact_id}/remark",
            headers={"Authorization": f"Bearer {token}"},
            json={"remark": "   "},
        )

    assert response.status_code == 200
    with psycopg.connect(clean_database.dsn) as connection:
        remark = connection.execute(
            "SELECT remark FROM contacts WHERE id = %s",
            (contact_id,),
        ).fetchone()[0]
    assert remark is None


def test_agent_contact_remark_rejects_cross_area_access(clean_database):
    username = "cross_contact_" + uuid4().hex
    password = "correct-password"
    area = "north_" + uuid4().hex[:12]
    other_area = "south_" + uuid4().hex[:12]
    with psycopg.connect(clean_database.dsn) as connection:
        _insert_account(connection, username, password, area)
        contact_id, _ = _insert_contact(
            connection, clean_database, other_area, "south remark"
        )
        connection.commit()

    app = create_app(Settings(clean_database.dsn, "registration-secret", "business-secret"))
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _login(client, username, password)
        response = client.patch(
            f"/api/v1/contacts/{contact_id}/remark",
            headers={"Authorization": f"Bearer {token}"},
            json={"remark": "not allowed"},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_agent_menu_list_returns_only_matching_non_empty_area_menus(clean_database):
    username = "menu_contact_" + uuid4().hex
    password = "correct-password"
    area = "north_" + uuid4().hex[:12]
    other_area = "south_" + uuid4().hex[:12]
    north_id = "prod_" + uuid4().hex
    south_id = "prod_" + uuid4().hex
    blank_id = "prod_" + uuid4().hex
    with psycopg.connect(clean_database.dsn) as connection:
        _insert_account(connection, username, password, area)
        connection.execute(
            """
            INSERT INTO products(id, menu, update_time, areas)
            VALUES(%s, %s, %s, %s)
            """,
            (north_id, "north script", 1_800_000_000_003, area),
        )
        connection.execute(
            """
            INSERT INTO products(id, menu, update_time, areas)
            VALUES(%s, %s, %s, %s)
            """,
            (south_id, "south script", 1_800_000_000_002, other_area),
        )
        connection.execute(
            """
            INSERT INTO products(id, menu, update_time, areas)
            VALUES(%s, %s, %s, %s)
            """,
            (blank_id, "   ", 1_800_000_000_001, area),
        )
        connection.commit()

    app = create_app(Settings(clean_database.dsn, "registration-secret", "business-secret"))
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _login(client, username, password)
        response = client.get(
            "/api/v1/menus",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": north_id,
            "menu": "north script",
            "updateTime": 1_800_000_000_003,
            "updateBy": None,
            "areas": area,
        }
    ]
