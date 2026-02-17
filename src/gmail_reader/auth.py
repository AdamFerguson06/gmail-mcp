"""OAuth 2.0 authentication flow for Gmail API.

CRITICAL SECURITY: Only gmail.readonly scope is used.
This prevents sending, modifying, or deleting emails.
"""

import fcntl
import sys
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from gmail_reader.config import load_config

# CRITICAL: Read-only scope ONLY. Never add gmail.send, gmail.modify, etc.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def run_oauth_flow() -> None:
    """Run interactive OAuth 2.0 flow and save refresh token to ~/.env.

    This should only be run once for initial setup.

    Flow:
    1. Check if GMAIL_CLIENT_ID/SECRET are in ~/.env
    2. Start local server on localhost:8080 for OAuth redirect
    3. Open browser to Google consent screen
    4. Exchange authorization code for access + refresh tokens
    5. Append GMAIL_REFRESH_TOKEN to ~/.env
    6. Print success message

    Raises:
        EnvironmentError: If GMAIL_CLIENT_ID or GMAIL_CLIENT_SECRET are missing
    """
    print("Starting Gmail OAuth 2.0 authentication flow...")

    try:
        config = load_config()
    except (FileNotFoundError, EnvironmentError) as e:
        print(f"Error: {e}", file=sys.stderr)
        print(
            "\nPlease add GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET to ~/.env first.",
            file=sys.stderr,
        )
        print(
            "You can obtain these from Google Cloud Console > APIs & Services > Credentials.",
            file=sys.stderr,
        )
        sys.exit(1)

    client_id = config["client_id"]
    client_secret = config["client_secret"]

    # Build client config for InstalledAppFlow
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8080/"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

    print("\nOpening browser for Google authentication...")
    print("Please grant permission for read-only Gmail access.")

    # If port 8080 is in use, fall back to OS-assigned port (port=0)
    try:
        creds = flow.run_local_server(port=8080)
    except OSError:
        print(
            "Warning: Port 8080 is in use. Falling back to OS-assigned port.",
            file=sys.stderr,
        )
        creds = flow.run_local_server(port=0)

    # Save refresh token to ~/.env
    refresh_token = creds.refresh_token
    if not refresh_token:
        print(
            "Error: No refresh token received. Your OAuth client may not support refresh tokens.",
            file=sys.stderr,
        )
        sys.exit(1)

    _append_refresh_token_to_env(refresh_token)

    print("\n✅ Authentication successful!")
    print(f"Refresh token saved to {Path.home() / '.env'}")
    print("\nYou can now use 'gmail-reader list', 'gmail-reader search', etc.")


def get_credentials() -> Credentials:
    """Load refresh token from ~/.env and return Credentials object.

    Returns:
        google.oauth2.credentials.Credentials for Gmail API

    Raises:
        EnvironmentError: If GMAIL_REFRESH_TOKEN is missing from ~/.env
    """
    config = load_config()

    if not config["refresh_token"]:
        raise EnvironmentError(
            "GMAIL_REFRESH_TOKEN not found in ~/.env. "
            "Run 'gmail-reader auth' to authenticate."
        )

    creds = Credentials(
        token=None,  # Access token will be auto-refreshed
        refresh_token=config["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config["client_id"],
        client_secret=config["client_secret"],
        scopes=SCOPES,
    )

    # Refresh access token if needed
    if not creds.valid:
        if creds.refresh_token:
            # Credentials object created from refresh token needs initial refresh
            try:
                creds.refresh(Request())
            except RefreshError as e:
                # Provide actionable error message when refresh token is revoked
                raise EnvironmentError(
                    f"OAuth refresh token is invalid or has been revoked: {e}\n"
                    "This can happen if you changed your Google password, revoked app access, "
                    "or if the token expired.\n"
                    "Run 'gmail-reader auth' to re-authenticate and obtain a new refresh token."
                ) from e
        else:
            raise EnvironmentError(
                "Credentials invalid. Run 'gmail-reader auth' to re-authenticate."
            )

    return creds


def _append_refresh_token_to_env(refresh_token: str) -> None:
    """Safely append or update GMAIL_REFRESH_TOKEN in ~/.env.

    Uses fcntl.flock() exclusive lock to prevent concurrent
    'gmail-reader auth' processes from clobbering each other's refresh token.

    Args:
        refresh_token: OAuth refresh token to save

    Handles both new append (if GMAIL_REFRESH_TOKEN doesn't exist)
    and updating existing value.
    """
    env_path = Path.home() / ".env"

    # Open (or create) the .env file and acquire an exclusive lock
    # before reading/writing to prevent race conditions with concurrent auth runs.
    with env_path.open("a+") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            # Re-read content under lock to get the current state
            lock_file.seek(0)
            content = lock_file.read()

            if "GMAIL_REFRESH_TOKEN" in content:
                # Update existing token in-place
                lines = content.splitlines()
                updated = []
                for line in lines:
                    if line.startswith("GMAIL_REFRESH_TOKEN="):
                        updated.append(f"GMAIL_REFRESH_TOKEN={refresh_token}")
                    else:
                        updated.append(line)
                new_content = "\n".join(updated) + "\n"
                lock_file.seek(0)
                lock_file.truncate()
                lock_file.write(new_content)
            else:
                # Append new token
                lock_file.write(f"\nGMAIL_REFRESH_TOKEN={refresh_token}\n")
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
