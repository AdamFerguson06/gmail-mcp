"""Security test: prevent hardcoded OAuth credentials in source code.

Scans all source files for hardcoded secrets that should be in ~/.env.
If this test fails, someone committed credentials to the repo.

CRITICAL SECURITY: Credentials must NEVER be committed.
"""

import re
from pathlib import Path

SRC_DIR = Path(__file__).parent.parent / "src" / "gmail_reader"
TESTS_DIR = Path(__file__).parent
ROOT_DIR = Path(__file__).parent.parent

# Regex patterns for OAuth secrets
SECRET_PATTERNS = [
    (r"GOCSPX-[0-9A-Za-z\-_]{28}", "Google OAuth client secret"),
    (r"1//[0-9A-Za-z\-_]{40,}", "Google OAuth refresh token"),
    (r"ya29\.[0-9A-Za-z\-_]+", "Google OAuth access token"),
    (r'client_secret\s*[=:]\s*["\'][^"\']+["\']', "Hardcoded client secret"),
    (r'refresh_token\s*[=:]\s*["\']1//[^"\']+["\']', "Hardcoded refresh token"),
]

# Sensitive filenames that should never be committed
SENSITIVE_FILENAMES = [
    ".env",
    "credentials.json",
    "client_secret.json",
    "token.json",
    "client_secret_*.json",
]


def _get_all_python_files():
    """Get all Python files in src/ and tests/."""
    src_files = list(SRC_DIR.glob("**/*.py"))
    test_files = list(TESTS_DIR.glob("**/*.py"))
    return src_files + test_files


def test_no_hardcoded_secrets():
    """Scan all Python files for hardcoded OAuth secrets."""
    violations = []

    for py_file in _get_all_python_files():
        content = py_file.read_text()

        for pattern, description in SECRET_PATTERNS:
            matches = re.findall(pattern, content)
            if matches:
                # Skip false positives in test files (pattern definitions)
                if py_file.name == "test_secret_leak.py":
                    continue

                violations.append(
                    f"{py_file.name}: contains {description} ({matches[0][:20]}...)"
                )

    assert not violations, (
        "HARDCODED SECRET DETECTED — Credentials must be in ~/.env only.\n"
        "Violations:\n" + "\n".join(f"  - {v}" for v in violations)
    )


def test_gitignore_blocks_credentials():
    """Verify .gitignore has all sensitive file patterns."""
    gitignore_path = ROOT_DIR / ".gitignore"

    if not gitignore_path.exists():
        raise FileNotFoundError(
            ".gitignore not found. Create one to block sensitive files."
        )

    gitignore_content = gitignore_path.read_text()

    required_patterns = [
        ".env",
        "*.json",
        "credentials.json",
        "token.json",
        "client_secret_*.json",
    ]

    missing = []
    for pattern in required_patterns:
        if pattern not in gitignore_content:
            missing.append(pattern)

    assert not missing, (
        ".gitignore is missing required patterns to block credentials:\n"
        + "\n".join(f"  - {p}" for p in missing)
    )


def test_no_sensitive_files_in_repo():
    """Verify no sensitive credential files are in the repository."""
    violations = []

    # Check for .env file
    if (ROOT_DIR / ".env").exists():
        violations.append(".env file found in repo (should be gitignored)")

    # Check for JSON credential files
    for json_file in ROOT_DIR.glob("*.json"):
        if json_file.name != "pyproject.toml":  # Skip package.json if exists
            violations.append(f"{json_file.name} found in repo (should be gitignored)")

    for json_file in ROOT_DIR.glob("client_secret_*.json"):
        violations.append(
            f"{json_file.name} found in repo (OAuth credential file, should be gitignored)"
        )

    assert not violations, (
        "SENSITIVE FILES DETECTED in repository:\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nThese files should be in .gitignore and removed from repo."
    )


def test_no_example_credentials_in_readme():
    """Verify README doesn't contain example credentials that look real."""
    readme_path = ROOT_DIR / "README.md"

    if not readme_path.exists():
        # README not created yet, skip
        return

    content = readme_path.read_text()

    # Check for patterns that look like real credentials (not obviously fake)
    suspicious_patterns = [
        (r"GOCSPX-[0-9A-Za-z\-_]{28}", "Real-looking client secret"),
        (r"1//[0-9A-Za-z\-_]{40,}", "Real-looking refresh token"),
    ]

    violations = []
    for pattern, description in suspicious_patterns:
        matches = re.findall(pattern, content)
        if matches:
            violations.append(f"{description} in README ({matches[0][:30]}...)")

    assert not violations, (
        "README contains credentials that look real:\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nUse obviously fake placeholders like 'YOUR_CLIENT_ID_HERE'."
    )
