"""Email parsing, formatting, and display functions."""

import base64
import binascii
import json
import sys
from datetime import datetime
from typing import Optional

from tabulate import tabulate

from gmail_reader.client import execute_gmail_request
from gmail_reader.queries import build_date_query


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

    # Fetch full details for each message (for headers)
    message_data = []
    for msg in messages:
        msg_id = msg["id"]
        detail = execute_gmail_request(
            service,
            lambda: service.users()
            .messages()
            .get(userId="me", id=msg_id, format="metadata", metadataHeaders=["From", "Subject", "Date"])
            .execute(),
        )

        headers = _parse_headers(detail.get("payload", {}))
        internal_date = detail.get("internalDate", "0")
        snippet = detail.get("snippet", "")

        message_data.append(
            {
                "id": msg_id,
                "date": _format_date(internal_date),
                "from": headers.get("From", "(unknown)"),
                "subject": headers.get("Subject", "(no subject)"),
                "snippet": snippet[:100] + ("..." if len(snippet) > 100 else ""),
            }
        )

    if output_format == "json":
        print(json.dumps(message_data, indent=2))
    else:
        # Table format
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
    message = execute_gmail_request(
        service,
        lambda: service.users().messages().get(userId="me", id=message_id).execute(),
    )

    if output_format == "json":
        print(json.dumps(message, indent=2))
        return

    # Table format
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
        # Full body
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
    thread = execute_gmail_request(
        service,
        lambda: service.users().threads().get(userId="me", id=thread_id).execute(),
    )

    messages = thread.get("messages", [])

    if not messages:
        print("No messages found in thread.")
        return

    if output_format == "json":
        print(json.dumps(thread, indent=2))
        return

    # Table format
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
        print(f"Snippet: {snippet[:150]}")
        print()


def print_labels(service, output_format="table"):
    """Print all Gmail labels.

    Args:
        service: Gmail API service object
        output_format: "table" or "json"
    """
    result = execute_gmail_request(
        service, lambda: service.users().labels().list(userId="me").execute()
    )

    labels = result.get("labels", [])

    if not labels:
        print("No labels found.")
        return

    if output_format == "json":
        print(json.dumps(labels, indent=2))
        return

    # Table format
    headers = ["ID", "Name", "Type"]
    rows = [[label["id"], label["name"], label.get("type", "")] for label in labels]
    print(tabulate(rows, headers=headers, tablefmt="grid"))


def export_messages_to_json(service, start_date, end_date, output_file):
    """Export all messages in date range to JSON file.

    CRITICAL: Streams to file to avoid memory overflow on large exports.

    Args:
        service: Gmail API service object
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD
        output_file: Path to output JSON file
    """
    query = build_date_query(start_date, end_date)
    message_ids = _fetch_all_message_ids(service, query=query)

    print(f"Exporting {len(message_ids)} messages to {output_file}...")

    # Wrap export in try/except so partial-write failures are reported
    # clearly instead of leaving an invalid JSON file with no error message.
    exported_count = 0
    try:
        with open(output_file, "w") as f:
            f.write("[\n")
            first = True

            for i, msg_id in enumerate(message_ids, 1):
                if i % 100 == 0:
                    print(f"Progress: {i}/{len(message_ids)} messages exported...")

                message = execute_gmail_request(
                    service,
                    lambda: service.users()
                    .messages()
                    .get(userId="me", id=msg_id)
                    .execute(),
                )

                if not first:
                    f.write(",\n")
                json.dump(message, f, indent=2)
                first = False
                exported_count += 1

            f.write("\n]\n")
    except Exception as e:
        print(
            f"Error: Export failed after writing {exported_count}/{len(message_ids)} messages. "
            f"Output file '{output_file}' may be incomplete or invalid JSON. "
            f"Reason: {e}",
            file=sys.stderr,
        )
        raise

    print(f"✅ Export complete: {len(message_ids)} messages saved to {output_file}")


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
    # Guard against infinite pagination from duplicate nextPageToken.
    # Also enforces a hard page limit as a safety net.
    _MAX_PAGES = 1000

    # Hard memory limit to prevent 100MB+ RAM usage on large inboxes
    _MAX_MESSAGES_IN_MEMORY = 10000

    seen_tokens: set = set()

    all_messages = []
    page_token = None
    page_count = 0

    while True:
        if page_count >= _MAX_PAGES:
            print(
                f"Warning: Reached maximum page limit ({_MAX_PAGES}). "
                "Returning partial results.",
                file=sys.stderr,
            )
            break

        params = {
            "userId": "me",
            "maxResults": min(500, max_results or 500),  # API max per page
        }
        if query:
            params["q"] = query
        if page_token:
            params["pageToken"] = page_token

        result = execute_gmail_request(
            service, lambda: service.users().messages().list(**params).execute()
        )

        messages = result.get("messages", [])
        all_messages.extend(messages)
        page_count += 1

        # Enforce hard memory limit
        if len(all_messages) >= _MAX_MESSAGES_IN_MEMORY:
            print(
                f"Warning: Reached maximum in-memory message limit ({_MAX_MESSAGES_IN_MEMORY}). "
                "Returning partial results to avoid excessive memory usage. "
                "Use --start-date/--end-date to narrow the query.",
                file=sys.stderr,
            )
            return all_messages[:_MAX_MESSAGES_IN_MEMORY]

        # Check if we've hit user's max_results limit
        if max_results and len(all_messages) >= max_results:
            return all_messages[:max_results]

        new_page_token = result.get("nextPageToken")
        if not new_page_token:
            break

        # Detect duplicate nextPageToken to prevent infinite loop
        if new_page_token in seen_tokens:
            print(
                f"Warning: Duplicate nextPageToken detected at page {page_count}. "
                "Stopping pagination to prevent infinite loop.",
                file=sys.stderr,
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


def _parse_headers(payload) -> dict:
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


# Limit recursive MIME parsing depth to prevent stack overflow on deeply nested messages
_MAX_MIME_DEPTH = 50


def _parse_body(payload, depth: int = 0) -> tuple[str, str]:
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
    # Guard against deeply nested multipart messages
    if depth > _MAX_MIME_DEPTH:
        print(
            f"Warning: MIME parsing exceeded maximum depth ({_MAX_MIME_DEPTH}). "
            "Skipping remaining nested parts.",
            file=sys.stderr,
        )
        return "", ""

    text_body = ""
    html_body = ""

    try:
        # Check for simple body (non-multipart)
        if "body" in payload and payload["body"].get("data"):
            data = base64.urlsafe_b64decode(payload["body"]["data"])
            mime_type = payload.get("mimeType", "text/plain")

            if "html" in mime_type.lower():
                html_body = _decode_bytes(data)
            else:
                text_body = _decode_bytes(data)

            return text_body, html_body

        # Handle multipart messages
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
                # Nested multipart — pass incremented depth
                nested_text, nested_html = _parse_body(part, depth=depth + 1)
                text_body = text_body or nested_text
                html_body = html_body or nested_html

    except (KeyError, ValueError, UnicodeDecodeError, binascii.Error) as e:
        print(f"Warning: Failed to parse message body: {e}", file=sys.stderr)
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
    # Last resort: replace undecodable bytes
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
        return "(invalid date)"
