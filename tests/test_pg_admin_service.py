from contextlib import contextmanager

from pg.admin_service import (
    AccountCreate,
    AccountUpdate,
    PgAdminService,
    ProductCreate,
    ProductUpdate,
    SimCardUpdate,
)


class RecordingCursor:
    def __init__(self, database):
        self._database = database

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement, params=()):
        self._database.statements.append(" ".join(statement.split()))
        self._database.params.append(params)
        return self

    def fetchall(self):
        return self._database.rows


class RecordingConnection:
    def __init__(self, database):
        self._database = database

    def cursor(self, **_kwargs):
        return RecordingCursor(self._database)

    def execute(self, statement, params=()):
        return self.cursor().execute(statement, params)


class RecordingDatabase:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.statements = []
        self.params = []

    @contextmanager
    def transaction(self):
        yield RecordingConnection(self)


def test_list_rows_uses_allowed_columns_and_hides_password_hash():
    database = RecordingDatabase(rows=[{"id": "acc_1", "username": "alice"}])
    service = PgAdminService(database)

    rows = service.list_rows("accounts")

    assert rows == [{"id": "acc_1", "username": "alice"}]
    assert "FROM accounts" in database.statements[0]
    assert "password_hash" not in database.statements[0]
    assert database.params[0] == (200,)


def test_list_rows_rejects_unknown_table_name():
    service = PgAdminService(RecordingDatabase())

    try:
        service.list_rows("messages")
    except ValueError as error:
        assert str(error) == "Unsupported admin table: messages"
    else:
        raise AssertionError("unknown table name was accepted")


def test_create_product_sets_update_time():
    database = RecordingDatabase()
    service = PgAdminService(database, now_ms=lambda: 123456)

    service.create_product(
        ProductCreate(
            id="prod_1",
            menu="remind support",
            update_by="acc_1",
            areas="CN",
        )
    )

    assert "INSERT INTO products" in database.statements[0]
    assert database.params[0] == (
        "prod_1",
        "remind support",
        123456,
        "acc_1",
        "CN",
    )


def test_update_product_keeps_id_and_refreshes_update_time():
    database = RecordingDatabase()
    service = PgAdminService(database, now_ms=lambda: 234567)

    service.update_product(
        "prod_1",
        ProductUpdate(menu="new reminder", update_by=None, areas="US"),
    )

    statement = database.statements[0]
    assert "UPDATE products" in statement
    assert "id =" not in statement.partition("SET")[2].partition("WHERE")[0]
    assert database.params[0] == ("new reminder", 234567, None, "US", "prod_1")


def test_delete_product_removes_by_id():
    database = RecordingDatabase()
    service = PgAdminService(database)

    service.delete_product("prod_1")

    assert database.statements[0] == "DELETE FROM products WHERE id = %s"
    assert database.params[0] == ("prod_1",)


def test_create_account_hashes_password():
    database = RecordingDatabase()
    service = PgAdminService(database)

    service.create_account(
        AccountCreate(
            id="acc_1",
            username="alice",
            password="secret",
            areas="CN",
            use_sims_id="sim_1",
            status="ACTIVE",
        )
    )

    assert "INSERT INTO accounts" in database.statements[0]
    params = database.params[0]
    assert params[0] == "acc_1"
    assert params[1] == "alice"
    assert params[2].startswith("pbkdf2_sha256$")
    assert params[2] != "secret"
    assert params[3:] == ("CN", "sim_1", "ACTIVE")


def test_update_account_without_password_does_not_touch_password_hash():
    database = RecordingDatabase()
    service = PgAdminService(database)

    service.update_account(
        "acc_1",
        AccountUpdate(
            username="alice",
            password="",
            areas="CN",
            use_sims_id=None,
            status="DISABLED",
        ),
    )

    statement = database.statements[0]
    assert "UPDATE accounts" in statement
    assert "password_hash" not in statement
    assert database.params[0] == ("alice", "CN", None, "DISABLED", "acc_1")


def test_update_account_with_password_updates_password_hash():
    database = RecordingDatabase()
    service = PgAdminService(database)

    service.update_account(
        "acc_1",
        AccountUpdate(
            username="alice",
            password="new-secret",
            areas="CN",
            use_sims_id="sim_1",
            status="ACTIVE",
        ),
    )

    statement = database.statements[0]
    assert "password_hash = %s" in statement
    params = database.params[0]
    assert params[0] == "alice"
    assert params[1].startswith("pbkdf2_sha256$")
    assert params[1] != "new-secret"
    assert params[2:] == ("CN", "sim_1", "ACTIVE", "acc_1")


def test_delete_account_removes_by_id():
    database = RecordingDatabase()
    service = PgAdminService(database)

    service.delete_account("acc_1")

    assert database.statements[0] == "DELETE FROM accounts WHERE id = %s"
    assert database.params[0] == ("acc_1",)


def test_update_sim_card_changes_only_allowed_fields_and_refreshes_updated_at():
    database = RecordingDatabase()
    service = PgAdminService(database, now_ms=lambda: 345678)

    service.update_sim_card(
        "sim_1",
        SimCardUpdate(
            sim_type="ESIM",
            subscription_id=42,
            phone_number="+8613800000000",
            carrier_name="Carrier",
            iccid_hash="hash",
            esim_profile_name="Work",
            esim_group_id="group",
            enabled=False,
            status="disabled",
            areas="CN",
        ),
    )

    statement = database.statements[0]
    changed_columns = statement.partition("SET")[2].partition("WHERE")[0]
    updated_names = {
        assignment.strip().split(" = ", 1)[0]
        for assignment in changed_columns.split(",")
    }
    assert "UPDATE sim_cards" in statement
    assert "id" not in updated_names
    assert "device_id" not in updated_names
    assert "slot_index" not in updated_names
    assert "sim_number" not in updated_names
    assert "updated_at = %s" in changed_columns
    assert database.params[0] == (
        "ESIM",
        42,
        "+8613800000000",
        "Carrier",
        "hash",
        "Work",
        "group",
        False,
        "disabled",
        "CN",
        345678,
        "sim_1",
    )
