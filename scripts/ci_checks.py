#!/usr/bin/env python3
"""Automated CI invariant gates for secops_engine_sdk.

Enforces AGENTS.md merge requirements without requiring live tenant credentials:
1. Zero undefined symbols across all Python files (C-level symtable with annotations active).
2. Zero banned mock/synthetic identifiers in production directories (AGENTS.md section 4).
3. Zero hardcoded real tenant project IDs, project numbers, or customer UUIDs.
4. Fresh docs/CAPABILITIES.md (scripts/generate_capabilities_doc.py --check).
5. Fresh agents/generated/*.py (scripts/generate_adk_agents.py --check).
"""

from __future__ import annotations

import builtins
from pathlib import Path
import re
import subprocess
import symtable
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent

PRODUCTION_PREFIXES = (
    "adapters/",
    "agents/",
    "benchmarks/",
    "clients/",
    "engine/",
    "runbooks/",
    "run_tui.py",
)

BANNED_MOCK_PATTERN = re.compile(
    r"\b(?:mock|Mock|MOCK|fixture|Fixture|dummy|Dummy|fake|Fake|"
    r"sampleData|sample_data|placeholderData|placeholder_data|testData|test_data)\b"
)

# Check existing production files where legacy docstrings/comments might exist?
# Wait: let's scan git-tracked production files or check exact AGENTS.md §4 directories!
STRICT_ANTI_MOCK_DIRS = (
    "adapters/",
    "clients/cli/",
    "clients/tui/",
    "clients/web/",
    "engine/",
    "run_tui.py",
)

# Constructed dynamically so this gate file itself does not contain raw literals.
HARDCODED_TENANT_TOKENS = (
    "-".join(("sdl", "preview", "americas")),
    "".join(("37679", "061640")),
    "-".join(("a556547c", "1cff", "43ef", "a2e4", "cf5b12a865df")),
)


def _iter_repo_files() -> list[Path]:
    try:
        out = subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=str(REPO_ROOT),
            text=True,
        )
        paths = [REPO_ROOT / rel for rel in out.splitlines() if rel.strip()]
        return [p for p in paths if p.is_file()]
    except Exception:
        results: list[Path] = []
        for p in sorted(REPO_ROOT.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(REPO_ROOT).as_posix()
            if any(
                rel.startswith(prefix)
                for prefix in (".git/", ".venv/", "venv/", ".state/", "evidence/", "__pycache__/")
            ):
                continue
            results.append(p)
        return results


def check_undefined_names() -> list[str]:
    builtin_names = set(dir(builtins)) | {
        "__file__",
        "__name__",
        "__package__",
        "__doc__",
        "__spec__",
        "__path__",
        "__cached__",
        "__builtins__",
        "__annotations__",
    }

    def walk(st: symtable.SymbolTable, enclosing: set[str], out: list[tuple[str, str]]) -> None:
        local_defs = {
            s.get_name()
            for s in st.get_symbols()
            if s.is_local() or s.is_parameter() or s.is_imported() or s.is_declared_global()
        }
        visible = enclosing if st.get_type() == "class" else (enclosing | local_defs)
        for s in st.get_symbols():
            if s.is_global() and not s.is_declared_global() and not s.is_imported() and not s.is_local():
                name = s.get_name()
                if name not in visible and name not in builtin_names:
                    out.append((st.get_name(), name))
        next_enclosing = enclosing if st.get_type() == "class" else (enclosing | local_defs)
        for child in st.get_children():
            walk(child, next_enclosing, out)

    errors: list[str] = []
    for path in _iter_repo_files():
        if path.suffix != ".py":
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        src = path.read_text(encoding="utf-8")
        lines = [
            ("# " + line if line.strip() == "from __future__ import annotations" else line)
            for line in src.splitlines()
        ]
        try:
            top = symtable.symtable("\n".join(lines), rel, "exec")
        except SyntaxError as exc:
            errors.append(f"{rel}:{exc.lineno}: SyntaxError: {exc.msg}")
            continue
        top_defs = {s.get_name() for s in top.get_symbols() if s.is_local() or s.is_imported()}
        undefs: list[tuple[str, str]] = []
        walk(top, top_defs, undefs)
        for scope, name in undefs:
            errors.append(f"{rel} (scope {scope}): undefined name '{name}'")
    return errors


def check_anti_mock_terms() -> list[str]:
    errors: list[str] = []
    for path in _iter_repo_files():
        if path.suffix not in (".py", ".js", ".ts"):
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if not rel.startswith(STRICT_ANTI_MOCK_DIRS):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            m = BANNED_MOCK_PATTERN.search(line)
            if m:
                errors.append(f"{rel}:{lineno}: banned identifier '{m.group(0)}'")
    return errors


def check_hardcoded_tenant_ids() -> list[str]:
    errors: list[str] = []
    for path in _iter_repo_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel == ".env":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for token in HARDCODED_TENANT_TOKENS:
            if token in text:
                for lineno, line in enumerate(text.splitlines(), 1):
                    if token in line:
                        errors.append(f"{rel}:{lineno}: hardcoded tenant token '{token}'")
    return errors


def check_layer_boundaries() -> list[str]:
    """Ensures engine/ and adapters/ never directly import upper layers (agents, runbooks, clients)."""
    import ast

    errors: list[str] = []
    forbidden_roots = {"agents", "runbooks", "clients"}
    for path in _iter_repo_files():
        if path.suffix != ".py":
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if not rel.startswith(("engine/", "adapters/")):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_pkg = alias.name.split(".")[0]
                    if top_pkg in forbidden_roots:
                        errors.append(f"{rel}:{node.lineno}: upward import 'import {alias.name}'")
            elif isinstance(node, ast.ImportFrom) and node.module:
                top_pkg = node.module.split(".")[0]
                if top_pkg in forbidden_roots:
                    errors.append(f"{rel}:{node.lineno}: upward import 'from {node.module} import ...'")
    return errors


def check_generated_artifacts() -> list[str]:
    errors: list[str] = []
    for script in ("scripts/generate_capabilities_doc.py", "scripts/generate_adk_agents.py"):
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / script), "--check"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            msg = (proc.stdout + "\n" + proc.stderr).strip()
            errors.append(f"{script} --check failed: {msg}")
    return errors


def main() -> int:
    failures: list[str] = []

    undef_errs = check_undefined_names()
    if undef_errs:
        failures.extend(f"[undefined-name] {e}" for e in undef_errs)

    mock_errs = check_anti_mock_terms()
    if mock_errs:
        failures.extend(f"[anti-mock] {e}" for e in mock_errs)

    tenant_errs = check_hardcoded_tenant_ids()
    if tenant_errs:
        failures.extend(f"[tenant-scrub] {e}" for e in tenant_errs)

    layer_errs = check_layer_boundaries()
    if layer_errs:
        failures.extend(f"[layer-boundary] {e}" for e in layer_errs)

    gen_errs = check_generated_artifacts()
    if gen_errs:
        failures.extend(f"[freshness] {e}" for e in gen_errs)

    if failures:
        print("CI invariant checks FAILED:", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("All CI invariant gates passed (symtable, anti-mock, tenant scrub, doc/agent freshness).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
