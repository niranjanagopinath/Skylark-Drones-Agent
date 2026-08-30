"""
Low-level monday.com GraphQL read client.

Read-only: the runtime never mutates monday. It fetches every item from a board
(paginating through items_page) and returns each item as
{"id", "name", "columns": {column_id: display_text}}.

We read the `text` representation of each column value, which is exactly what we
want for normalization: status -> label, date -> 'YYYY-MM-DD', number -> its
string form. Failures raise `MondayError` so callers can degrade gracefully
instead of surfacing a wrong answer.
"""

from __future__ import annotations

import httpx

from .config import settings


class MondayError(RuntimeError):
    """Raised when monday.com cannot be reached or returns an error."""


_ITEMS_PAGE_QUERY = """
query ($board: [ID!], $limit: Int!) {
  boards(ids: $board) {
    items_page(limit: $limit) {
      cursor
      items { id name column_values { id text } }
    }
  }
}"""

_NEXT_PAGE_QUERY = """
query ($cursor: String!, $limit: Int!) {
  next_items_page(cursor: $cursor, limit: $limit) {
    cursor
    items { id name column_values { id text } }
  }
}"""


class MondayClient:
    def __init__(self, token: str | None = None, url: str | None = None, timeout: float = 60.0):
        self.token = (token or settings.monday_api_token).strip()
        self.url = url or settings.monday_api_url
        self.timeout = timeout

    def _post(self, query: str, variables: dict) -> dict:
        if not self.token:
            raise MondayError("MONDAY_API_TOKEN is not configured.")
        headers = {
            "Authorization": self.token,
            "Content-Type": "application/json",
            "API-Version": "2024-10",
        }
        try:
            resp = httpx.post(
                self.url,
                json={"query": query, "variables": variables},
                headers=headers,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise MondayError(f"Network error contacting monday.com: {exc}") from exc

        if resp.status_code == 401:
            raise MondayError("monday.com rejected the API token (401 Unauthorized).")
        try:
            body = resp.json()
        except ValueError as exc:
            raise MondayError(f"monday.com returned non-JSON (status {resp.status_code}).") from exc
        if body.get("errors"):
            raise MondayError(f"monday.com GraphQL error: {body['errors']}")
        if "data" not in body:
            raise MondayError(f"Unexpected monday.com response: {body}")
        return body["data"]

    def fetch_items(self, board_id: str | int, page_size: int = 500) -> list[dict]:
        """Return all items on a board as {id, name, columns:{col_id: text}}."""
        data = self._post(_ITEMS_PAGE_QUERY, {"board": [str(board_id)], "limit": page_size})
        boards = data.get("boards") or []
        if not boards:
            raise MondayError(f"Board {board_id} not found or not accessible with this token.")
        page = boards[0]["items_page"]
        items = list(page["items"])
        cursor = page["cursor"]

        while cursor:
            data = self._post(_NEXT_PAGE_QUERY, {"cursor": cursor, "limit": page_size})
            page = data["next_items_page"]
            items.extend(page["items"])
            cursor = page["cursor"]

        return [
            {
                "id": it["id"],
                "name": it["name"],
                "columns": {cv["id"]: cv["text"] for cv in it["column_values"]},
            }
            for it in items
        ]

    def ping(self) -> str:
        """Verify connectivity + token. Returns the authenticated account name."""
        data = self._post("query { me { name email } }", {})
        me = data["me"]
        return f"{me['name']} <{me['email']}>"
