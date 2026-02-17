"""Gmail API query constants and helper functions."""

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
