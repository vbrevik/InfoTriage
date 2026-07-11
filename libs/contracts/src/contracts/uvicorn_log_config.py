"""uvicorn_log_config.py — Python wrapper around the JSON SSOT for uvicorn logging.

The authoritative source is JSON at: ``contracts/uvicorn-log-config.json``.

Two consumers:
  * CLI-launched services — pass ``--log-config /path/to/uvicorn-log-config.json``
    to ``uvicorn`` (loaded directly by uvicorn).
  * Programmatic launches — import ``LOGGING_CONFIG`` from this module and pass
    it as the ``log_config`` kwarg to ``uvicorn.run(...)``.

Why both forms:
  * The JSON keeps the on-disk CLI form DRY — every Dockerfile references the
    same shipped JSON.
  * The dict lets code-driven launches reuse the same JSON without shelling out
    and avoids the awkward ``python -c "..."`` inline one-liner.

The module loads the JSON via ``importlib.resources`` so it works whether the
contracts package was installed as wheel, source-tree, or via ``-e`` (editable).
The JSON file is registered in ``libs/contracts/pyproject.toml`` via
``package-data``.
"""
import json
from importlib import resources
from typing import Any

__all__ = ["LOGGING_CONFIG"]


def _load_logging_config() -> dict[str, Any]:
    with resources.files("contracts").joinpath("uvicorn-log-config.json").open(
        encoding="utf-8"
    ) as f:
        return json.load(f)


LOGGING_CONFIG: dict[str, Any] = _load_logging_config()
