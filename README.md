# Gmail Reader - Read-Only Gmail Investigation Tool

**CRITICAL SECURITY NOTICE: This tool is READ-ONLY ONLY. It cannot send, modify, or delete emails.**

A secure, Python-based CLI tool **and MCP server** for investigating Gmail accounts with guaranteed read-only access. Provides seamless Gmail integration for Claude desktop/Code via Model Context Protocol (MCP). Uses the same battle-tested security architecture as [google_ads_controller](https://github.com/AdamFerguson06/google-ads-controller).

## Features

- **Dual Interface**: CLI tool + MCP server for Claude integration
- **Read-Only**: Gmail API with `gmail.readonly` scope only
- **Secure**: Test-enforced security guardrails (13 tests, all passing)
- **Full Access**: Search, read, list, export emails and threads
- **Rate Limited**: 10 req/sec (configurable Gmail API quota management)
- **OAuth 2.0**: Secure authentication with credentials in `~/.env`

## Security Guarantees

### Three-Layer Security Architecture

1. **OAuth Scope Restriction** (Layer 1)
   - Only `gmail.readonly` scope is granted during OAuth flow
   - Cannot send, modify, or delete emails at the OAuth level
   - Google enforces this - impossible to bypass

2. **Test-Enforced Guardrails** (Layer 2)
   - `test_read_only_guardrail.py` scans all source files on every commit
   - CI fails if mutating methods found (`.send()`, `.modify()`, `.trash()`, `.delete()`)
   - CI fails if non-readonly scopes found in `auth.py`

3. **Secret Leak Prevention** (Layer 3)
   - `test_secret_leak.py` scans for hardcoded credentials
   - `.gitignore` blocks `.env` and `*.json` credential files
   - CI fails if secrets found in code

### What Gets Committed vs. What Stays Local

✅ **Committed** (safe):
- Source code (no secrets)
- Security tests (scanners)
- Documentation

❌ **NEVER Committed** (blocked by `.gitignore` + tests):
- `~/.env` (OAuth credentials)
- `*.json` files (`client_secret.json`, `token.json`)
- Hardcoded secrets

## Installation

### Prerequisites

- Python 3.9+ (CLI only) or Python 3.11+ (for MCP server)
- Google Cloud Project with Gmail API enabled
- OAuth 2.0 credentials (Desktop app)

### Setup Steps

1. **Clone or create project directory**:
   ```bash
   cd ~/Documents/gmail_reader
   ```

2. **Create virtual environment**:
   ```bash
   python3.9 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install package**:
   ```bash
   pip install -e .
   ```

4. **Obtain OAuth credentials** (one-time):
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing
   - Enable Gmail API (APIs & Services → Library → Gmail API → Enable)
   - Create credentials (APIs & Services → Credentials → Create Credentials → OAuth client ID)
   - Application type: **Desktop app**
   - Download JSON file

5. **Add credentials to `~/.env`**:
   - Open downloaded JSON file
   - Add to `~/.env`:
     ```bash
     GMAIL_CLIENT_ID=YOUR_CLIENT_ID.apps.googleusercontent.com
     GMAIL_CLIENT_SECRET=GOCSPX-YOUR_CLIENT_SECRET
     ```
   - **Delete the downloaded JSON file** after copying values

6. **Run OAuth authentication** (one-time):
   ```bash
   gmail-reader auth
   ```
   - Opens browser to Google consent screen
   - Grant permission for **read-only Gmail access**
   - Refresh token automatically saved to `~/.env`

7. **Test**:
   ```bash
   gmail-reader list --max 10
   ```

## MCP Server Setup (Claude Integration)

The MCP server allows Claude to directly access your Gmail without manual CLI commands.

### Quick Setup

1. **Ensure Python 3.11+ is installed** (MCP requires Python 3.10+):
   ```bash
   python3.11 --version  # Should be 3.11 or higher
   ```

2. **Install gmail-reader** (if not already):
   ```bash
   cd ~/Documents/gmail_reader
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```

3. **Configure MCP server** in Claude desktop config:

   For **Claude Code** (VSCode extension), add to your MCP settings:
   ```json
   {
     "mcpServers": {
       "gmail": {
         "command": "/Users/YOUR_USERNAME/Documents/gmail_reader/.venv/bin/python",
         "args": ["-m", "gmail_reader.mcp_server"],
         "env": {}
       }
     }
   }
   ```

   For **Claude Desktop app**, add to `~/Library/Application Support/Claude/claude_desktop_config.json`:
   ```json
   {
     "mcpServers": {
       "gmail": {
         "command": "/Users/YOUR_USERNAME/Documents/gmail_reader/.venv/bin/python",
         "args": ["-m", "gmail_reader.mcp_server"]
       }
     }
   }
   ```

4. **Restart Claude** to load the MCP server

### MCP Tools Available

Once configured, Claude can use these tools:

| Tool | Description |
|------|-------------|
| `gmail_list` | List recent emails with sender, subject, date, snippet |
| `gmail_search` | Search with Gmail query operators (from:, subject:, after:, etc.) |
| `gmail_read` | Read full email content (headers + body) |
| `gmail_labels` | List all Gmail labels (INBOX, SENT, user-created) |
| `gmail_thread` | View all messages in a thread/conversation |
| `gmail_export` | Export emails in date range to JSON |

### Example Claude Interactions

```
User: "Show me emails from boss@company.com in the last week"
Claude: [Uses gmail_search with query "from:boss@company.com after:2026/02/10"]

User: "Read the most recent email from Google"
Claude: [Uses gmail_list to find ID, then gmail_read to show full content]

User: "How many unread emails do I have?"
Claude: [Uses gmail_search with query "is:unread"]
```

### Troubleshooting MCP Server

**Error: "Authentication error"**
- Run `gmail-reader auth` in terminal first
- Ensure `~/.env` has `GMAIL_REFRESH_TOKEN`

**MCP server not loading**
- Check Python path is correct (use absolute path)
- Restart Claude desktop/Code
- Check Claude logs for errors

## Usage

### Authentication

```bash
# One-time OAuth setup (opens browser)
gmail-reader auth
```

### List Recent Emails

```bash
# List 50 most recent emails (default)
gmail-reader list

# List 100 most recent emails
gmail-reader list --max 100

# Output as JSON
gmail-reader list --max 10 --output json
```

### Search Emails

Gmail supports powerful search operators:

```bash
# Search by sender
gmail-reader search "from:boss@company.com"

# Search by date range
gmail-reader search "after:2026/02/01 before:2026/02/17"

# Search by subject
gmail-reader search "subject:invoice"

# Search unread emails
gmail-reader search "is:unread"

# Combine multiple criteria
gmail-reader search "from:google.com is:unread after:2026/02/01" --max 100

# Search with label
gmail-reader search "label:important"

# Output as JSON
gmail-reader search "from:noreply" --max 5 --output json
```

**Search Operators**:
- `from:` - Sender email address
- `to:` - Recipient email address
- `subject:` - Subject line keywords
- `after:` - Date range start (YYYY/MM/DD)
- `before:` - Date range end (YYYY/MM/DD)
- `is:unread` / `is:read` - Read status
- `label:` - Gmail label
- `has:attachment` - Has attachments

### Read Full Email

```bash
# Read email (snippet view)
gmail-reader read <message-id>

# Read email (full body)
gmail-reader read <message-id> --format full

# Output as JSON
gmail-reader read <message-id> --output json
```

### Export Emails

```bash
# Export all emails in date range to JSON
gmail-reader export --start-date 2026-01-01 --end-date 2026-02-17

# Custom output file
gmail-reader export --start-date 2026-01-01 --end-date 2026-02-17 --file my_emails.json
```

**Note**: Large exports stream to file to avoid memory overflow.

### List Gmail Labels

```bash
# List all labels
gmail-reader labels

# Output as JSON
gmail-reader labels --output json
```

### View Email Thread

```bash
# View all messages in a thread
gmail-reader threads <thread-id>

# Output as JSON
gmail-reader threads <thread-id> --output json
```

## Rate Limiting

- **Gmail API quota**: 250 units/user/second
- **Default**: 10 requests/second (50 units/sec, 20% of limit)
- **Automatic retry**: On 429 (rate limit exceeded) errors

Rate limiting is configured in `src/gmail_reader/client.py`:
```python
_RATE_LIMIT_RPS = 10  # Requests per second
```

## Project Structure

```
gmail_reader/
├── src/gmail_reader/
│   ├── __init__.py          - Package metadata
│   ├── config.py            - Load ~/.env credentials
│   ├── auth.py              - OAuth 2.0 flow
│   ├── client.py            - Gmail API client + rate limiting
│   ├── queries.py           - Query constants & helpers
│   ├── __main__.py          - CLI entry point
│   ├── mcp_server.py        - MCP server for Claude integration
│   └── reports.py           - Email parsing & formatting
├── tests/
│   ├── test_config.py                - Config loading tests
│   ├── test_read_only_guardrail.py   - Security scanner (mutations)
│   └── test_secret_leak.py           - Security scanner (credentials)
├── pyproject.toml           - Package configuration
├── .gitignore               - Blocks .env and *.json
└── README.md                - This file
```

## Security Best Practices

### Credentials Management

1. **All credentials in `~/.env`** - Never commit to git
2. **Delete OAuth JSON** after adding to `~/.env`
3. **Refresh token rotation** - If token expires, re-run `gmail-reader auth`

### Verifying Read-Only Status

Run security tests to verify no mutations:

```bash
pytest tests/test_read_only_guardrail.py -v
pytest tests/test_secret_leak.py -v
```

### OAuth Scope Verification

Check `src/gmail_reader/auth.py`:
```python
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
```

Only `gmail.readonly` should be present. Security test will fail if modified.

## Troubleshooting

### "Error: GMAIL_REFRESH_TOKEN not found"

**Solution**: Run `gmail-reader auth` to authenticate.

### "Refresh token expired"

**Solution**: Re-run `gmail-reader auth` to obtain new refresh token.

### "Rate limit exceeded"

**Solution**: Wait 10 seconds. Tool automatically retries once. If persistent, increase delay in `client.py`.

### "No module named 'gmail_reader'"

**Solution**: Install package with `pip install -e .` from project root.

### OAuth JSON downloaded but can't find it

**Solution**: Check `~/Downloads/client_secret_*.json`. Open file and copy `client_id` and `client_secret` to `~/.env`.

## Development

### Running Tests

```bash
# All tests
pytest tests/ -v

# Security tests only
pytest tests/test_read_only_guardrail.py tests/test_secret_leak.py -v

# Config tests only
pytest tests/test_config.py -v
```

### Adding New Features

**CRITICAL**: Never add write operations. Security tests will fail.

If you need to add a new read operation:

1. Update `ALLOWED_GMAIL_METHODS` in `tests/test_read_only_guardrail.py`
2. Implement using only `.list()` or `.get()` methods
3. Run `pytest tests/test_read_only_guardrail.py` to verify

## License

MIT License - See LICENSE file for details.

## Related Projects

- [google_ads_controller](https://github.com/AdamFerguson06/google-ads-controller) - Read-only Google Ads investigation tool (same security architecture)

## Support

For issues or questions, create an issue in the GitHub repository.

---

**Last Updated**: 2026-02-17
**Version**: 0.1.0
