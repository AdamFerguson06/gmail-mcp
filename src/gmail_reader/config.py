import os
from pathlib import Path

from dotenv import load_dotenv


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

    # GMAIL_REFRESH_TOKEN is optional during initial auth setup
    refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")

    return {
        "client_id": os.getenv("GMAIL_CLIENT_ID"),
        "client_secret": os.getenv("GMAIL_CLIENT_SECRET"),
        "refresh_token": refresh_token,
    }
