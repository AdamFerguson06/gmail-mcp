"""Gmail API client with rate limiting."""

import sys
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

_last_request_time = 0.0


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

    Includes rate limiting (10 req/sec by default) and automatic retry
    on 429 (rate limit exceeded) errors.

    Args:
        service: Gmail API service object (not used, kept for consistency)
        request_callable: Lambda that returns API request
                         e.g., lambda: service.users().messages().list(...).execute()

    Returns:
        dict: API response

    Raises:
        HttpError: For non-429 HTTP errors
    """
    global _last_request_time

    # Rate limit: wait if we recently made a request
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)

    try:
        result = request_callable()
    except HttpError as error:
        if error.resp.status == 429:
            # Rate limit exceeded - wait and retry once
            print("Rate limit exceeded, waiting 10 seconds...", file=sys.stderr)
            time.sleep(10)
            result = request_callable()  # Retry once
        else:
            # Other HTTP errors - re-raise
            print(
                f"Gmail API error: {error.error_details if hasattr(error, 'error_details') else error}",
                file=sys.stderr,
            )
            raise
    finally:
        _last_request_time = time.time()

    return result
