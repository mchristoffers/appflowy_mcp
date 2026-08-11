"""AppFlowyMCP — an MCP server for Moritz's self-hosted AppFlowy Cloud.

Talks to the existing AppFlowy instance (https://appflowy.mchristoffers.dev)
through its native GoTrue + HTTP REST API. Owned by the repo; no third-party
MCP adapter involved.

Auth model: the server holds an AppFlowy account (email/password) and logs in
once via GoTrue, then refreshes the token before it expires. Clients of the
MCP server never see these credentials — the oauth-agents layer in front owns
all client-facing auth.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

GOTRUE_TOKEN_URL = "{base}/gotrue/token"


class AppFlowyError(RuntimeError):
    """Raised when the AppFlowy API answers with an application-level error."""


@dataclass
class AuthSession:
    """GoTrue session: access + refresh token plus expiry."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_at: float = 0.0


class AppFlowyClient:
    """Minimal, stateful REST client for the AppFlowy Cloud API.

    One instance holds one GoTrue session. Every request uses the access token
    as a Bearer header and transparently refreshes when it is near expiry.
    """

    def __init__(self, base_url: str, email: str, password: str) -> None:
        if base_url.endswith("/"):
            base_url = base_url[:-1]
        if not base_url.startswith(("http://", "https://")):
            raise AppFlowyError("APPFLOWY_BASE_URL must be an http(s) origin")
        self._base = base_url
        self._email = email
        self._password = password
        self._session: AuthSession | None = None

    # -- auth -----------------------------------------------------------------

    def login(self) -> AuthSession:
        resp = httpx.post(
            GOTRUE_TOKEN_URL.format(base=self._base),
            params={"grant_type": "password"},
            json={"email": self._email, "password": self._password},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if "access_token" not in data:
            raise AppFlowyError(f"GoTrue login failed: {data!r}")
        self._session = AuthSession(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            token_type=data.get("token_type", "bearer"),
            expires_at=float(data.get("expires_at") or (time.time() + int(data.get("expires_in", 3600)))),
        )
        return self._session

    def _ensure_token(self) -> str:
        now = time.time()
        if self._session is None:
            self.login()
        # Refresh five minutes early; a token that dies mid-request is worse.
        assert self._session is not None
        if now > self._session.expires_at - 300:
            self._refresh()
        return self._session.access_token

    def _refresh(self) -> None:
        if not self._session or not self._session.refresh_token:
            self.login()
            return
        resp = httpx.post(
            GOTRUE_TOKEN_URL.format(base=self._base),
            params={"grant_type": "refresh_token"},
            json={"refresh_token": self._session.refresh_token},
            timeout=30,
        )
        if resp.status_code >= 400:
            # Refresh token rejected (e.g. rotated or expired) — full re-login.
            self.login()
            return
        data = resp.json()
        self._session = AuthSession(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", self._session.refresh_token),
            token_type=data.get("token_type", "bearer"),
            expires_at=float(data.get("expires_at") or (time.time() + int(data.get("expires_in", 3600)))),
        )

    # -- requests -------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | list | None = None,
        headers: dict | None = None,
    ) -> dict | list:
        """Send an authenticated request and return the parsed JSON body.

        AppFlowy wraps most responses as ``{"code": 0, "data": ..., "message":
        ...}``; the payload is unwrapped here so every tool sees ``data``
        directly. Non-zero ``code`` raises AppFlowyError with the message.
        """
        url = f"{self._base}{path}"
        merged_headers = {
            "Authorization": f"Bearer {self._ensure_token()}",
            "Content-Type": "application/json",
            "client-version": "mcp/1.0",
            "device-id": "appflowy-mcp",
        }
        if headers:
            merged_headers.update(headers)
        resp = httpx.request(
            method,
            url,
            params=params,
            json=json_body,
            headers=merged_headers,
            timeout=60,
        )
        if resp.status_code == 401:
            # Possibly stale token — refresh once and retry.
            self._session = None
            merged_headers["Authorization"] = f"Bearer {self._ensure_token()}"
            resp = httpx.request(
                method, url, params=params, json=json_body, headers=merged_headers, timeout=60
            )
        if resp.status_code >= 400:
            raise AppFlowyError(f"{method} {path} -> HTTP {resp.status_code}: {resp.text[:500]}")
        payload = resp.json()
        if isinstance(payload, dict) and "code" in payload and payload.get("code") != 0:
            raise AppFlowyError(f"{method} {path} -> {payload.get('code')}: {payload.get('message', payload)}")
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload