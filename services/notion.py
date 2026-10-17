"""Save words to a Notion database (ported from DutchPal-API Services/NotionService.cs).

Same properties and de-duplication as the .NET service: the name is stored lowercased and
skipped when a page whose Name contains it already exists. Writes go to the signed-in
user's own Notion when they saved one in Settings, otherwise to the default Notion
configured on the server (NOTION_SECRET, NOTION_NOUN_DB_ID, NOTION_VERB_DB_ID).
"""

import os
import re
from dataclasses import dataclass

import httpx
from fastapi import HTTPException

from services.users import UserSettings, decrypt_secret

NOTION_API = "https://api.notion.com/v1/"
NOTION_VERSION = "2022-06-28"
BOLD = re.compile(r"\*\*(.*?)\*\*")


@dataclass
class NotionTarget:
    secret: str
    database_id: str


def notion_target(settings: UserSettings | None, kind: str) -> NotionTarget:
    """Where a `kind` ("noun" or "verb") is saved: the user's own Notion, else the default."""
    if settings is not None and settings.notion_secret_encrypted:
        database_id = getattr(settings, f"notion_{kind}_db_id")
        if not database_id:
            raise HTTPException(status_code=400, detail=f"Add your {kind} database id in Settings first")
        return NotionTarget(decrypt_secret(settings.notion_secret_encrypted), database_id)

    secret, database_id = os.getenv("NOTION_SECRET"), os.getenv(f"NOTION_{kind.upper()}_DB_ID")
    if not secret or not database_id:
        raise HTTPException(status_code=503, detail="Saving to Notion is not configured on this server")
    return NotionTarget(secret, database_id)


async def notion_request(secret: str, method: str, path: str, json: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {secret}", "Notion-Version": NOTION_VERSION}
    async with httpx.AsyncClient(base_url=NOTION_API, headers=headers, timeout=20) as client:
        response = await client.request(method, path, json=json)
    if response.is_error:
        try:
            message = response.json().get("message")
        except ValueError:
            message = None
        raise HTTPException(status_code=502, detail=f"Notion: {message or response.status_code}")
    return response.json()


def rich_text(content: str) -> dict:
    return {"rich_text": [{"text": {"content": content}}]}


def rich_text_with_bold(text: str) -> dict:
    """`**word**` becomes a bold segment, like NotionHelper.ConvertToNotionRichTextWithBold."""
    segments, last = [], 0
    for match in BOLD.finditer(text):
        if match.start() > last:
            segments.append(_segment(text[last : match.start()], bold=False))
        segments.append(_segment(match.group(1), bold=True))
        last = match.end()
    if last < len(text):
        segments.append(_segment(text[last:], bold=False))
    return {"rich_text": segments}


def _segment(content: str, bold: bool) -> dict:
    return {"type": "text", "text": {"content": content}, "annotations": {"bold": bold}}


async def insert_if_not_exists(target: NotionTarget, name: str, properties: dict) -> int:
    """Adds a page unless one with this name exists; returns how many pages were added."""
    lower_name = name.strip().lower()
    query = {"filter": {"property": "Name", "rich_text": {"contains": lower_name}}}
    existing = await notion_request(target.secret, "POST", f"databases/{target.database_id}/query", query)
    if existing["results"]:
        return 0

    properties = {
        "Name": {"title": [{"text": {"content": lower_name}}]},
        **properties,
        "Source": rich_text("API"),
    }
    await notion_request(
        target.secret, "POST", "pages", {"parent": {"database_id": target.database_id}, "properties": properties}
    )
    return 1


async def database_title(secret: str, database_id: str) -> str:
    database = await notion_request(secret, "GET", f"databases/{database_id}")
    return "".join(part.get("plain_text", "") for part in database.get("title", [])) or database_id
