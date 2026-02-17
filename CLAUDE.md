# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_config.py -v

# Run a single test
python -m pytest tests/test_config.py::test_load_config_success -v

# Install in development mode
pip install -e ".[test]"

# Verify credentials and API connectivity
gmail-reader test

# Run CLI with debug logging
gmail-reader list -v
```

## Architecture

This is a **read-only** Gmail tool with two interfaces: a CLI (`__main__.py`) and an MCP server (`mcp_server.py`). Both share the same data layer.

### Data Flow

```
CLI (__main__.py)  ──┐
                     ├──> reports.py (shared fetch functions) ──> client.py ──> Gmail API
MCP (mcp_server.py) ┘
```

- **`config.py`** — Loads OAuth credentials from `~/.env`; also holds all tunable constants (rate limits, pagination limits, etc.) with env var overrides
- **`auth.py`** — OAuth 2.0 flow; POSIX-only (uses `fcntl` for file locking)
- **`client.py`** — `get_gmail_service()` builds the API client; `execute_gmail_request()` wraps every API call with token-bucket rate limiting and retry logic (429 + 5xx)
- **`queries.py`** — Field mask constants (`MESSAGE_LIST_FIELDS`, etc.), date helpers, input validators (`validate_query_length`, `validate_gmail_id`)
- **`reports.py`** — Shared public functions (`fetch_message_details`, `fetch_message_full_detail`, `fetch_thread_details`, `fetch_labels`) used by both CLI and MCP server; also has CLI-specific `print_*` functions and private helpers (`_fetch_all_messages`, `_parse_headers`, `_parse_body`, `_format_date`)
- **`mcp_server.py`** — MCP server with 6 tools; delegates data fetching to `reports.py`; wraps `call_tool()` in HttpError/Exception catch to prevent crashes

### Key Patterns

**Lambda closures in loops** — Always use default arguments to capture loop variables:
```python
# Correct:
lambda mid=msg_id: service.users().messages().get(userId="me", id=mid).execute()
# Wrong (captures reference, gets last value):
lambda: service.users().messages().get(userId="me", id=msg_id).execute()
```

**Field masks** — Every Gmail API call must use `fields=` parameter with constants from `queries.py` to reduce bandwidth.

**All API calls go through `execute_gmail_request()`** — This ensures rate limiting and retry are applied consistently.

## Security Constraints

This tool is **strictly read-only**. Three layers enforce this:

1. **OAuth scope**: Only `gmail.readonly` — set in `auth.py:SCOPES`
2. **Test guardrails**: `test_read_only_guardrail.py` scans all source for mutating API methods (send, modify, trash, delete) and forbidden scopes — CI fails if any are found
3. **Secret scanner**: `test_secret_leak.py` scans for hardcoded credentials

**When adding new Gmail API operations**: Only `.list()`, `.get()`, and `.batchGet()` are allowed. Update `ALLOWED_GMAIL_METHODS` in `test_read_only_guardrail.py` if adding a new read method.

## Configuration

All tunable constants live in `config.py` with env var overrides (e.g., `GMAIL_RATE_LIMIT_RPS`, `GMAIL_MAX_RETRIES`, `MAX_PAGES`). Don't hardcode magic numbers in other modules — import from config.
