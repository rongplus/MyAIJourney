"""Gmail MCP Server — exposes Gmail tools via Model Context Protocol (stdio transport).

This is a standalone MCP server script launched as a subprocess by the MCP agent
(mcpAgent.py -> native mcp.ClientSession via stdio_client). It provides 4 Gmail tools:

  - send_email(to, subject, body)   : send an email via Gmail
  - search_emails(query, max_results): search emails using Gmail search syntax
  - read_email(email_id)             : read a specific email by ID
  - list_labels()                     : list all Gmail labels

OAuth setup:
  1. Enable Gmail API at https://console.cloud.google.com/apis/library/gmail.googleapis.com
  2. Create OAuth 2.0 credentials (Desktop app type), download as ``credentials.json``
  3. Run a one-time consent flow to generate ``token.json``
  4. Set env var ``GMAIL_TOKEN_PATH`` to the token file path,
     or just place ``token.json`` next to this script.

If credentials are missing, tools return a helpful error message instead of crashing.
"""
import os
import json
import base64
from email.mime.text import MIMEText

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("gmail")


# ---------------------------------------------------------------------------
# Gmail API helpers
# ---------------------------------------------------------------------------

_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def _token_path() -> str:
    """Resolve the Gmail OAuth token file path from env or default location."""
    return os.environ.get(
        "GMAIL_TOKEN_PATH",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.json"),
    )


def _get_gmail_service():
    """Create and return an authenticated Gmail API service instance.

    Raises FileNotFoundError if the OAuth token is not set up.
    """
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    path = _token_path()
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Gmail OAuth token not found at: {path}\n"
            "Please set up Gmail OAuth credentials:\n"
            "  1. Enable Gmail API in Google Cloud Console\n"
            "  2. Create OAuth 2.0 credentials (Desktop app)\n"
            "  3. Complete consent flow to generate token.json\n"
            "  4. Set GMAIL_TOKEN_PATH env var or place token.json next to the server script\n"
            "See: https://developers.google.com/gmail/api/quickstart/python"
        )

    creds = Credentials.from_authorized_user_file(path, _SCOPES)
    return build("gmail", "v1", credentials=creds, static_discovery=False)


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email to a recipient via Gmail.

    Args:
        to: Email address of the recipient.
        subject: Subject line of the email.
        body: Plain text body content of the email.
    """
    try:
        service = _get_gmail_service()
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        result = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )
        return f"Email sent successfully! Message ID: {result.get('id', 'unknown')}"
    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"Failed to send email: {e}"


@mcp.tool()
def search_emails(query: str, max_results: int = 10) -> str:
    """Search emails in Gmail using Gmail search syntax.

    Args:
        query: Gmail search query, e.g. "from:example@gmail.com subject:hello".
        max_results: Maximum number of emails to return (default 10, max 50).
    """
    try:
        max_results = max(1, min(max_results, 50))
        service = _get_gmail_service()
        results = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        messages = results.get("messages", [])
        if not messages:
            return f"No emails found for query: {query}"

        summaries = []
        for msg in messages:
            detail = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
                .execute()
            )
            headers = {
                h["name"]: h["value"]
                for h in detail.get("payload", {}).get("headers", [])
            }
            summaries.append(
                f"ID: {msg['id']} | From: {headers.get('From', '?')} | "
                f"Subject: {headers.get('Subject', '?')} | Date: {headers.get('Date', '?')}"
            )
        return f"Found {len(summaries)} email(s):\n" + "\n".join(summaries)
    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"Failed to search emails: {e}"


@mcp.tool()
def read_email(email_id: str) -> str:
    """Read the full content of a specific email by its Gmail message ID.

    Args:
        email_id: The Gmail message ID (obtainable from search_emails results).
    """
    try:
        service = _get_gmail_service()
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=email_id, format="full")
            .execute()
        )

        headers = {
            h["name"]: h["value"]
            for h in msg.get("payload", {}).get("headers", [])
        }
        subject = headers.get("Subject", "(no subject)")
        sender = headers.get("From", "(unknown)")
        date = headers.get("Date", "(unknown)")

        # Extract plain-text body
        body_text = _extract_body(msg.get("payload", {}))

        snippet = msg.get("snippet", "")
        if not body_text:
            body_text = f"(no plain-text body found)\nSnippet: {snippet}"

        return (
            f"From: {sender}\n"
            f"Date: {date}\n"
            f"Subject: {subject}\n"
            f"\n{body_text[:8000]}"
        )
    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"Failed to read email: {e}"


@mcp.tool()
def list_labels() -> str:
    """List all labels in the user's Gmail account (e.g. INBOX, SENT, custom labels)."""
    try:
        service = _get_gmail_service()
        results = service.users().labels().list(userId="me").execute()
        labels = results.get("labels", [])
        if not labels:
            return "No labels found in this account."
        lines = [f"{l['name']} (id: {l['id']})" for l in labels]
        return f"Found {len(labels)} label(s):\n" + "\n".join(lines)
    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"Failed to list labels: {e}"


# ---------------------------------------------------------------------------
# Body extraction helper
# ---------------------------------------------------------------------------

def _extract_body(payload: dict) -> str:
    """Recursively extract plain-text body from a Gmail message payload."""
    mime = payload.get("mimeType", "")
    body = payload.get("body", {})

    if mime == "text/plain" and "data" in body:
        return base64.urlsafe_b64decode(body["data"]).decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        text = _extract_body(part)
        if text:
            return text

    return ""


# ---------------------------------------------------------------------------
# Entry point — stdio transport for MCP client
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
