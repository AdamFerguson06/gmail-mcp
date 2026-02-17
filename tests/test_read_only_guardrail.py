"""Guardrail test: ensure no write operations can ever be introduced.

Scans all source files for Gmail API mutating methods and non-readonly scopes.
If this test fails, someone is trying to add write operations — which must
never happen in this repo.

CRITICAL SECURITY: This tool is READ-ONLY ONLY.
"""

import ast
from pathlib import Path

SRC_DIR = Path(__file__).parent.parent / "src" / "gmail_reader"

# Gmail API methods that perform mutations
# These should NEVER appear in source code
MUTATING_GMAIL_METHODS = [
    "send",  # Send email
    "modify",  # Modify labels/metadata
    "trash",  # Move to trash
    "untrash",  # Restore from trash
    "delete",  # Permanently delete
    "insert",  # Insert message
    "import_",  # Import message
    "batchModify",  # Batch modify labels
    "batchDelete",  # Batch delete
]

# Gmail API methods that are allowed (read-only)
ALLOWED_GMAIL_METHODS = [
    "list",  # List messages/threads
    "get",  # Get message/thread details
    "getProfile",  # Get user profile
    "batchGet",  # Batch get messages
]

# OAuth scopes that are forbidden (write operations)
FORBIDDEN_SCOPES = [
    "gmail.send",
    "gmail.modify",
    "gmail.insert",
    "gmail.compose",
    "gmail.settings.basic",
    "gmail.settings.sharing",
]


def _get_all_python_files():
    return list(SRC_DIR.glob("**/*.py"))


def test_no_mutating_method_calls():
    """No source file should call Gmail API mutating methods."""
    violations = []

    for py_file in _get_all_python_files():
        content = py_file.read_text()

        for method in MUTATING_GMAIL_METHODS:
            # Check for method calls: .send(, .modify(, etc.
            if f".{method}(" in content or f".{method} (" in content:
                violations.append(f"{py_file.name}: calls '.{method}()'")

    assert not violations, (
        "WRITE OPERATION DETECTED — This repo is strictly read-only.\n"
        "Violations:\n" + "\n".join(f"  - {v}" for v in violations)
    )


def test_only_readonly_scope():
    """Verify only gmail.readonly scope is used in auth.py."""
    auth_file = SRC_DIR / "auth.py"

    if not auth_file.exists():
        raise FileNotFoundError(f"auth.py not found at {auth_file}")

    content = auth_file.read_text()

    # Must have gmail.readonly
    assert (
        "gmail.readonly" in content
    ), "Missing gmail.readonly scope in auth.py"

    # Extract SCOPES constant value (check only the actual scope definition, not comments)
    # Look for SCOPES = ["..."] or SCOPES = ['...']
    import re
    scopes_match = re.search(r'SCOPES\s*=\s*\[(.*?)\]', content, re.DOTALL)
    assert scopes_match, "SCOPES constant not found in auth.py"

    scopes_value = scopes_match.group(1)

    # Must NOT have any forbidden scopes in the SCOPES value
    for scope in FORBIDDEN_SCOPES:
        assert scope not in scopes_value, (
            f"BLOCKED: {scope} scope found in SCOPES constant. "
            "Only gmail.readonly is allowed."
        )


def test_only_allowed_api_methods():
    """AST parse to verify only list/get/batchGet methods called.

    Scans all source files for API method calls and ensures only
    read-only methods are used.
    """
    violations = []

    for py_file in _get_all_python_files():
        try:
            tree = ast.parse(py_file.read_text())
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                attr = node.func.attr

                # Skip allowed methods and common helper methods
                if attr in ALLOWED_GMAIL_METHODS or attr in [
                    "execute",
                    "build",
                    "users",
                    "messages",
                    "threads",
                    "labels",
                ]:
                    continue

                # Check if this looks like a Gmail API call
                # (calling methods on service objects)
                if isinstance(node.func.value, ast.Name):
                    var_name = node.func.value.id
                    if "service" in var_name.lower():
                        violations.append(
                            f"{py_file.name}:{node.lineno}: calls '{var_name}.{attr}()'"
                        )
                elif isinstance(node.func.value, ast.Call):
                    # Chain calls like service.users().messages().XXXX()
                    if attr not in ALLOWED_GMAIL_METHODS + ["execute"]:
                        # Check if it's a mutating method
                        if attr in MUTATING_GMAIL_METHODS:
                            violations.append(
                                f"{py_file.name}:{node.lineno}: calls mutating method '.{attr}()'"
                            )

    assert not violations, (
        "UNEXPECTED API METHOD — only list/get/batchGet are allowed.\n"
        "Violations:\n" + "\n".join(f"  - {v}" for v in violations)
    )


def test_scopes_constant_not_modified():
    """Verify SCOPES constant in auth.py hasn't been tampered with."""
    auth_file = SRC_DIR / "auth.py"
    content = auth_file.read_text()

    # Find SCOPES assignment
    lines = content.splitlines()
    scopes_line = None

    for line in lines:
        if line.strip().startswith("SCOPES = ["):
            scopes_line = line
            break

    assert scopes_line is not None, "SCOPES constant not found in auth.py"

    # Must be exactly gmail.readonly
    assert (
        'https://www.googleapis.com/auth/gmail.readonly' in scopes_line
    ), "gmail.readonly scope missing or modified"

    # Must be a single-element list
    assert (
        scopes_line.count("https://") == 1
    ), "Multiple scopes detected in SCOPES constant"
