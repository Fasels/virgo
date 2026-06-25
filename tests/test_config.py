from pathlib import Path

import pytest

from app.config import Settings


VALID_CONFIG = (
    'private_registration_token = "registration-secret"\n'
    'business_api_token = "business-secret"\n'
    'device_online_window_seconds = 300\n'
)


def test_settings_reads_environment_and_config_file(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://db/example")
    monkeypatch.setenv("VIRGO_CONFIG_FILE", "chosen-config.toml")
    read_paths = []

    def read_text(path, encoding):
        read_paths.append((path, encoding))
        return VALID_CONFIG

    monkeypatch.setattr(Path, "read_text", read_text)

    settings = Settings.from_env()

    assert settings.database_url == "postgresql://db/example"
    assert settings.private_registration_token == "registration-secret"
    assert settings.business_api_token == "business-secret"
    assert settings.device_online_window_seconds == 300
    assert read_paths == [(Path("chosen-config.toml"), "utf-8")]


@pytest.mark.parametrize("invalid_value", ["", " \t "])
def test_settings_rejects_empty_or_whitespace_database_url(monkeypatch, invalid_value):
    monkeypatch.setenv("DATABASE_URL", invalid_value)
    monkeypatch.setenv("VIRGO_CONFIG_FILE", "config.toml")
    monkeypatch.setattr(Path, "read_text", lambda self, encoding: VALID_CONFIG)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        Settings.from_env()


def test_settings_rejects_missing_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("VIRGO_CONFIG_FILE", "config.toml")
    monkeypatch.setattr(Path, "read_text", lambda self, encoding: VALID_CONFIG)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        Settings.from_env()


@pytest.mark.parametrize(
    "contents,match",
    [
        (
            'business_api_token = "business-secret"\n'
            'device_online_window_seconds = 300\n',
            "private_registration_token",
        ),
        (
            'private_registration_token = "   "\n'
            'business_api_token = "business-secret"\n'
            'device_online_window_seconds = 300\n',
            "private_registration_token",
        ),
        (
            'private_registration_token = "registration-secret"\n'
            'device_online_window_seconds = 300\n',
            "business_api_token",
        ),
        (
            'private_registration_token = "registration-secret"\n'
            'business_api_token = "   "\n'
            'device_online_window_seconds = 300\n',
            "business_api_token",
        ),
        (
            'private_registration_token = "registration-secret"\n'
            'business_api_token = "business-secret"\n'
            'device_online_window_seconds = 0\n',
            "device_online_window_seconds",
        ),
        (
            'private_registration_token = "registration-secret"\n'
            'business_api_token = "business-secret"\n'
            'device_online_window_seconds = true\n',
            "device_online_window_seconds",
        ),
    ],
)
def test_settings_rejects_invalid_config(monkeypatch, contents, match):
    monkeypatch.setenv("DATABASE_URL", "postgresql://db/example")
    monkeypatch.setenv("VIRGO_CONFIG_FILE", "invalid-config.toml")
    monkeypatch.setattr(Path, "read_text", lambda self, encoding: contents)

    with pytest.raises(RuntimeError, match=match):
        Settings.from_env()


def test_settings_rejects_missing_config_file(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://db/example")
    monkeypatch.setenv("VIRGO_CONFIG_FILE", "missing.toml")

    def missing_file(self, encoding):
        raise FileNotFoundError(self)

    monkeypatch.setattr(Path, "read_text", missing_file)

    with pytest.raises(RuntimeError, match="VIRGO_CONFIG_FILE"):
        Settings.from_env()
