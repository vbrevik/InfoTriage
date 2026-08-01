#!/usr/bin/env python3
"""outbox.py — authenticated ntfy HTTP egress. The only network egress this
phase introduces (T-12-02).

Security: never log the token or the Authorization header value, never log
the full payload — only method, topic, and status code.
"""
from __future__ import annotations

import json
import logging

import httpx

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10.0


class NtfyClient:
    """Minimal authenticated ntfy publisher for the CAT I alert payload."""

    def __init__(self, base_url: str, token: str, topic: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._topic = topic

    async def deliver(self, payload: dict) -> None:
        """POST payload to {base_url}/{topic} with bearer auth + ntfy headers.

        Raises on non-2xx via httpx's raise_for_status().
        """
        url = f"{self._base_url}/{self._topic}"

        sab_excerpt = payload.get("sab_excerpt") or ""
        title = (
            sab_excerpt.splitlines()[0][:80]
            if sab_excerpt
            else (f"CAT {payload.get('cnr_tier', '')} Alert")
        )
        tags = ",".join(
            ["triangular_flag_on_post", *(payload.get("pmseii_tags") or [])]
        )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
            "X-Title": title,
            "X-Priority": "5",
            "X-Tags": tags,
            "X-Click": payload.get("deep_link", ""),
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as http_client:
            response = await http_client.post(
                url, content=json.dumps(payload), headers=headers
            )
        response.raise_for_status()
        # Never log the token/Authorization header value or the full payload (T-12-02).
        log.info(
            "ntfy delivery method=POST topic=%s status=%s",
            self._topic,
            response.status_code,
        )
