from collections.abc import Callable
from dataclasses import dataclass
import time
from typing import Any

from psycopg.rows import dict_row

from app.database import Database
from app.security import hash_password


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


@dataclass(frozen=True, slots=True)
class TableDefinition:
    name: str
    columns: tuple[str, ...]
    order_by: str


@dataclass(frozen=True, slots=True)
class ProductCreate:
    id: str
    menu: str | None = None
    update_by: str | None = None
    areas: str | None = None


@dataclass(frozen=True, slots=True)
class ProductUpdate:
    menu: str | None = None
    update_by: str | None = None
    areas: str | None = None


@dataclass(frozen=True, slots=True)
class AccountCreate:
    id: str
    username: str
    password: str
    areas: str | None = None
    use_sims_id: str | None = None
    status: str = "ACTIVE"


@dataclass(frozen=True, slots=True)
class AccountUpdate:
    username: str
    password: str | None = None
    areas: str | None = None
    use_sims_id: str | None = None
    status: str = "ACTIVE"


@dataclass(frozen=True, slots=True)
class SimCardUpdate:
    sim_type: str = "PHYSICAL"
    subscription_id: int | None = None
    phone_number: str | None = None
    carrier_name: str | None = None
    iccid_hash: str | None = None
    esim_profile_name: str | None = None
    esim_group_id: str | None = None
    enabled: bool = True
    status: str = "active"
    areas: str | None = None


TABLES: dict[str, TableDefinition] = {
    "devices": TableDefinition(
        name="devices",
        columns=(
            "id",
            "name",
            "manufacturer",
            "model",
            "android_version",
            "app_version",
            "enabled",
            "status",
            "last_seen_at",
            "registered",
            "created_at",
            "updated_at",
        ),
        order_by="updated_at DESC",
    ),
    "sim_cards": TableDefinition(
        name="sim_cards",
        columns=(
            "id",
            "device_id",
            "sim_type",
            "slot_index",
            "sim_number",
            "subscription_id",
            "phone_number",
            "carrier_name",
            "iccid_hash",
            "esim_profile_name",
            "esim_group_id",
            "enabled",
            "status",
            "last_used_at",
            "created_at",
            "updated_at",
            "areas",
        ),
        order_by="updated_at DESC",
    ),
    "contacts": TableDefinition(
        name="contacts",
        columns=(
            "id",
            "display_name",
            "phone_number",
            "normalized_phone_number",
            "avatar_url",
            "remark",
            "status",
            "source",
            "last_contact_at",
            "created_at",
            "updated_at",
            "areas",
        ),
        order_by="updated_at DESC",
    ),
    "products": TableDefinition(
        name="products",
        columns=("id", "menu", "update_time", "update_by", "areas"),
        order_by="update_time DESC",
    ),
    "accounts": TableDefinition(
        name="accounts",
        columns=("id", "username", "areas", "use_sims_id", "status"),
        order_by="username ASC",
    ),
}


class PgAdminService:
    def __init__(
        self,
        database: Database,
        now_ms: Callable[[], int] = _now_ms,
        password_hasher: Callable[[str], str] = hash_password,
    ):
        self._database = database
        self._now_ms = now_ms
        self._password_hasher = password_hasher

    def list_rows(self, table_name: str, limit: int = 200) -> list[dict[str, Any]]:
        table = TABLES.get(table_name)
        if table is None:
            raise ValueError(f"Unsupported admin table: {table_name}")
        safe_limit = self._coerce_limit(limit)
        columns = ", ".join(table.columns)
        statement = (
            f"SELECT {columns} FROM {table.name} "
            f"ORDER BY {table.order_by} LIMIT %s"
        )
        with self._database.transaction() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(statement, (safe_limit,))
                return [dict(row) for row in cursor.fetchall()]

    def create_product(self, data: ProductCreate) -> None:
        self._execute(
            """
            INSERT INTO products (id, menu, update_time, update_by, areas)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                data.id.strip(),
                data.menu,
                self._now_ms(),
                _blank_to_none(data.update_by),
                _blank_to_none(data.areas),
            ),
        )

    def update_product(self, product_id: str, data: ProductUpdate) -> None:
        self._execute(
            """
            UPDATE products
            SET menu = %s, update_time = %s, update_by = %s, areas = %s
            WHERE id = %s
            """,
            (
                data.menu,
                self._now_ms(),
                _blank_to_none(data.update_by),
                _blank_to_none(data.areas),
                product_id,
            ),
        )

    def delete_product(self, product_id: str) -> None:
        self._execute("DELETE FROM products WHERE id = %s", (product_id,))

    def create_account(self, data: AccountCreate) -> None:
        self._execute(
            """
            INSERT INTO accounts (
                id, username, password_hash, areas, use_sims_id, status
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                data.id.strip(),
                data.username.strip(),
                self._password_hasher(data.password),
                _blank_to_none(data.areas),
                _blank_to_none(data.use_sims_id),
                data.status,
            ),
        )

    def update_account(self, account_id: str, data: AccountUpdate) -> None:
        password = _blank_to_none(data.password)
        if password is None:
            self._execute(
                """
                UPDATE accounts
                SET username = %s, areas = %s, use_sims_id = %s, status = %s
                WHERE id = %s
                """,
                (
                    data.username.strip(),
                    _blank_to_none(data.areas),
                    _blank_to_none(data.use_sims_id),
                    data.status,
                    account_id,
                ),
            )
            return

        self._execute(
            """
            UPDATE accounts
            SET username = %s, password_hash = %s,
                areas = %s, use_sims_id = %s, status = %s
            WHERE id = %s
            """,
            (
                data.username.strip(),
                self._password_hasher(password),
                _blank_to_none(data.areas),
                _blank_to_none(data.use_sims_id),
                data.status,
                account_id,
            ),
        )

    def delete_account(self, account_id: str) -> None:
        self._execute("DELETE FROM accounts WHERE id = %s", (account_id,))

    def update_sim_card(self, sim_card_id: str, data: SimCardUpdate) -> None:
        self._execute(
            """
            UPDATE sim_cards
            SET sim_type = %s, subscription_id = %s, phone_number = %s,
                carrier_name = %s, iccid_hash = %s, esim_profile_name = %s,
                esim_group_id = %s, enabled = %s, status = %s, areas = %s,
                updated_at = %s
            WHERE id = %s
            """,
            (
                data.sim_type,
                data.subscription_id,
                _blank_to_none(data.phone_number),
                _blank_to_none(data.carrier_name),
                _blank_to_none(data.iccid_hash),
                _blank_to_none(data.esim_profile_name),
                _blank_to_none(data.esim_group_id),
                data.enabled,
                data.status,
                _blank_to_none(data.areas),
                self._now_ms(),
                sim_card_id,
            ),
        )

    def _execute(self, statement: str, params: tuple[Any, ...]) -> None:
        with self._database.transaction() as connection:
            connection.execute(statement, params)

    def _coerce_limit(self, limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int):
            return 200
        if limit <= 0:
            return 200
        return min(limit, 500)
