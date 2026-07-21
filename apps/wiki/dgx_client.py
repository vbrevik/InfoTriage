#!/usr/bin/env python3
"""dgx_client.py — DGX-backed synthesis backend for heavy recall/wiki tasks.

Implements the ``RecallBackend`` protocol used by ``apps/triage/recall.py`` and the
auto-wiki generator. DGX is reserved for heavy synthesis (larger context, longer
generations) per ADR-004; routine tasks stay on the local LLM backend.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Protocol, cast


class RecallBackend(Protocol):
    """Protocol for a synthesis backend used by recall and the wiki generator."""

    def synthesize(self, messages: list[dict], max_tokens: int = 800) -> str:
        """Return synthesized text for the given OpenAI-style ``messages``."""
        ...


# Matches reasoning/thinking tokens produced by some DGX models of the form
# " thinking ... ]". If the deployed DGX model uses a different delimiter,
# adjust this pattern or disable stripping by passing a no-op compile.
_THINK_RE = re.compile(r" thinking.*?\]", re.S)

DEFAULT_DGX_BASE_URL = "http://192.168.10.2:8000/v1"
DEFAULT_DGX_MODEL = "model"
DEFAULT_DGX_MAX_TOKENS = 4096


class DGXSynthesisBackend:
    """Heavy synthesis backend that routes chat completions to DGX Spark."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str = DEFAULT_DGX_MODEL,
        default_max_tokens: int = DEFAULT_DGX_MAX_TOKENS,
        timeout: int = 600,
    ) -> None:
        raw_base = base_url or os.environ.get("DGX_BASE_URL", DEFAULT_DGX_BASE_URL)
        assert raw_base is not None
        self.base_url = raw_base.rstrip("/")
        self.api_key = api_key or os.environ.get("DGX_API_KEY", "omlx")
        self.model = model
        self.default_max_tokens = default_max_tokens
        self.timeout = timeout

    def synthesize(self, messages: list[dict], max_tokens: int = 800) -> str:
        """POST ``messages`` to the DGX chat/completions endpoint and return content.

        ``max_tokens`` is boosted to ``default_max_tokens`` (default 4096) when the
        caller requests fewer, because heavy synthesis on DGX needs headroom for
        longer responses.
        """
        effective_max = max(max_tokens, self.default_max_tokens)
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": effective_max,
        }
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            response = json.load(r)

        content = cast(str, response["choices"][0]["message"]["content"])
        # Strip reasoning tokens if the model emitted them.
        return _THINK_RE.sub("", content).strip()
