"""Fetches tab content from a Google Doc via a service-account credential.

Why a service account (not a bare API key): an API key cannot read
"link-shared" documents — only fully public ones. A service account can read
any doc shared (Viewer) with its ``client_email`` without interactive OAuth
consent, which is what we want for a content-managed site.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

_SCOPES = ['https://www.googleapis.com/auth/documents.readonly']
# Slugs that would collide with the static /chat, /api/* and /static routes.
_RESERVED_SLUGS = {'chat', 'api', 'static'}


@dataclass
class DocTab:
    """A single Google Doc tab rendered as a website page."""

    tab_id: str
    title: str
    slug: str
    content: str


class GoogleDocsServiceError(Exception):
    """Raised when credentials are missing/invalid or the Docs API fails."""


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_-]+', '-', slug)
    return slug.strip('-')


def _safe_slug(title: str, index: int, seen: set[str]) -> str:
    """Return a unique, non-empty, non-reserved slug for a tab.

    Empty/punctuation-only titles fall back to ``page-N``; reserved words get a
    ``-page`` suffix; collisions are disambiguated with a numeric suffix.
    """
    base = _slugify(title) or f'page-{index + 1}'
    if base in _RESERVED_SLUGS:
        base = f'{base}-page'
    slug = base
    suffix = 1
    while slug in seen:
        slug = f'{base}-{suffix}'
        suffix += 1
    seen.add(slug)
    return slug


def _extract_text(tab_body: dict[str, Any]) -> str:
    """Recursively concatenate paragraph and table text from a doc body."""
    lines: list[str] = []
    for element in tab_body.get('content', []):
        paragraph = element.get('paragraph', {})
        if paragraph:
            parts = [
                e.get('textRun', {}).get('content', '')
                for e in paragraph.get('elements', [])
            ]
            lines.append(''.join(parts))
        table = element.get('table', {})
        if table:
            for row in table.get('tableRows', []):
                for cell in row.get('tableCells', []):
                    lines.append(_extract_text(cell))
    return ''.join(lines)


def _flatten_tabs(raw_tabs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Depth-first flatten of tabs and their nested ``childTabs``."""
    flat: list[dict[str, Any]] = []
    for tab in raw_tabs:
        flat.append(tab)
        flat.extend(_flatten_tabs(tab.get('childTabs', [])))
    return flat


def _load_credentials(source: str) -> Any:
    """Build credentials from a file path or inline JSON string."""
    if not source:
        raise GoogleDocsServiceError('GOOGLE_SERVICE_ACCOUNT_JSON is not set.')
    # google-auth ships no type stubs; treat the factory as Any so strict mypy
    # does not flag the untyped calls (and does not demand env-specific ignores).
    credentials: Any = service_account.Credentials
    if os.path.isfile(source):
        return credentials.from_service_account_file(source, scopes=_SCOPES)
    try:
        info = json.loads(source)
    except json.JSONDecodeError as exc:
        raise GoogleDocsServiceError(
            'GOOGLE_SERVICE_ACCOUNT_JSON is neither a file path nor valid JSON.'
        ) from exc
    return credentials.from_service_account_info(info, scopes=_SCOPES)


class GoogleDocsService:
    """Reads a Google Doc's tabs (including nested child tabs) as pages."""

    def __init__(self, service_account_source: str, doc_id: str) -> None:
        self._source = service_account_source
        self._doc_id = doc_id

    def fetch_tabs(self) -> list[DocTab]:
        try:
            creds = _load_credentials(self._source)
            service = build('docs', 'v1', credentials=creds,
                            cache_discovery=False)
            doc = service.documents().get(
                documentId=self._doc_id,
                includeTabsContent=True,
            ).execute()
        except GoogleDocsServiceError:
            raise
        except Exception as exc:
            raise GoogleDocsServiceError(str(exc)) from exc

        tabs: list[DocTab] = []
        seen_slugs: set[str] = set()
        for index, tab in enumerate(_flatten_tabs(doc.get('tabs', []))):
            props = tab.get('tabProperties', {})
            title = props.get('title', 'Untitled')
            tab_id = props.get('tabId', '')
            slug = _safe_slug(title, index, seen_slugs)
            body = tab.get('documentTab', {}).get('body', {})
            content = _extract_text(body)
            tabs.append(DocTab(tab_id=tab_id, title=title, slug=slug,
                               content=content))
        return tabs
