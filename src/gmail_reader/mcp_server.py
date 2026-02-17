#!/usr/bin/env python3
"""MCP server for Gmail Reader - provides read-only Gmail access to Claude.

CRITICAL SECURITY: This server is READ-ONLY. It cannot send, modify, or delete emails.
All security guarantees from the CLI tool apply here.
"""

import asyncio
import json
import logging
from typing import Any

from googleapiclient.errors import HttpError
from mcp.server import Server
from mcp.types import Tool, TextContent

from gmail_reader.client import get_gmail_service
from gmail_reader.config import MCP_EXPORT_LIMIT
from gmail_reader.queries import (
    build_date_query,
    validate_date_format,
    validate_date_range,
    validate_gmail_id,
    validate_query_length,
)
from gmail_reader.reports import (
    fetch_all_message_ids,
    fetch_all_messages,
    parse_body,
    parse_headers,
    format_date,
    fetch_labels,
    fetch_message_details,
    fetch_message_full_detail,
    fetch_thread_details,
)

logger = logging.getLogger(__name__)

app = Server("gmail-reader")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available Gmail tools.

    All tools are READ-ONLY - no sending, modifying, or deleting emails.
    """
    return [
        Tool(
            name="gmail_list",
            description="List recent emails with sender, subject, date, and snippet. Returns up to max_results emails (default: 50).",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of emails to return (default: 50)",
                        "default": 50,
                    },
                },
            },
        ),
        Tool(
            name="gmail_search",
            description="Search Gmail with powerful query operators. Supports: from:, to:, subject:, after:YYYY/MM/DD, before:YYYY/MM/DD, is:unread, label:, has:attachment. Returns matching emails with sender, subject, date, and snippet.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Gmail search query (e.g., 'from:boss@company.com is:unread after:2026/02/01')",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="gmail_read",
            description="Read full email content including headers and body (text or HTML). Use message ID from gmail_list or gmail_search results.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "Gmail message ID (from gmail_list or gmail_search)",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["snippet", "full"],
                        "description": "Detail level: 'snippet' for preview, 'full' for complete body (default: full)",
                        "default": "full",
                    },
                },
                "required": ["message_id"],
            },
        ),
        Tool(
            name="gmail_labels",
            description="List all Gmail labels (both system labels like INBOX, SENT and user-created labels).",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="gmail_thread",
            description="View all messages in an email thread/conversation. Shows the complete conversation flow with all messages in chronological order.",
            inputSchema={
                "type": "object",
                "properties": {
                    "thread_id": {
                        "type": "string",
                        "description": "Gmail thread ID (from gmail_list or gmail_search results)",
                    },
                },
                "required": ["thread_id"],
            },
        ),
        Tool(
            name="gmail_export",
            description="Export all emails in a date range to structured JSON. Useful for analysis, archiving, or processing multiple emails. WARNING: Large date ranges may take several minutes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Start date in YYYY-MM-DD format",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date in YYYY-MM-DD format",
                    },
                },
                "required": ["start_date", "end_date"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls for Gmail operations.

    All operations are read-only and use the authenticated Gmail API service.
    """
    try:
        service = get_gmail_service()
    except Exception as e:
        return [
            TextContent(
                type="text",
                text=f"Authentication error: {e}\n\nRun 'gmail-reader auth' in terminal to authenticate.",
            )
        ]

    try:
        return await _dispatch_tool(name, arguments, service)
    except HttpError as e:
        logger.error("Gmail API error in %s: %s", name, e)
        return [
            TextContent(
                type="text",
                text=f"Gmail API error: {e}",
            )
        ]
    except Exception as e:
        logger.exception("Unexpected error in %s", name)
        return [
            TextContent(
                type="text",
                text=f"Unexpected error: {e}",
            )
        ]


async def _dispatch_tool(name: str, arguments: Any, service) -> list[TextContent]:
    """Route tool call to the appropriate handler."""

    if name == "gmail_list":
        max_results = arguments.get("max_results", 50)
        messages = fetch_all_messages(service, max_results=max_results)

        if not messages:
            return [TextContent(type="text", text="No messages found.")]

        message_data = fetch_message_details(
            service, messages, include_thread_id=True
        )

        return [
            TextContent(type="text", text=json.dumps(message_data, indent=2))
        ]

    elif name == "gmail_search":
        query = arguments.get("query", "")
        max_results = arguments.get("max_results", 50)

        if not query:
            return [TextContent(type="text", text="Error: query parameter is required")]

        try:
            validate_query_length(query)
        except ValueError as e:
            return [TextContent(type="text", text=f"Error: {e}")]

        messages = fetch_all_messages(
            service, query=query, max_results=max_results
        )

        if not messages:
            return [
                TextContent(type="text", text=f"No messages found for query: {query}")
            ]

        message_data = fetch_message_details(
            service, messages, include_thread_id=True
        )

        return [
            TextContent(
                type="text",
                text=f"Found {len(message_data)} message(s) for query: {query}\n\n"
                + json.dumps(message_data, indent=2),
            )
        ]

    elif name == "gmail_read":
        message_id = arguments.get("message_id", "")
        detail_level = arguments.get("format", "full")

        if not message_id:
            return [
                TextContent(type="text", text="Error: message_id parameter is required")
            ]

        try:
            validate_gmail_id(message_id, label="message ID")
        except ValueError as e:
            return [TextContent(type="text", text=f"Error: {e}")]

        message = fetch_message_full_detail(service, message_id)

        headers = parse_headers(message.get("payload", {}))
        snippet = message.get("snippet", "")
        internal_date = message.get("internalDate", "0")
        labels = message.get("labelIds", [])

        result = {
            "id": message_id,
            "date": format_date(internal_date),
            "from": headers.get("From", "(unknown)"),
            "to": headers.get("To", "(unknown)"),
            "subject": headers.get("Subject", "(no subject)"),
            "labels": labels,
            "snippet": snippet,
        }

        if detail_level == "full":
            text_body, html_body = parse_body(message.get("payload", {}))
            result["text_body"] = text_body
            result["html_body"] = html_body

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "gmail_labels":
        labels = fetch_labels(service)

        if not labels:
            return [TextContent(type="text", text="No labels found.")]

        return [TextContent(type="text", text=json.dumps(labels, indent=2))]

    elif name == "gmail_thread":
        thread_id = arguments.get("thread_id", "")

        if not thread_id:
            return [
                TextContent(type="text", text="Error: thread_id parameter is required")
            ]

        try:
            validate_gmail_id(thread_id, label="thread ID")
        except ValueError as e:
            return [TextContent(type="text", text=f"Error: {e}")]

        thread = fetch_thread_details(service, thread_id)
        messages = thread.get("messages", [])

        if not messages:
            return [TextContent(type="text", text="No messages found in thread.")]

        thread_data = []
        for msg in messages:
            headers = parse_headers(msg.get("payload", {}))
            snippet = msg.get("snippet", "")
            internal_date = msg.get("internalDate", "0")

            thread_data.append(
                {
                    "id": msg["id"],
                    "date": format_date(internal_date),
                    "from": headers.get("From", "(unknown)"),
                    "subject": headers.get("Subject", "(no subject)"),
                    "snippet": snippet,
                }
            )

        return [
            TextContent(
                type="text",
                text=f"Thread {thread_id} ({len(thread_data)} messages):\n\n"
                + json.dumps(thread_data, indent=2),
            )
        ]

    elif name == "gmail_export":
        start_date = arguments.get("start_date", "")
        end_date = arguments.get("end_date", "")

        if not start_date or not end_date:
            return [
                TextContent(
                    type="text",
                    text="Error: start_date and end_date parameters are required (YYYY-MM-DD format)",
                )
            ]

        try:
            validate_date_format(start_date)
            validate_date_format(end_date)
            validate_date_range(start_date, end_date)
        except ValueError as e:
            return [TextContent(type="text", text=f"Date validation error: {e}")]

        query = build_date_query(start_date, end_date)
        message_ids = fetch_all_message_ids(service, query=query)

        if not message_ids:
            return [
                TextContent(
                    type="text",
                    text=f"No messages found between {start_date} and {end_date}",
                )
            ]

        truncated = len(message_ids) > MCP_EXPORT_LIMIT
        ids_to_fetch = message_ids[:MCP_EXPORT_LIMIT]

        all_messages = []
        for msg_id in ids_to_fetch:
            try:
                message = fetch_message_full_detail(service, msg_id)
                headers = parse_headers(message.get("payload", {}))
                internal_date = message.get("internalDate", "0")
                text_body, html_body = parse_body(message.get("payload", {}))

                all_messages.append({
                    "id": msg_id,
                    "thread_id": message.get("threadId", ""),
                    "date": format_date(internal_date),
                    "from": headers.get("From", "(unknown)"),
                    "to": headers.get("To", "(unknown)"),
                    "subject": headers.get("Subject", "(no subject)"),
                    "snippet": message.get("snippet", ""),
                    "labels": message.get("labelIds", []),
                    "text_body": text_body,
                    "html_body": html_body,
                })
            except HttpError as e:
                logger.warning("Skipping message %s during export: %s", msg_id, e)

        summary = f"Exported {len(all_messages)} message(s) from {start_date} to {end_date}"
        if truncated:
            summary += (
                f"\n\nWARNING: Only {MCP_EXPORT_LIMIT} of {len(message_ids)} total messages "
                f"were exported. The MCP tool limits exports to {MCP_EXPORT_LIMIT} messages. "
                "For a complete export, use the CLI: "
                f"gmail-reader export --start-date {start_date} --end-date {end_date} --file output.json"
            )

        return [
            TextContent(
                type="text",
                text=summary + "\n\n" + json.dumps(all_messages, indent=2),
            )
        ]

    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    """Run the MCP server."""
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
