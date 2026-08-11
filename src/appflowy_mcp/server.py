"""AppFlowyMCP — the MCP server itself.

Exposes the AppFlowy Cloud REST API as MCP tools, grouped by domain. Tools are
named ``appflowy_*`` with a consistent shape, return only the payload from the
AppFlowy wrapper (``{code, data, message}`` → ``data``), and never leak the
credential used to talk to AppFlowy — the oauth-agents layer in front owns
client-facing auth.

Run it locally:

    fastmcp run src/appflowy_mcp/server.py  --transport http --port 8000
"""

from __future__ import annotations

import os

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from appflowy_mcp.client import AppFlowyClient, AppFlowyError
from appflowy_mcp.collab import CollabDecoder

mcp = FastMCP(
    "appflowy",
    instructions=(
        "Tools for Moritz's self-hosted AppFlowy Cloud instance. Read the "
        "workspace tree first (appflowy_list_workspaces / "
        "appflowy_get_workspace_tree) to learn view ids, then act on "
        "documents, databases, and rows by id. Content lives in Yjs collab; "
        "appflowy_get_document_content decodes it to plain text."
    ),
)


def get_client() -> AppFlowyClient:
    base = os.environ.get("APPFLOWY_BASE_URL")
    email = os.environ.get("APPFLOWY_EMAIL")
    password = os.environ.get("APPFLOWY_PASSWORD")
    missing = [n for n, v in (("APPFLOWY_BASE_URL", base), ("APPFLOWY_EMAIL", email), ("APPFLOWY_PASSWORD", password)) if not v]
    if missing:
        raise AppFlowyError(f"Missing environment: {', '.join(missing)}")
    return AppFlowyClient(base or "", email or "", password or "")


# Lazy: only constructed on first tool call, so importing the module (e.g. in
# tests, or the FastMCP metadata listing) never requires live credentials.
_client: AppFlowyClient | None = None


def client() -> AppFlowyClient:
    global _client
    if _client is None:
        _client = get_client()
    return _client


# --------------------------------------------------------------------------
# Workspace & navigation
# --------------------------------------------------------------------------


@mcp.tool
def appflowy_get_user_profile() -> dict:
    """Return the profile of the account the MCP uses, including the latest workspace id."""
    return client().request("GET", "/api/user/profile")


@mcp.tool
def appflowy_list_workspaces() -> list | dict:
    """List all workspaces the account can see, with ids, names, and roles."""
    return client().request("GET", "/api/workspace")


@mcp.tool
def appflowy_get_workspace_tree(workspace_id: str = Field(description="Workspace id"), depth: int = Field(default=3, description="How many levels of the page tree to fetch"), include_trash: bool = Field(default=False, description="Include trashed views")) -> dict:
    """Return the page tree of a workspace as nested views (spaces, folders, documents, databases).

    Every node carries view_id, name, layout (0 document, 1 grid/database),
    is_space, is_favorite, is_published, and children.
    """
    return client().request("GET", f"/api/workspace/{workspace_id}/view/{workspace_id}", params={"depth": depth})


@mcp.tool
def appflowy_get_workspace_settings(workspace_id: str) -> dict:
    """Return workspace settings (e.g. the configured AI model)."""
    return client().request("GET", f"/api/workspace/{workspace_id}/settings")


@mcp.tool
def appflowy_list_members(workspace_id: str) -> list | dict:
    """List workspace members with their email and role."""
    return client().request("GET", f"/api/workspace/{workspace_id}/member")


@mcp.tool
def appflowy_list_favorites(workspace_id: str) -> list | dict:
    """List the user's favorite pages in a workspace."""
    return client().request("GET", f"/api/workspace/{workspace_id}/favorites")


@mcp.tool
def appflowy_list_trash(workspace_id: str) -> list | dict:
    """List views currently in the workspace recycle bin (with their original parent)."""
    return client().request("GET", f"/api/workspace/{workspace_id}/trash")


# --------------------------------------------------------------------------
# Spaces & pages (views)
# --------------------------------------------------------------------------


@mcp.tool
def appflowy_create_space(workspace_id: str, name: str = Field(description="Name of the new space"), space_icon: str = Field(default="", description="Emoji or URL icon for the space"), space_icon_color: str = Field(default="", description="Color for the space icon"), space_permission: int = Field(default=1, description="0 = PublicToAll, 1 = Private")) -> dict:
    """Create a new space in the workspace and return its view id."""
    return client().request("POST", f"/api/workspace/{workspace_id}/space", json_body={"name": name, "space_icon": space_icon, "space_icon_color": space_icon_color, "space_permission": space_permission})


@mcp.tool
def appflowy_create_page(workspace_id: str, name: str, layout: int = Field(default=0, description="0 = document, 1 = grid/database, 2 = board, 3 = calendar"), parent_view_id: str | None = Field(default=None, description="View to nest the new page under (defaults to the space root)")) -> dict:
    """Create a new page (document, grid, board, or calendar) and return its view id."""
    return client().request("POST", f"/api/workspace/{workspace_id}/page-view", json_body={"name": name, "layout": layout, "parent_view_id": parent_view_id})


@mcp.tool
def appflowy_rename_page(workspace_id: str, view_id: str, name: str) -> dict:
    """Rename a page/view."""
    return client().request("POST", f"/api/workspace/{workspace_id}/page-view/{view_id}/update-name", json_body={"name": name})


@mcp.tool
def appflowy_update_page_icon(workspace_id: str, view_id: str, icon_value: str = Field(description="Icon value, e.g. an emoji such as 🚀, when ty=1"), icon_type: int = Field(default=1, description="Icon type: 0 = n/a, 1 = emoji, 2 = url")) -> dict:
    """Set a page's icon (emoji or URL)."""
    return client().request("POST", f"/api/workspace/{workspace_id}/page-view/{view_id}/update-icon", json_body={"icon": {"ty": icon_type, "value": icon_value}})


@mcp.tool
def appflowy_remove_page_icon(workspace_id: str, view_id: str) -> dict:
    """Remove a page's icon entirely."""
    return client().request("POST", f"/api/workspace/{workspace_id}/page-view/{view_id}/remove-icon", json_body={})


@mcp.tool
def appflowy_move_page(workspace_id: str, view_id: str, new_parent_view_id: str) -> dict:
    """Move a page under a different parent view."""
    return client().request("POST", f"/api/workspace/{workspace_id}/page-view/{view_id}/move", json_body={"new_parent_view_id": new_parent_view_id})


@mcp.tool
def appflowy_toggle_favorite(workspace_id: str, view_id: str, is_favorite: bool = Field(default=True, description="True = favorite this page, False = unfavorite"), is_pinned: bool = Field(default=False, description="Also pin the favorited page to the top of the favorites list")) -> dict:
    """Add or remove a page from favorites, optionally pinning it."""
    return client().request("POST", f"/api/workspace/{workspace_id}/page-view/{view_id}/favorite", json_body={"is_favorite": is_favorite, "is_pinned": is_pinned})


@mcp.tool
def appflowy_move_to_trash(workspace_id: str, view_id: str) -> dict:
    """Move a page to the workspace recycle bin."""
    return client().request("POST", f"/api/workspace/{workspace_id}/page-view/{view_id}/move-to-trash", json_body={})


@mcp.tool
def appflowy_restore_from_trash(workspace_id: str, view_id: str) -> dict:
    """Restore a page from the workspace recycle bin."""
    return client().request("POST", f"/api/workspace/{workspace_id}/page-view/{view_id}/restore-from-trash", json_body={})


@mcp.tool
def appflowy_delete_from_trash(workspace_id: str, view_id: str) -> dict:
    """Permanently delete a page from the recycle bin (irrecoverable)."""
    return client().request("DELETE", f"/api/workspace/{workspace_id}/trash/{view_id}")


@mcp.tool
def appflowy_publish_page(workspace_id: str, view_id: str) -> dict:
    """Publish a page so it gets a public URL."""
    return client().request("POST", f"/api/workspace/{workspace_id}/page-view/{view_id}/publish", json_body={})


@mcp.tool
def appflowy_unpublish_page(workspace_id: str, view_id: str) -> dict:
    """Unpublish a page and remove its public URL."""
    return client().request("POST", f"/api/workspace/{workspace_id}/page-view/{view_id}/unpublish", json_body={})


# --------------------------------------------------------------------------
# Document content
# --------------------------------------------------------------------------


@mcp.tool
def appflowy_get_document_content(workspace_id: str, view_id: str, as_blocks: bool = Field(default=False, description="Return structured blocks instead of plain text")) -> dict:
    """Return the full content of a document page as text (or as blocks).

    Reads the Yjs collab document and renders it top to bottom. Use this to
    see what a document actually says, not just its title.
    """
    data = client().request(
        "GET",
        f"/api/workspace/v1/{workspace_id}/collab/{view_id}",
        params={"collab_type": 0},
        headers={"client-version": "web", "device-id": "appflowy-mcp"},
    )
    doc_state = bytes(data.get("doc_state", []))
    decoder = CollabDecoder(doc_state)
    if as_blocks:
        return {"page_id": view_id, "blocks": decoder.to_blocks()}
    return {"page_id": view_id, "text": decoder.to_text()}


@mcp.tool
def appflowy_append_blocks(
    workspace_id: str,
    view_id: str,
    blocks: list[dict] = Field(description="List of blocks, each {type, data{delta:[{insert: text}]}} — e.g. {'type':'paragraph','data':{'delta':[{'insert':'Hello\\n'}]}}"),
) -> dict:
    """Append server-validated blocks to a document page.

    This is the only high-level write path the AppFlowy API validates; use it
    to add paragraphs, headings, or lists to the end of a document.
    """
    return client().request("POST", f"/api/workspace/{workspace_id}/page-view/{view_id}/append-block", json_body={"blocks": blocks})


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------


@mcp.tool
def appflowy_search(workspace_id: str, query: str, limit: int = Field(default=20, description="Max results")) -> list | dict:
    """Full-text search across a workspace: documents, databases, and rows."""
    return client().request("GET", f"/api/search/{workspace_id}", params={"query": query, "limit": limit})


@mcp.tool
def appflowy_search_pages(workspace_id: str, query: str, limit: int = Field(default=20, description="Max results")) -> list | dict:
    """Full-text search restricted to pages (documents/databases) in a workspace."""
    return client().request("GET", f"/api/search/{workspace_id}/page", params={"query": query, "limit": limit})


# --------------------------------------------------------------------------
# Databases & rows
# --------------------------------------------------------------------------


@mcp.tool
def appflowy_list_databases(workspace_id: str) -> list | dict:
    """List databases in a workspace: each with id and its views (grid etc.)."""
    return client().request("GET", f"/api/workspace/{workspace_id}/database")


@mcp.tool
def appflowy_get_database_fields(workspace_id: str, database_id: str) -> list | dict:
    """List the fields (columns) of a database with their types."""
    return client().request("GET", f"/api/workspace/{workspace_id}/database/{database_id}/fields")


@mcp.tool
def appflowy_create_database_field(workspace_id: str, database_id: str, name: str, field_type: int = Field(default=0, description="0 RichText, 1 Number, 2 DateTime, 3 SingleSelect, 4 MultiSelect, 5 Checkbox, 6 URL, 7 Checklist"), type_option_data: dict | None = Field(default=None, description="Optional type-specific options (e.g. {options: [...]} for selects)")) -> dict:
    """Add a new field (column) to a database."""
    body: dict = {"name": name, "field_type": field_type}
    if type_option_data is not None:
        body["type_option_data"] = type_option_data
    return client().request("POST", f"/api/workspace/{workspace_id}/database/{database_id}/fields", json_body=body)


@mcp.tool
def appflowy_list_database_rows(workspace_id: str, database_id: str) -> list | dict:
    """List row ids of a database. Use appflowy_get_database_rows_detail for content."""
    return client().request("GET", f"/api/workspace/{workspace_id}/database/{database_id}/row")


@mcp.tool
def appflowy_get_database_rows_detail(workspace_id: str, database_id: str, row_ids: str | list[str] = Field(description="Comma-separated row ids, or a JSON list"), with_document: bool = Field(default=False, description="Also return each row's linked inline document")) -> list | dict:
    """Return full content (cells per field) of one or more database rows by id."""
    if isinstance(row_ids, list):
        ids = ",".join(row_ids)
    else:
        ids = row_ids
    params = {"ids": ids, "with_doc": str(with_document).lower()}
    return client().request("GET", f"/api/workspace/{workspace_id}/database/{database_id}/row/detail", params=params)


@mcp.tool
def appflowy_get_database_row(workspace_id: str, database_id: str, row_id: str, with_document: bool = Field(default=False, description="Also return the row's linked inline document")) -> list | dict:
    """Return full content of a single database row by id."""
    return appflowy_get_database_rows_detail(workspace_id, database_id, row_id, with_document)


@mcp.tool
def appflowy_create_database_row(workspace_id: str, database_id: str, cells: dict | None = Field(default=None, description="cells keyed by field id: {fieldId: {data: value}} — omit for an empty row")) -> dict:
    """Create a new row in a database and return its row_id."""
    body: dict = {"cells": cells or {}}
    result = client().request("POST", f"/api/workspace/{workspace_id}/database/{database_id}/row", json_body=body)
    if isinstance(result, str):
        return {"row_id": result}
    return result


@mcp.tool
def appflowy_update_database_row(workspace_id: str, database_id: str, row_id: str, cells: dict | None = Field(default=None, description="cells keyed by field id to update"), pre_hash: str | None = Field(default=None, description="Server-provided row pre_hash (stable idempotency key)")) -> dict:
    """Update an existing database row (PUT, create-or-update with pre_hash) and return its row_id."""
    body: dict = {"cells": cells or {}}
    if pre_hash:
        body["pre_hash"] = pre_hash
    result = client().request("PUT", f"/api/workspace/{workspace_id}/database/{database_id}/row", json_body=body)
    if isinstance(result, str):
        return {"row_id": result}
    return result


# --------------------------------------------------------------------------
# Files & quick notes
# --------------------------------------------------------------------------


@mcp.tool
def appflowy_get_storage_usage(workspace_id: str) -> dict:
    """Return workspace file-storage usage (consumed capacity in bytes)."""
    return client().request("GET", f"/api/file_storage/{workspace_id}/usage")


@mcp.tool
def appflowy_list_quick_notes(workspace_id: str) -> dict:
    """List all quick notes in the workspace."""
    return client().request("GET", f"/api/workspace/{workspace_id}/quick-note")


@mcp.tool
def appflowy_create_quick_note(workspace_id: str, content: str = Field(description="Note text")) -> dict:
    """Create a new quick note with the given content."""
    return client().request("POST", f"/api/workspace/{workspace_id}/quick-note", json_body={"content": content})


def run() -> None:
    """Run the MCP server with streamable HTTP transport (port from PORT env, default 8000)."""
    port = int(os.environ.get("PORT", "8000"))
    mcp.run(transport="http", host="0.0.0.0", port=port)


if __name__ == "__main__":
    run()