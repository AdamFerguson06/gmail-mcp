"""Gmail API client with rate limiting."""

import sys
import threading
import time

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from gmail_reader.auth import get_credentials

# Gmail API quota: 250 units/user/second
# List operation: 5 units, Get operation: 5 units
# Conservative default: 10 requests/sec (50 units/sec, 20% of limit)
# This can be tuned up to ~40 req/sec if needed
_RATE_LIMIT_RPS = 10
_MIN_REQUEST_INTERVAL = 1.0 / _RATE_LIMIT_RPS  # 0.1 seconds

# Thread-safe rate limiting using a lock
_last_request_time = 0.0
_rate_limit_lock = threading.Lock()

# Exponential backoff settings for 429 retry
_MAX_RETRIES = 3
_RETRY_BASE_WAIT = 10  # seconds (10, 20, 40)


def get_gmail_service():
    """Build Gmail API service from ~/.env credentials.

    Returns:
        googleapiclient.discovery.Resource: Gmail API service object

    Raises:
        EnvironmentError: If credentials are missing or invalid
    """
    creds = get_credentials()
    return build("gmail", "v1", credentials=creds)


def execute_gmail_request(service, request_callable):
    """Execute Gmail API request with rate limiting.

    Includes thread-safe rate limiting (10 req/sec by default) and automatic
    retry with exponential backoff on 429 (rate limit exceeded) errors.

    Args:
        service: Gmail API service object (not used, kept for consistency)
        request_callable: Lambda that returns API request
                         e.g., lambda: service.users().messages().list(...).execute()

    Returns:
        dict: API response

    Raises:
        HttpError: For non-429 HTTP errors, or 429 after max retries exceeded
    """
    global _last_request_time

    # Thread-safe rate limiting: acquire lock to prevent concurrent calls
    # from bursting past the rate limit.
    with _rate_limit_lock:
        elapsed = time.time() - _last_request_time
        if elapsed < _MIN_REQUEST_INTERVAL:
            time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
        _last_request_time = time.time()

    # Exponential backoff retry for 429 errors
    last_error = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return request_callable()
        except HttpError as error:
            if error.resp.status == 429:
                if attempt < _MAX_RETRIES:
                    wait_time = _RETRY_BASE_WAIT * (2 ** attempt)  # 10, 20, 40 seconds
                    print(
                        f"Rate limit exceeded, waiting {wait_time}s before retry "
                        f"(attempt {attempt + 1}/{_MAX_RETRIES})...",
                        file=sys.stderr,
                    )
                    time.sleep(wait_time)
                    last_error = error
                else:
                    print(
                        f"Rate limit exceeded after {_MAX_RETRIES} retries. Giving up.",
                        file=sys.stderr,
                    )
                    raise
            else:
                # Other HTTP errors - re-raise immediately
                print(
                    f"Gmail API error: {error.error_details if hasattr(error, 'error_details') else error}",
                    file=sys.stderr,
                )
                raise

    # Should not reach here, but re-raise last error as a safety net
    raise last_error  # type: ignore[misc]
