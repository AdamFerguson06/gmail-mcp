"""Gmail API query constants and helper functions."""

import re

from gmail_reader.config import MAX_QUERY_LENGTH

# Gmail message/thread IDs are variable-length hex strings
_GMAIL_ID_PATTERN = re.compile(r"^[0-9a-f]+$", re.IGNORECASE)

# Message fields to request (partial response optimization)
# Reduces bandwidth and improves performance
MESSAGE_LIST_FIELDS = "messages(id,threadId,labelIds,snippet,internalDate)"
MESSAGE_DETAIL_FIELDS = "id,threadId,labelIds,snippet,payload,internalDate"
MESSAGE_FULL_FIELDS = (
    "id,threadId,labelIds,snippet,payload,internalDate,sizeEstimate"
)

# Thread fields
THREAD_FIELDS = "id,messages(id,labelIds,snippet,payload,internalDate)"

# Label fields
LABEL_FIELDS = "labels(id,name,type)"

# Default list parameters
DEFAULT_LIST_PARAMS = {
    "userId": "me",
    "maxResults": 50,
}


def build_date_query(start_date: str, end_date: str) -> str:
    """Build Gmail search query for date range.

    Gmail uses after:YYYY/MM/DD before:YYYY/MM/DD format.

    Args:
        start_date: YYYY-MM-DD format
        end_date: YYYY-MM-DD format

    Returns:
        Gmail search query string like "after:2026/02/01 before:2026/02/17"
    """
    start = start_date.replace("-", "/")
    end = end_date.replace("-", "/")
    return f"after:{start} before:{end}"


def validate_date_format(date_str: str) -> str:
    """Validate date string is in YYYY-MM-DD format.

    Args:
        date_str: Date string to validate

    Returns:
        The validated date string

    Raises:
        ValueError: If date format is invalid
    """
    import datetime

    try:
        datetime.datetime.strptime(date_str, "%Y-%m-%d")
        return date_str
    except ValueError:
        raise ValueError(f"Invalid date format: {date_str}. Use YYYY-MM-DD.")


def validate_date_range(start_date: str, end_date: str) -> None:
    """Validate that start_date is not after end_date.

    Catches reversed date ranges (start > end) that would silently return
    0 results from the Gmail API with no explanation.

    Args:
        start_date: Start date string in YYYY-MM-DD format (already validated)
        end_date: End date string in YYYY-MM-DD format (already validated)

    Raises:
        ValueError: If start_date is later than end_date
    """
    import datetime

    start = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.datetime.strptime(end_date, "%Y-%m-%d")

    if start > end:
        raise ValueError(
            f"Invalid date range: start date ({start_date}) is after end date ({end_date}). "
            "Please provide a start date that is on or before the end date."
        )


def validate_query_length(query: str) -> None:
    """Validate that a Gmail search query does not exceed the API limit.

    Args:
        query: Gmail search query string

    Raises:
        ValueError: If query exceeds MAX_QUERY_LENGTH characters
    """
    if len(query) > MAX_QUERY_LENGTH:
        raise ValueError(
            f"Query too long ({len(query)} chars). "
            f"Maximum is {MAX_QUERY_LENGTH} characters."
        )


def validate_gmail_id(value: str, label: str = "ID") -> None:
    """Validate that a string looks like a Gmail message or thread ID.

    Gmail IDs are variable-length hexadecimal strings.

    Args:
        value: The ID string to validate
        label: Human-readable label for error messages (e.g. "message ID", "thread ID")

    Raises:
        ValueError: If value is not a valid hex string
    """
    if not _GMAIL_ID_PATTERN.match(value):
        raise ValueError(
            f"Invalid {label} format: '{value}'. "
            f"Gmail {label}s are hexadecimal strings."
        )
