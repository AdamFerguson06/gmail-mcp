"""Email parsing, formatting, and display functions.

Provides both shared data-fetching functions (used by CLI and MCP server)
and CLI-specific print/export functions.
"""

import base64
import binascii
import json
import logging
from datetime import datetime

from googleapiclient.errors import HttpError
from tabulate import tabulate

from gmail_reader.client import execute_gmail_request
from gmail_reader.config import (
    MAX_MESSAGES_IN_MEMORY,
    MAX_MIME_DEPTH,
    MAX_PAGES,
    SNIPPET_MAX_LENGTH,
)
from gmail_reader.queries import (
    LABEL_FIELDS,
    MESSAGE_DETAIL_FIELDS,
    MESSAGE_FULL_FIELDS,
    MESSAGE_LIST_FIELDS,
    THREAD_FIELDS,
    build_date_query,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared data-fetching functions (used by both CLI and MCP server)
# ---------------------------------------------------------------------------


def fetch_message_details(
    service,
    messages: list[dict],
    include_thread_id: bool = False,
) -> list[dict]:
    """Fetch metadata details for a list of message stubs.

    Args:
        service: Gmail API service object
        messages: List of message dicts with at least "id" key (from messages.list)
        include_thread_id: If True, include threadId in output

    Returns:
        List of dicts with id, date, from, to, subject, snippet (and optionally thread_id)
    """
    message_data = []
    for msg in messages:
        msg_id = msg["id"]
        try:
            detail = execute_gmail_request(
                service,
                lambda mid=msg_id: service.users()
                .messages()
                .get(
                    userId="me",
                    id=mid,
                    format="metadata",
                    metadataHeaders=["From", "To", "Subject", "Date"],
                    fields=MESSAGE_DETAIL_FIELDS,
                )
                .execute(),
                operation_name="get message metadata",
            )
        except HttpError as e:
            logger.warning("Skipping message %s: %s", msg_id, e)
            continue

        headers = _parse_headers(detail.get("payload", {}))
        internal_date = detail.get("internalDate", "0")
        snippet = detail.get("snippet", "")

        entry = {
            "id": msg_id,
            "date": _format_date(internal_date),
            "from": headers.get("From", "(unknown)"),
            "to": headers.get("To", "(unknown)"),
            "subject": headers.get("Subject", "(no subject)"),
            "snippet": snippet,
        }
        if include_thread_id:
            entry["thread_id"] = detail.get("threadId", "")
        message_data.append(entry)

    return message_data


def fetch_message_full_detail(service, message_id: str) -> dict:
    """Fetch full message content by ID.

    Args:
        service: Gmail API service object
        message_id: Gmail message ID

    Returns:
        Full Gmail message resource dict
    """
    return execute_gmail_request(
        service,
        lambda: service.users()
        .messages()
        .get(userId="me", id=message_id, fields=MESSAGE_FULL_FIELDS)
        .execute(),
        operation_name="get message detail",
    )


def fetch_thread_details(service, thread_id: str) -> dict:
    """Fetch a thread with all its messages.

    Args:
        service: Gmail API service object
        thread_id: Gmail thread ID

    Returns:
        Gmail thread resource dict with "messages" list
    """
    return execute_gmail_request(
        service,
        lambda: service.users()
        .threads()
        .get(userId="me", id=thread_id, fields=THREAD_FIELDS)
        .execute(),
        operation_name="get thread",
    )


def fetch_labels(service) -> list[dict]:
    """Fetch all Gmail labels.

    Args:
        service: Gmail API service object

    Returns:
        List of label dicts with id, name, type
    """
    result = execute_gmail_request(
        service,
        lambda: service.users()
        .labels()
        .list(userId="me", fields=LABEL_FIELDS)
        .execute(),
        operation_name="list labels",
    )
    return result.get("labels", [])


# ---------------------------------------------------------------------------
# CLI display functions
# ---------------------------------------------------------------------------


def print_message_list(
    service, query=None, max_results=50, output_format="table"
):
    """List messages with sender, subject, date, snippet.

    Args:
        service: Gmail API service object
        query: Gmail search query string (optional)
        max_results: Maximum number of messages to return
        output_format: "table" or "json"
    """
    messages = _fetch_all_messages(service, query=query, max_results=max_results)

    if not messages:
        print("No messages found.")
        return

    message_data = fetch_message_details(service, messages)

    if not message_data:
        print("No messages found.")
        return

    # Truncate snippets for table display
    for m in message_data:
        snippet = m["snippet"]
        m["snippet"] = snippet[:100] + ("..." if len(snippet) > 100 else "")

    if output_format == "json":
        print(json.dumps(message_data, indent=2))
    else:
        headers = ["ID", "Date", "From", "Subject", "Snippet"]
        rows = [
            [m["id"], m["date"], m["from"], m["subject"], m["snippet"]]
            for m in message_data
        ]
        print(tabulate(rows, headers=headers, tablefmt="grid"))


def print_message_detail(
    service, message_id, output_format="table", detail_level="full"
):
    """Print full message details including headers and body.

    Args:
        service: Gmail API service object
        message_id: Gmail message ID
        output_format: "table" or "json"
        detail_level: "full" or "snippet"
    """
    message = fetch_message_full_detail(service, message_id)

    if output_format == "json":
        print(json.dumps(message, indent=2))
        return

    headers = _parse_headers(message.get("payload", {}))
    snippet = message.get("snippet", "")
    internal_date = message.get("internalDate", "0")
    labels = message.get("labelIds", [])

    print("=" * 80)
    print(f"Message ID: {message_id}")
    print(f"Date: {_format_date(internal_date)}")
    print(f"From: {headers.get('From', '(unknown)')}")
    print(f"To: {headers.get('To', '(unknown)')}")
    print(f"Subject: {headers.get('Subject', '(no subject)')}")
    print(f"Labels: {', '.join(labels)}")
    print("=" * 80)

    if detail_level == "snippet":
        print(f"\n{snippet}\n")
    else:
        text_body, html_body = _parse_body(message.get("payload", {}))

        if text_body:
            print("\n--- Plain Text Body ---")
            print(text_body)
        elif html_body:
            print("\n--- HTML Body ---")
            print(html_body)
        else:
            print("\n(No body content)")

    print("=" * 80)


def print_thread_messages(service, thread_id, output_format="table"):
    """Print all messages in a thread.

    Args:
        service: Gmail API service object
        thread_id: Gmail thread ID
        output_format: "table" or "json"
    """
    thread = fetch_thread_details(service, thread_id)
    messages = thread.get("messages", [])

    if not messages:
        print("No messages found in thread.")
        return

    if output_format == "json":
        print(json.dumps(thread, indent=2))
        return

    print(f"Thread ID: {thread_id}")
    print(f"Messages: {len(messages)}\n")

    for i, msg in enumerate(messages, 1):
        headers = _parse_headers(msg.get("payload", {}))
        snippet = msg.get("snippet", "")
        internal_date = msg.get("internalDate", "0")

        print(f"--- Message {i}/{len(messages)} ---")
        print(f"ID: {msg['id']}")
        print(f"Date: {_format_date(internal_date)}")
        print(f"From: {headers.get('From', '(unknown)')}")
        print(f"Subject: {headers.get('Subject', '(no subject)')}")
        print(f"Snippet: {snippet[:SNIPPET_MAX_LENGTH]}")
        print()


def print_labels(service, output_format="table"):
    """Print all Gmail labels.

    Args:
        service: Gmail API service object
        output_format: "table" or "json"
    """
    labels = fetch_labels(service)

    if not labels:
        print("No labels found.")
        return

    if output_format == "json":
        print(json.dumps(labels, indent=2))
        return

    headers = ["ID", "Name", "Type"]
    rows = [[label["id"], label["name"], label.get("type", "")] for label in labels]
    print(tabulate(rows, headers=headers, tablefmt="grid"))


def export_messages_to_json(service, start_date, end_date, output_file):
    """Export all messages in date range to JSON file.

    Streams to file to avoid memory overflow on large exports.

    Args:
        service: Gmail API service object
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD
        output_file: Path to output JSON file
    """
    query = build_date_query(start_date, end_date)
    message_ids = _fetch_all_message_ids(service, query=query)

    print(f"Exporting {len(message_ids)} messages to {output_file}...")

    exported_count = 0
    skipped_count = 0
    try:
        with open(output_file, "w") as f:
            f.write("[\n")
            first = True

            for i, msg_id in enumerate(message_ids, 1):
                if i % 100 == 0:
                    logger.info("Export progress: %d/%d messages", i, len(message_ids))

                try:
                    message = execute_gmail_request(
                        service,
                        lambda mid=msg_id: service.users()
                        .messages()
                        .get(userId="me", id=mid, fields=MESSAGE_FULL_FIELDS)
                        .execute(),
                        operation_name="export message",
                    )
                except HttpError as e:
                    logger.warning("Skipping message %s during export: %s", msg_id, e)
                    skipped_count += 1
                    continue

                if not first:
                    f.write(",\n")
                json.dump(message, f, indent=2)
                first = False
                exported_count += 1

            f.write("\n]\n")
    except Exception as e:
        logger.error(
            "Export failed after writing %d/%d messages. "
            "Output file '%s' may be incomplete. Reason: %s",
            exported_count, len(message_ids), output_file, e,
        )
        raise

    summary = f"Export complete: {exported_count} messages saved to {output_file}"
    if skipped_count:
        summary += f" ({skipped_count} messages skipped due to errors)"
    print(summary)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_all_messages(service, query=None, max_results=None):
    """Fetch all messages matching query, handling pagination.

    Gmail API returns nextPageToken for results > 500.

    Args:
        service: Gmail API service object
        query: Gmail search query string (optional)
        max_results: Maximum number of messages to return (optional)

    Returns:
        list of message dicts with 'id' and 'threadId'
    """
    seen_tokens: set = set()
    all_messages = []
    page_token = None
    page_count = 0

    while True:
        if page_count >= MAX_PAGES:
            logger.warning(
                "Reached maximum page limit (%d). Returning partial results.",
                MAX_PAGES,
            )
            break

        params = {
            "userId": "me",
            "maxResults": min(500, max_results or 500),
            "fields": "messages(id,threadId),nextPageToken",
        }
        if query:
            params["q"] = query
        if page_token:
            params["pageToken"] = page_token

        result = execute_gmail_request(
            service,
            lambda p=dict(params): service.users().messages().list(**p).execute(),
            operation_name="list messages",
        )

        messages = result.get("messages", [])
        all_messages.extend(messages)
        page_count += 1

        if page_count % 5 == 0:
            logger.debug(
                "Pagination progress: page %d, %d messages so far",
                page_count, len(all_messages),
            )

        if len(all_messages) >= MAX_MESSAGES_IN_MEMORY:
            logger.warning(
                "Reached maximum in-memory message limit (%d). "
                "Returning partial results. Use date filters to narrow the query.",
                MAX_MESSAGES_IN_MEMORY,
            )
            return all_messages[:MAX_MESSAGES_IN_MEMORY]

        if max_results and len(all_messages) >= max_results:
            return all_messages[:max_results]

        new_page_token = result.get("nextPageToken")
        if not new_page_token:
            break

        if new_page_token in seen_tokens:
            logger.warning(
                "Duplicate nextPageToken at page %d. Stopping pagination.",
                page_count,
            )
            break

        seen_tokens.add(new_page_token)
        page_token = new_page_token

    return all_messages


def _fetch_all_message_ids(service, query=None):
    """Fetch all message IDs matching query (for export).

    Args:
        service: Gmail API service object
        query: Gmail search query string (optional)

    Returns:
        list of message IDs (strings)
    """
    messages = _fetch_all_messages(service, query=query)
    return [msg["id"] for msg in messages]


def _parse_headers(payload: dict) -> dict:
    """Extract common headers from message payload.

    Args:
        payload: Gmail message payload dict

    Returns:
        dict with keys: From, To, Subject, Date, Cc, Bcc
    """
    headers = {
        "From": "(unknown)",
        "To": "(unknown)",
        "Subject": "(no subject)",
        "Date": "(unknown)",
        "Cc": "",
        "Bcc": "",
    }

    for header in payload.get("headers", []):
        name = header["name"]
        if name in headers:
            headers[name] = header["value"]

    return headers


def _parse_body(payload: dict, depth: int = 0) -> tuple[str, str]:
    """Extract text and HTML body from message payload.

    Handles:
    - Simple body (non-multipart)
    - Multipart messages (text/plain + text/html)
    - Nested multipart (up to MAX_MIME_DEPTH levels)
    - Base64 decoding (Gmail uses urlsafe_b64decode)
    - Encoding errors (try multiple encodings before replace)

    Args:
        payload: Gmail message payload dict
        depth: Current recursion depth (used to enforce MAX_MIME_DEPTH)

    Returns:
        tuple of (text_body, html_body)
    """
    if depth > MAX_MIME_DEPTH:
        logger.warning(
            "MIME parsing exceeded maximum depth (%d). Skipping remaining nested parts.",
            MAX_MIME_DEPTH,
        )
        return "", ""

    text_body = ""
    html_body = ""

    try:
        if "body" in payload and payload["body"].get("data"):
            data = base64.urlsafe_b64decode(payload["body"]["data"])
            mime_type = payload.get("mimeType", "text/plain")

            if "html" in mime_type.lower():
                html_body = _decode_bytes(data)
            else:
                text_body = _decode_bytes(data)

            return text_body, html_body

        parts = payload.get("parts", [])
        for part in parts:
            mime_type = part.get("mimeType", "")

            if mime_type == "text/plain" and "data" in part.get("body", {}):
                data = base64.urlsafe_b64decode(part["body"]["data"])
                text_body = _decode_bytes(data)

            elif mime_type == "text/html" and "data" in part.get("body", {}):
                data = base64.urlsafe_b64decode(part["body"]["data"])
                html_body = _decode_bytes(data)

            elif "parts" in part:
                nested_text, nested_html = _parse_body(part, depth=depth + 1)
                text_body = text_body or nested_text
                html_body = html_body or nested_html

    except (KeyError, ValueError, UnicodeDecodeError, binascii.Error) as e:
        logger.warning(
            "Failed to parse message body (mimeType=%s): %s",
            payload.get("mimeType", "unknown"), e,
        )
        return "(parsing error)", "(parsing error)"

    return text_body, html_body


def _decode_bytes(data: bytes) -> str:
    """Decode email body bytes, trying common encodings before falling back.

    Try multiple encodings (utf-8, windows-1252, iso-8859-1) before falling
    back to errors='replace', to avoid garbling cp1252 emails. Note:
    windows-1252 must come before iso-8859-1 because iso-8859-1 accepts
    every byte sequence without error, making any later fallback unreachable.

    Args:
        data: Raw bytes from email body

    Returns:
        Decoded string
    """
    for encoding in ("utf-8", "windows-1252", "iso-8859-1"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _format_date(internal_date: str) -> str:
    """Convert Gmail internalDate (ms timestamp) to YYYY-MM-DD HH:MM:SS.

    Args:
        internal_date: Gmail internalDate as string (milliseconds)

    Returns:
        Formatted date string
    """
    try:
        timestamp_sec = int(internal_date) / 1000
        dt = datetime.fromtimestamp(timestamp_sec)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError):
        logger.debug("Invalid internalDate value: %r", internal_date)
        return "(invalid date)"
