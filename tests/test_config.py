"""Tests for config.py credential loading."""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from gmail_reader.config import load_config


@patch("gmail_reader.config.Path.home")
@patch("gmail_reader.config.load_dotenv")
def test_load_config_success(mock_load_dotenv, mock_home):
    """Test successful config loading with all required env vars."""
    mock_home.return_value = Path("/fake/home")

    valid_client_id = "123456789-abcdef.apps.googleusercontent.com"

    with patch.dict(
        os.environ,
        {
            "GMAIL_CLIENT_ID": valid_client_id,
            "GMAIL_CLIENT_SECRET": "test-client-secret",
            "GMAIL_REFRESH_TOKEN": "test-refresh-token",
        },
    ):
        with patch("gmail_reader.config.Path.exists", return_value=True):
            config = load_config()

            assert config["client_id"] == valid_client_id
            assert config["client_secret"] == "test-client-secret"
            assert config["refresh_token"] == "test-refresh-token"


@patch("gmail_reader.config.Path.home")
def test_load_config_missing_env_file(mock_home):
    """Test that FileNotFoundError is raised if ~/.env doesn't exist."""
    mock_home.return_value = Path("/fake/home")

    with patch("gmail_reader.config.Path.exists", return_value=False):
        with pytest.raises(FileNotFoundError) as exc_info:
            load_config()

        assert "Credentials file not found" in str(exc_info.value)
        assert ".env" in str(exc_info.value)


@patch("gmail_reader.config.Path.home")
@patch("gmail_reader.config.load_dotenv")
def test_load_config_missing_client_id(mock_load_dotenv, mock_home):
    """Test that EnvironmentError is raised if GMAIL_CLIENT_ID is missing."""
    mock_home.return_value = Path("/fake/home")

    with patch.dict(
        os.environ,
        {
            "GMAIL_CLIENT_SECRET": "test-client-secret",
        },
        clear=True,
    ):
        with patch("gmail_reader.config.Path.exists", return_value=True):
            with pytest.raises(EnvironmentError) as exc_info:
                load_config()

            assert "Missing required environment variables" in str(exc_info.value)
            assert "GMAIL_CLIENT_ID" in str(exc_info.value)


@patch("gmail_reader.config.Path.home")
@patch("gmail_reader.config.load_dotenv")
def test_load_config_missing_client_secret(mock_load_dotenv, mock_home):
    """Test that EnvironmentError is raised if GMAIL_CLIENT_SECRET is missing."""
    mock_home.return_value = Path("/fake/home")

    with patch.dict(
        os.environ,
        {
            "GMAIL_CLIENT_ID": "test-client-id",
        },
        clear=True,
    ):
        with patch("gmail_reader.config.Path.exists", return_value=True):
            with pytest.raises(EnvironmentError) as exc_info:
                load_config()

            assert "Missing required environment variables" in str(exc_info.value)
            assert "GMAIL_CLIENT_SECRET" in str(exc_info.value)


@patch("gmail_reader.config.Path.home")
@patch("gmail_reader.config.load_dotenv")
def test_load_config_missing_refresh_token_ok(mock_load_dotenv, mock_home):
    """Test that missing GMAIL_REFRESH_TOKEN is OK (for initial auth setup)."""
    mock_home.return_value = Path("/fake/home")

    valid_client_id = "123456789-abcdef.apps.googleusercontent.com"

    with patch.dict(
        os.environ,
        {
            "GMAIL_CLIENT_ID": valid_client_id,
            "GMAIL_CLIENT_SECRET": "test-client-secret",
        },
        clear=True,
    ):
        with patch("gmail_reader.config.Path.exists", return_value=True):
            config = load_config()

            assert config["client_id"] == valid_client_id
            assert config["client_secret"] == "test-client-secret"
            assert config["refresh_token"] is None  # Should be None, not raise


@patch("gmail_reader.config.Path.home")
@patch("gmail_reader.config.load_dotenv")
def test_load_config_malformed_client_id(mock_load_dotenv, mock_home):
    """Test that EnvironmentError is raised for malformed GMAIL_CLIENT_ID (MEDIUM #13)."""
    mock_home.return_value = Path("/fake/home")

    with patch.dict(
        os.environ,
        {
            "GMAIL_CLIENT_ID": "not-a-valid-google-client-id",
            "GMAIL_CLIENT_SECRET": "test-client-secret",
        },
        clear=True,
    ):
        with patch("gmail_reader.config.Path.exists", return_value=True):
            with pytest.raises(EnvironmentError) as exc_info:
                load_config()

            assert "malformed" in str(exc_info.value)
            assert "apps.googleusercontent.com" in str(exc_info.value)
