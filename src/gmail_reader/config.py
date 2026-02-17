import os
from pathlib import Path

from dotenv import load_dotenv

# Tunable constants with environment variable overrides.
# Gmail API quota: 250 units/user/second. Default 25 req/sec = 125 units/sec (50% of limit).
GMAIL_RATE_LIMIT_RPS = max(1, int(os.getenv("GMAIL_RATE_LIMIT_RPS", "25")))
GMAIL_MAX_RETRIES = int(os.getenv("GMAIL_MAX_RETRIES", "3"))
GMAIL_RETRY_BASE_WAIT = float(os.getenv("GMAIL_RETRY_BASE_WAIT", "2.0"))
MAX_PAGES = int(os.getenv("GMAIL_MAX_PAGES", "1000"))
MAX_MESSAGES_IN_MEMORY = int(os.getenv("GMAIL_MAX_MESSAGES_IN_MEMORY", "10000"))
MCP_EXPORT_LIMIT = int(os.getenv("GMAIL_MCP_EXPORT_LIMIT", "100"))
MAX_MIME_DEPTH = int(os.getenv("GMAIL_MAX_MIME_DEPTH", "50"))
SNIPPET_MAX_LENGTH = int(os.getenv("GMAIL_SNIPPET_MAX_LENGTH", "150"))
MAX_QUERY_LENGTH = int(os.getenv("GMAIL_MAX_QUERY_LENGTH", "2000"))


def load_config() -> dict:
    """Load Gmail OAuth credentials from ~/.env and return a config dict.

    Returns:
        dict with keys: client_id, client_secret, refresh_token

    Raises:
        FileNotFoundError: If ~/.env doesn't exist
        EnvironmentError: If required environment variables are missing
    """
    env_path = Path.home() / ".env"
    if not env_path.exists():
        raise FileNotFoundError(
            f"Credentials file not found at {env_path}. "
            "Create ~/.env with GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, "
            "and GMAIL_REFRESH_TOKEN (run 'gmail-reader auth' to obtain refresh token)."
        )

    load_dotenv(dotenv_path=env_path, override=True)

    required_vars = [
        "GMAIL_CLIENT_ID",
        "GMAIL_CLIENT_SECRET",
    ]
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables in ~/.env: {', '.join(missing)}"
        )

    client_id = os.getenv("GMAIL_CLIENT_ID")

    # Validate client_id format early to give a clear error
    # before it manifests as a cryptic OAuth failure later.
    if client_id and not client_id.endswith(".apps.googleusercontent.com"):
        raise EnvironmentError(
            f"GMAIL_CLIENT_ID appears to be malformed: '{client_id}'\n"
            "A valid Google OAuth 2.0 client ID ends with '.apps.googleusercontent.com'.\n"
            "Please check your credentials in Google Cloud Console > APIs & Services > Credentials."
        )

    # GMAIL_REFRESH_TOKEN is optional during initial auth setup
    refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")

    return {
        "client_id": client_id,
        "client_secret": os.getenv("GMAIL_CLIENT_SECRET"),
        "refresh_token": refresh_token,
    }
