"""Gmail API client with rate limiting and retry logic."""

import logging
import threading
import time

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from gmail_reader.auth import get_credentials
from gmail_reader.config import (
    GMAIL_MAX_RETRIES,
    GMAIL_RATE_LIMIT_RPS,
    GMAIL_RETRY_BASE_WAIT,
)

logger = logging.getLogger(__name__)

# HTTP status codes that are safe to retry (transient server errors)
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503}


class TokenBucketRateLimiter:
    """Token bucket rate limiter that allows short bursts while enforcing average rate.

    Unlike a fixed-interval limiter, this accumulates tokens over idle periods
    (up to `capacity`), allowing burst requests after quiet periods while still
    throttling sustained high-rate usage.
    """

    def __init__(self, rate: float, capacity: float | None = None):
        self.rate = rate
        self.capacity = capacity or rate
        self.tokens = self.capacity
        self.last_update = time.time()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        """Block until a token is available, then consume it."""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens < 1.0:
                sleep_time = (1.0 - self.tokens) / self.rate
                time.sleep(sleep_time)
                self.tokens = 0.0
            else:
                self.tokens -= 1.0


_rate_limiter = TokenBucketRateLimiter(rate=GMAIL_RATE_LIMIT_RPS)


def get_gmail_service():
    """Build Gmail API service from ~/.env credentials.

    Returns:
        googleapiclient.discovery.Resource: Gmail API service object

    Raises:
        EnvironmentError: If credentials are missing or invalid
    """
    creds = get_credentials()
    try:
        return build("gmail", "v1", credentials=creds)
    except Exception as e:
        raise EnvironmentError(
            f"Failed to initialize Gmail API client: {e}\n"
            "Check your network connection and credentials."
        ) from e


def execute_gmail_request(service, request_callable, operation_name: str = ""):
    """Execute Gmail API request with rate limiting and retry.

    Includes token-bucket rate limiting and automatic retry with exponential
    backoff on transient errors (429, 500, 502, 503).

    Args:
        service: Gmail API service object (kept for call-site consistency)
        request_callable: Callable that executes the API request,
            e.g., lambda: service.users().messages().list(...).execute()
        operation_name: Optional label for log messages (e.g. "list messages")

    Returns:
        dict: API response

    Raises:
        HttpError: For non-retryable HTTP errors, or after max retries exceeded
    """
    _rate_limiter.acquire()

    label = f" [{operation_name}]" if operation_name else ""
    last_error: HttpError | None = None

    for attempt in range(GMAIL_MAX_RETRIES + 1):
        try:
            return request_callable()
        except HttpError as error:
            status = error.resp.status
            if status in _RETRYABLE_STATUS_CODES and attempt < GMAIL_MAX_RETRIES:
                # Honor Retry-After header if present, otherwise exponential backoff
                retry_after = error.resp.get("retry-after")
                if retry_after:
                    try:
                        wait_time = float(retry_after)
                    except (ValueError, TypeError):
                        wait_time = GMAIL_RETRY_BASE_WAIT * (2 ** attempt)
                else:
                    wait_time = GMAIL_RETRY_BASE_WAIT * (2 ** attempt)

                logger.warning(
                    "HTTP %d%s, retrying in %.1fs (attempt %d/%d)",
                    status, label, wait_time, attempt + 1, GMAIL_MAX_RETRIES,
                )
                time.sleep(wait_time)
                last_error = error
            elif status in _RETRYABLE_STATUS_CODES:
                logger.error(
                    "HTTP %d%s after %d retries, giving up",
                    status, label, GMAIL_MAX_RETRIES,
                )
                raise
            else:
                logger.error("Gmail API error%s: %s", label, error)
                raise

    # Safety net: should not reach here, but re-raise last error if we do
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Unexpected retry loop exit{label}")
