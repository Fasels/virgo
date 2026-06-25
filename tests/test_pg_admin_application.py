from datetime import timezone

from app.application import create_app
from app.config import Settings
from pg.admin_ui import (
    _format_table_rows_for_display,
    _patch_nicegui_process_pool_setup,
)


class RecordingDatabase:
    def __init__(self, dsn):
        self.dsn = dsn


def test_create_app_mounts_pg_admin_ui_with_configured_database(monkeypatch):
    mounted = {}

    def fake_mount_admin_ui(app, database):
        mounted["app"] = app
        mounted["database"] = database

    monkeypatch.setattr("app.application.Database", RecordingDatabase)
    monkeypatch.setattr(
        "app.application.mount_admin_ui",
        fake_mount_admin_ui,
        raising=False,
    )

    app = create_app(Settings("postgresql://configured/database", "registration-token"))

    assert mounted["app"] is app
    assert isinstance(mounted["database"], RecordingDatabase)
    assert mounted["database"].dsn == "postgresql://configured/database"


def test_nicegui_process_pool_setup_degrades_on_permission_error():
    class FakeNiceGuiRun:
        process_pool = object()

        @staticmethod
        def setup():
            raise PermissionError("named pipe denied")

    _patch_nicegui_process_pool_setup(FakeNiceGuiRun)

    FakeNiceGuiRun.setup()

    assert FakeNiceGuiRun.process_pool is None


def test_table_rows_format_unix_millisecond_time_fields():
    rows = [
        {
            "id": "dev_1",
            "created_at": 0,
            "updated_at": 1000,
            "last_seen_at": None,
            "name": "phone",
        }
    ]

    formatted = _format_table_rows_for_display(rows, timezone.utc)

    assert formatted == [
        {
            "id": "dev_1",
            "created_at": "1970-01-01 00:00:00",
            "updated_at": "1970-01-01 00:00:01",
            "last_seen_at": None,
            "name": "phone",
        }
    ]
    assert rows[0]["created_at"] == 0
