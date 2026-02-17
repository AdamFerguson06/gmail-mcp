"""Gmail Reader CLI - Read-only Gmail investigation tool.

Commands:
    auth        - Run OAuth 2.0 flow to obtain refresh token
    list        - List recent emails
    search      - Search emails with Gmail query syntax
    read        - Read full email content
    export      - Export emails to JSON file
    labels      - List all Gmail labels
    threads     - View all messages in a thread
    test        - Verify credentials and API connectivity
"""

import argparse
import logging
import sys

from googleapiclient.errors import HttpError

from gmail_reader.auth import run_oauth_flow
from gmail_reader.client import get_gmail_service, execute_gmail_request
from gmail_reader import reports
from gmail_reader.queries import (
    validate_date_format,
    validate_date_range,
    validate_gmail_id,
    validate_query_length,
)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Gmail Reader - Read-only Gmail investigation tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # One-time setup
  gmail-reader auth

  # Verify credentials work
  gmail-reader test

  # List 50 most recent emails
  gmail-reader list

  # Search by sender
  gmail-reader search "from:boss@company.com"

  # Search by date range
  gmail-reader search "after:2026/02/01 before:2026/02/17"

  # Search by subject
  gmail-reader search "subject:invoice"

  # Combine search criteria
  gmail-reader search "from:google.com is:unread after:2026/02/01" --max 100

  # Read full email
  gmail-reader read <message-id>

  # Export to JSON
  gmail-reader export --start-date 2026-01-01 --end-date 2026-02-17 --output emails.json

  # List all labels
  gmail-reader labels

  # View thread
  gmail-reader threads <thread-id>
        """,
    )

    parser.add_argument(
        "command",
        choices=["auth", "list", "search", "read", "export", "labels", "threads", "test"],
        help="Command to execute",
    )

    parser.add_argument(
        "--query",
        help="Gmail search query (for search command). See examples above.",
    )

    parser.add_argument(
        "--message-id",
        help="Message ID (for read command)",
    )

    parser.add_argument(
        "--thread-id",
        help="Thread ID (for threads command)",
    )

    parser.add_argument(
        "--max",
        type=int,
        default=50,
        help="Maximum number of results (default: 50)",
    )

    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date in YYYY-MM-DD format (for export command)",
    )

    parser.add_argument(
        "--end-date",
        type=str,
        help="End date in YYYY-MM-DD format (for export command)",
    )

    parser.add_argument(
        "--output",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )

    parser.add_argument(
        "--format",
        choices=["snippet", "full"],
        default="snippet",
        help="Email detail level for read command (default: snippet)",
    )

    parser.add_argument(
        "--file",
        type=str,
        help="Output file path (for export command with --output json)",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose/debug logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(name)s %(levelname)s: %(message)s",
    )

    # Handle auth command separately (doesn't require service)
    if args.command == "auth":
        run_oauth_flow()
        return

    # All other commands require authenticated Gmail service
    try:
        service = get_gmail_service()
    except (FileNotFoundError, EnvironmentError) as e:
        print(f"Error: {e}", file=sys.stderr)
        print(
            "\nRun 'gmail-reader auth' first to authenticate.", file=sys.stderr
        )
        sys.exit(1)

    # Command dispatch
    try:
        if args.command == "test":
            profile = execute_gmail_request(
                service,
                lambda: service.users().getProfile(userId="me").execute(),
                operation_name="getProfile",
            )
            print(f"Authenticated as: {profile.get('emailAddress', '(unknown)')}")
            print(f"Total messages: {profile.get('messagesTotal', '(unknown)')}")
            print(f"Total threads: {profile.get('threadsTotal', '(unknown)')}")

        elif args.command == "list":
            reports.print_message_list(
                service, max_results=args.max, output_format=args.output
            )

        elif args.command == "search":
            if not args.query:
                print("Error: --query is required for search command", file=sys.stderr)
                sys.exit(1)
            try:
                validate_query_length(args.query)
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)
            reports.print_message_list(
                service,
                query=args.query,
                max_results=args.max,
                output_format=args.output,
            )

        elif args.command == "read":
            if not args.message_id:
                print("Error: --message-id is required for read command", file=sys.stderr)
                sys.exit(1)
            try:
                validate_gmail_id(args.message_id, label="message ID")
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)
            reports.print_message_detail(
                service,
                args.message_id,
                output_format=args.output,
                detail_level=args.format,
            )

        elif args.command == "export":
            if not args.start_date or not args.end_date:
                print(
                    "Error: --start-date and --end-date are required for export command",
                    file=sys.stderr,
                )
                sys.exit(1)

            try:
                start_date = validate_date_format(args.start_date)
                end_date = validate_date_format(args.end_date)
                validate_date_range(start_date, end_date)
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)

            output_file = args.file or f"gmail_export_{start_date}_to_{end_date}.json"

            reports.export_messages_to_json(
                service, start_date, end_date, output_file
            )

        elif args.command == "labels":
            reports.print_labels(service, output_format=args.output)

        elif args.command == "threads":
            if not args.thread_id:
                print("Error: --thread-id is required for threads command", file=sys.stderr)
                sys.exit(1)
            try:
                validate_gmail_id(args.thread_id, label="thread ID")
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)
            reports.print_thread_messages(
                service, args.thread_id, output_format=args.output
            )

    except KeyboardInterrupt:
        print("\n\nInterrupted by user.", file=sys.stderr)
        sys.exit(1)
    except HttpError as e:
        print(f"Gmail API error: {e}", file=sys.stderr)
        sys.exit(1)
    except EnvironmentError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
