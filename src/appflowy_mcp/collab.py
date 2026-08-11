"""Decode AppFlowy Yjs collab documents into plain text.

AppFlowy stores every document/row as a Yjs CRDT. The REST API exposes it as
``doc_state`` (a JSON array of bytes) via the collab endpoint. This module
walks that Yjs structure and renders the block tree as readable text, so the
MCP can offer document *content* read-back, not just metadata.

Document schema (as produced by AppFlowy Web / Cloud 0.17):

    data.document
      .blocks          { id: {id, ty, parent, children, external_type, external_id, data(JSON)} }
      .meta.children_map  { children_id: [child_block_id, ...] }
      .meta.text_map      { external_id: YText }
      .page_id         → the root block id

At the moment only the ``blocks``/``children_map``/``text_map`` structure is
walked; block ``data`` (a JSON string of block-specific options) is kept for
block-style output, not parsed per-type.
"""

from __future__ import annotations

from typing import Any, Iterator

from pycrdt import Doc, Map

# Block types that carry rich content worth surfacing in block output.
_KNOWN_TYPES = {
    "paragraph",
    "heading",
    "bulleted_list",
    "numbered_list",
    "todo_list",
    "toggle_list",
    "quote",
    "callout",
    "divider",
    "code_block",
}


class CollabDecoder:
    """Renders one AppFlowy collab document into text and block structures."""

    def __init__(self, doc_state: bytes):
        self._doc = Doc()
        self._doc.apply_update(doc_state)
        data_node = self._doc.get("data", type=Map)
        self._root = data_node.get("document")
        assert isinstance(self._root, Map), "unexpected collab layout"

    @property
    def page_id(self) -> str:
        pid = self._root.get("page_id")
        return pid if isinstance(pid, str) else ""

    def _blocks(self) -> Map:
        b = self._root.get("blocks")
        return b if isinstance(b, Map) else Map()

    def _children_map(self) -> Map:
        meta = self._root.get("meta")
        m = meta.get("children_map") if isinstance(meta, Map) else None
        return m if isinstance(m, Map) else Map()

    def _text_map(self) -> Map:
        meta = self._root.get("meta")
        m = meta.get("text_map") if isinstance(meta, Map) else None
        return m if isinstance(m, Map) else Map()

    def _text_for(self, external_type: str, external_id: Any) -> str:
        if external_type == "text" and external_id:
            tm = self._text_map()
            if external_id in tm:
                node = tm[external_id]
                # YText renders to plain string via str()/to_string
                return str(node)
        return ""

    def _block_iter(self, parent_children_id: str | None) -> Iterator[str]:
        """Yield block ids in document order under a given children node."""
        if parent_children_id is None:
            return
        cm = self._children_map()
        node = cm.get(parent_children_id)
        if node is None:
            return
        for bid in node:  # Yjs array iterates its elements
            yield str(bid)

    def _walk(self, block_id: str, indent: int = 0) -> Iterator[tuple[str, str, str]]:
        """Yield (block_type, text, extra_data_json) per block, depth-first."""
        blocks = self._blocks()
        if block_id not in blocks:
            return
        node = blocks[block_id]
        btype = str(node.get("ty") or node.get("type") or "paragraph")
        text = self._text_for(node.get("external_type"), node.get("external_id"))
        data = node.get("data") or "{}"
        yield btype, text, data
        children_id = node.get("children")
        if isinstance(children_id, str):
            for child in self._block_iter(children_id):
                yield from self._walk(child, indent + 1)

    def to_text(self, max_blocks: int = 200) -> str:
        """Render the document as readable plain text (markdown-ish)."""
        lines: list[str] = []
        for i, (btype, text, _data) in enumerate(self._walk(self.page_id)):
            if i >= max_blocks:
                lines.append(f"… ({i} blocks rendered, truncating)")
                break
            if not text:
                text = {"divider": "———"}.get(btype, "")
            if text:
                lines.append(text)
        return "\n".join(lines)

    def to_blocks(self, max_blocks: int = 200) -> list[dict[str, Any]]:
        """Render the document as structured blocks (type + text + data)."""
        out: list[dict[str, Any]] = []
        for i, (btype, text, data) in enumerate(self._walk(self.page_id)):
            if i >= max_blocks:
                out.append({"type": "truncated", "text": f"{i} blocks rendered", "data": ""})
                break
            out.append({"type": btype, "text": text, "data": data})
        return out