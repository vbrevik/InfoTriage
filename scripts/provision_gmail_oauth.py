#!/usr/bin/env python3
"""provision_gmail_oauth.py — one-time Gmail OAuth2 setup for InfoTriage.

Runs the InstalledAppFlow browser-based OAuth2 consent flow, obtains a
refresh token with the minimal read-only Gmail scopes (D-06), and idempotently
writes GMAIL_OAUTH2_REFRESH_TOKEN to .env (D-07).

Run ONCE on the operator machine before `docker compose up`:
    python3 scripts/provision_gmail_oauth.py

Prerequisites:
    pip install google-auth-oauthlib
    A `client_secrets.json` (OAuth 2.0 Desktop App credentials) downloaded
    from https://console.cloud.google.com/apis/credentials

Security:
    - Only gmail.readonly + gmail.metadata scopes are requested (D-06, NF-4).
    - The refresh token value is written to .env (which is gitignored) but is
      NEVER printed to stdout (NF-6, T-04-11).
    - client_secrets.json stays on disk; it is not embedded in this script
      and must be kept out of git (add to .gitignore if not already listed).
"""

import pathlib
import re
import sys

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.metadata",
    # Read-only scopes only — mutating scopes are not requested (D-06, ADR-008)
]

CLIENT_SECRETS = pathlib.Path("client_secrets.json")
ENV_PATH = pathlib.Path(".env")


def _check_client_secrets() -> None:
    if not CLIENT_SECRETS.exists():
        print(
            f"ERROR: {CLIENT_SECRETS} not found.\n"
            "Download OAuth 2.0 Desktop App credentials from:\n"
            "  https://console.cloud.google.com/apis/credentials\n"
            "and save as client_secrets.json in the project root."
        )
        sys.exit(1)


def _run_flow() -> str:
    """Run InstalledAppFlow and return the refresh token (not printed)."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print(
            "ERROR: google-auth-oauthlib is not installed.\n"
            "Run: pip install google-auth-oauthlib"
        )
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS), SCOPES)
    # port=0 lets the OS pick a free port for the local redirect server
    creds = flow.run_local_server(port=0)

    if not creds.refresh_token:
        print(
            "ERROR: No refresh token returned.\n"
            "This can happen when consent has been granted before.\n"
            "Revoke existing permissions at https://myaccount.google.com/permissions\n"
            "and re-run this script."
        )
        sys.exit(1)

    return creds.refresh_token


def _write_to_env(token: str) -> None:
    """Idempotently write GMAIL_OAUTH2_REFRESH_TOKEN to .env.

    - If the key already exists, the line is replaced in-place.
    - If the file does not exist, it is created.
    - The token value is never echoed to stdout (NF-6, T-04-11).
    """
    env_content = ENV_PATH.read_text() if ENV_PATH.exists() else ""

    # Remove any existing GMAIL_OAUTH2_REFRESH_TOKEN line
    env_content = re.sub(
        r"^GMAIL_OAUTH2_REFRESH_TOKEN=.*$", "", env_content, flags=re.MULTILINE
    )
    # Strip trailing whitespace and append the new value
    env_content = env_content.rstrip() + f"\nGMAIL_OAUTH2_REFRESH_TOKEN={token}\n"

    ENV_PATH.write_text(env_content)


def main() -> None:
    _check_client_secrets()
    print("Opening browser for Gmail OAuth2 consent flow …")
    print(f"Requesting scopes: {', '.join(SCOPES)}")
    token = _run_flow()  # blocks until browser flow completes

    _write_to_env(token)
    # Confirm success WITHOUT printing the token value (NF-6)
    print("Refresh token written to .env as GMAIL_OAUTH2_REFRESH_TOKEN.")
    print("You can now start the gmail-mcp-server container with `docker compose up gmail-mcp-server`.")


if __name__ == "__main__":
    main()
