"""07-04 dep-list-regression cross-check (Phase 7 follow-up).

The transitive deps that `contracts/__init__.py` eagerly imports now live in
TWO places that must stay in sync:

  1. ``libs/contracts/pyproject.toml`` — ``[project].dependencies`` array.
     Authoritative source for `pip install -e libs/contracts` (dev / out-of-Docker).

  2. Every ``apps/*/requirements.txt`` that ships a service which imports
     ``contracts`` (directly OR via a Dockerfile that installs libs/contracts).
     Authoritative source for Docker images (which install contracts with
     ``--no-deps``; transitive runtime deps must be hand-pasted).

A future addition to ``contracts/__init__.py`` (e.g. a new transport with
import-time deps) would require editing N+1 files. This test fires the moment
ONE app's ``requirements.txt`` falls behind the pyproject declaration.

Closes the regression class surfaced in Phase 7 07-03 (3 services crashed
because their reqs.txt was missing transitive deps). See
``.planning/phases/07-ops-cutover/07-03-SUMMARY.md`` for the prior incident.
"""
import re
import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_TOML = PROJECT_ROOT / "libs/contracts" / "pyproject.toml"
APPS_DIR = PROJECT_ROOT / "apps"

# Matches the leading package name on a deps line (TOML array entry OR pip
# reqs.txt entry), regardless of which version specifier follows. Examples:
#   "pydantic>=2.0"            ->  "pydantic"
#   "aio-pika>=9.6,<10"        ->  "aio-pika"
#   "PyYAML>=6.0"              ->  "PyYAML"
_PACKAGE_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.+-]*)")

# Catches `import contracts` and `from contracts import X` (NOT
# `from contracts.X import Y` — that's a sub-module access; the sub-import
# still requires the package to be installed, but if `import contracts`
# appears anywhere in the app's source tree, the app must list the deps).
_CONTRACTS_IMPORT_RE = re.compile(
    r"""^[^#\n]*\b(?:import|from)\s+contracts\b""", re.MULTILINE
)

# Catches imports of sibling libs in libs/, e.g. `from libs.ingest_common...`.
# Note the word-boundary after `<X>` (between the lib name and the next char)
# — `libs.ingest_common_X` won't match. Treats `import libs.<X>` and
# `from libs.<X> import Y` identically (both forms resolve the package).
_LIBS_IMPORT_RE = re.compile(
    r"""\b(?:import|from)\s+libs\.([A-Za-z0-9_]+)\b"""
)


def _contracts_dep_names() -> set[str]:
    """Normalized package names declared in libs/contracts/pyproject.toml."""
    with CONTRACTS_TOML.open("rb") as fh:
        deps = tomllib.load(fh).get("project", {}).get("dependencies", []) or []
    out: set[str] = set()
    for d in deps:
        m = _PACKAGE_RE.match(d)
        if m:
            out.add(m.group(1).lower())
    return out


LIBS_DIR = PROJECT_ROOT / "libs"


def _transitively_consumes_contracts(app_dir: Path) -> bool:
    """True if the app imports a sibling lib whose own pyproject.toml declares
    ``contracts`` as a dep. Catches the case where the app never mentions
    contracts itself but pulls it in through, e.g., ``libs.ingest_common``.

    Strategy: scan the app's .py files for `from libs.<X>` (and the parallel
    `import libs.<X>`), then for each candidate lib, read libs/<X>/pyproject.toml
    and check whether its ``[project].dependencies`` array contains anything
    that would resolve to the ``contracts`` package on install. (We don't
    normalize version specifiers \u2014 any dep line that starts with the literal
    substring ``contracts`` matches. Cheap + good-enough for this repo's
    conventions.)
    """
    siblings: set[str] = set()
    for py in app_dir.rglob("*.py"):
        for m in _LIBS_IMPORT_RE.finditer(py.read_text(encoding="utf-8", errors="ignore")):
            siblings.add(m.group(1))
    for lib_name in siblings:
        lib_pyproject = LIBS_DIR / lib_name / "pyproject.toml"
        if not lib_pyproject.exists():
            continue
        with lib_pyproject.open("rb") as fh:
            deps = tomllib.load(fh).get("project", {}).get("dependencies", []) or []
        if any(
            m and m.group(1).lower() == "contracts"
            for m in (_PACKAGE_RE.match(d) for d in deps)
        ):
            return True
    return False


def _apps_consuming_contracts() -> list[Path]:
    """Return ``apps/*/requirements.txt`` for services that need contracts deps.

    A service needs the transitive deps in its reqs.txt if EITHER:
      (A) ANY .py file in the app directly imports ``contracts``; OR
      (B) The app's Dockerfile installs ``libs/contracts`` (even if the app's
          own source doesn\\'t import contracts — e.g. apps/ingest-imap uses
          ``libs/ingest_common`` which itself imports ``contracts``; the
          Dockerfile installs contracts so the runtime import resolves).
    """
    out: list[Path] = []
    for req in APPS_DIR.glob("*/requirements.txt"):
        app = req.parent
        py_uses = any(
            _CONTRACTS_IMPORT_RE.search(p.read_text(encoding="utf-8", errors="ignore"))
            for p in app.rglob("*.py")
        )
        dockerfile = app / "Dockerfile"
        docker_uses = dockerfile.exists() and any(
            token in dockerfile.read_text(encoding="utf-8", errors="ignore")
            for token in ("libs/contracts", "build/contracts")
        )
        # (C) Transitive via a sibling libs/* module that itself depends on
        # contracts. Closes the future-proofing gap for any future indirect-
        # only service that never names `contracts` or `libs/contracts` in its
        # own source/Dockerfile but pulls contracts in through a sibling lib.
        transitive = _transitively_consumes_contracts(app)
        if py_uses or docker_uses or transitive:
            out.append(req)
    return sorted(out, key=lambda p: p.parent.name)


@pytest.mark.parametrize(
    "req_txt",
    _apps_consuming_contracts(),
    ids=lambda p: p.parent.name,
)
def test_contracts_deps_in_every_consuming_app_reqs(req_txt: Path) -> None:
    """Every dep declared in libs/contracts must be re-listed here."""
    contract_deps = _contracts_dep_names()
    app_deps: set[str] = set()
    for raw in req_txt.read_text(encoding="utf-8").splitlines():
        # Drop inline comments (`# foo`) then extract the leading package name.
        stripped = raw.split("#", 1)[0].strip()
        m = _PACKAGE_RE.match(stripped)
        if m:
            app_deps.add(m.group(1).lower())

    missing = contract_deps - app_deps
    assert not missing, (
        f"{req_txt.relative_to(PROJECT_ROOT)} is missing contracts transitive "
        f"dep(s) {sorted(missing)} declared in libs/contracts/pyproject.toml. "
        f"Each apps/* Dockerfile installs contracts with --no-deps, so the "
        f"runtime container must list every dep explicitly. Add each missing "
        f"dep to {req_txt.parent.name}/requirements.txt."
    )
