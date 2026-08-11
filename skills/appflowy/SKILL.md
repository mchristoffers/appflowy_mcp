---
name: appflowy
description: Use when working with Moritz's self-hosted AppFlowy Cloud (https://appflowy.mchristoffers.dev) through the appflowy-mcp MCP tools. Covers documents, pages, spaces, databases, rows, search, quick notes, favorites, trash, and publishing.
---

# AppFlowy (self-hosted) via appflowy-mcp

The `appflowy-mcp` server exposes tools named `appflowy_*` that talk to the
existing AppFlowy Cloud at `https://appflowy.mchristoffers.dev`. All tools
take a `workspace_id`; most page/database operations additionally take a
`view_id` or `database_id`.

## Agree on the IDs first

AppFlowy ids are opaque UUIDs. Never guess one — look it up each time:

1. `appflowy_list_workspaces` → get `workspace_id` (the account owns one).
2. `appflowy_get_workspace_tree(workspace_id, depth)` → navigate spaces,
   folders and pages. Every node carries `view_id`, `name`, and `layout`
   (0 = document, 1 = grid/database).
3. For a database, use `appflowy_list_databases`/`appflowy_get_database_fields`
   to learn `database_id` and field ids before reading or writing rows.

## Read-then-write

- Prefer read tools before mutating: fetch the tree / a doc / a row, then
  create, rename, append, or move. `appflowy_get_document_content` decodes the
  Yjs document into plain text so you see what a page actually says.
- `appflowy_search(workspace_id, query)` does full-text search across the
  workspace — use it to find a document by content when the title is unknown.

## Writing

- `appflowy_append_blocks` is the only server-validated high-level write for
  document content. Blocks are `{"type": ..., "data": {"delta": [{"insert":
  "text\n"}]}}` — e.g. `paragraph`, `heading`, `bulleted_list`,
  `numbered_list`, `todo_list`, `toggle_list`, `quote`, `callout`, `divider`.
  Appends to the end of the page.
- `appflowy_create_page` (layout 0 = document, 1 = grid) and
  `appflowy_create_space` create new containers.
- Databases: create rows with `appflowy_create_database_row`; update with
  `appflowy_update_database_row` (pass the server's `pre_hash` for a stable
  idempotent key when you have it).

## Destructive actions

- `appflowy_move_to_trash` → reversible via `appflowy_restore_from_trash`.
- `appflowy_delete_from_trash` is irreversible — confirm with the user before
  calling it, and prefer trash/restore over permanent delete.
- `appflowy_unpublish_page` removes a public URL — confirm if the page was
  shared.

## Auth model

The MCP server holds an AppFlowy account internally and logs in itself; you
never see or pass an AppFlowy credential. The connection to the MCP endpoint
(`https://appflowymcp-oauth.mchristoffers.dev/mcp`) is protected by
oauth-agents: log in with the gateway credentials when prompted, and the
client keeps the session.