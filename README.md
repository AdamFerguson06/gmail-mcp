# Gmail Reader - Read-Only Gmail Investigation Tool

**CRITICAL SECURITY NOTICE: This tool is READ-ONLY ONLY. It cannot send, modify, or delete emails.**

A secure, Python-based CLI tool for investigating Gmail accounts with guaranteed read-only access. Uses the same battle-tested security architecture as [google_ads_controller](https://github.com/AdamFerguson06/google-ads-controller).

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

- Python 3.9+
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
