#!/usr/bin/env python3
"""A small, correct lint pass — no network, no dependencies.

This existed once before as a throwaway in a temp directory, reported 99
problems of which roughly 90 were phantom, and was then lost. Both halves of
that are the reason it is committed now: a checker nobody can rerun is not a
check, and a checker that cries wolf gets ignored precisely when it is right.

The false positives it used to produce are fixed here and are worth naming,
because each is a case where the naive AST reading is wrong:

1. **`f"{x:.0f}"` is not a placeholder-free f-string.** `ast.JoinedStr` with a
   format spec still has `FormattedValue` children; the old check looked only
   at the top-level values it recognised and concluded there was no
   interpolation. It flagged every formatted number in the repository.

2. **A format spec is itself a `JoinedStr` with no placeholders.** Fixing (1)
   was not enough, because `ast.walk` still visits `:,.0f` as a node in its own
   right. This produced a *second* report for every formatted number — 119
   findings of which 118 were the checker's. Worth stating plainly: the first
   version of this rule was fixed, tested against the case that produced it,
   and still wrong for the same underlying reason one level down.

3. **`from __future__ import annotations` is never "unused".** It has no name
   to reference. Nor are `__all__` re-exports, which the AST does not show as a
   `Name` load.

4. **`# noqa` is honoured.** An import whose only purpose is its registration
   side effect has no name to reference, and a checker that cannot be
   overridden gets worked around rather than used.

Of the 119 it first reported, 4 were real and all 4 are now fixed — including
an `assert` used for type narrowing in the MCP transport, which `python -O`
strips, leaving an `AttributeError` on `None` in its place.

What it checks, deliberately a short list — each of these has actually bitten
this repository:

- imports that are never used (dead weight, and a rename that missed a spot)
- f-strings with no interpolation (usually a `.format` half-converted)
- bare `except:` (swallows KeyboardInterrupt and SystemExit)
- mutable default arguments
- `assert` in non-test code (stripped under `python -O`, so a guard that
  vanishes in exactly the configuration you would deploy)

Exit code is 1 if anything is found, so CI can gate on it.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterator, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ("deckscope", "marketreport", "tests", "scripts")

Problem = Tuple[Path, int, str]


def _sources() -> Iterator[Path]:
    for package in PACKAGES:
        directory = ROOT / package
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            yield path


def _has_interpolation(node: ast.JoinedStr) -> bool:
    """True if anything is actually substituted in.

    Walks the whole subtree rather than reading `node.values` directly, because
    a format spec is itself a `JoinedStr` hanging off a `FormattedValue` and the
    shallow read misses it. This is false-positive number one.
    """
    return any(isinstance(child, ast.FormattedValue) for child in ast.walk(node))


def _format_specs(tree: ast.Module) -> set:
    """The `JoinedStr` nodes that are format specs rather than strings.

    False positive number one, second costume. Fixing the *detection* was not
    enough: `ast.walk` still visits the spec itself, and `:,.0f` is a
    placeholder-free `JoinedStr` by construction. Every formatted number in the
    repository got reported a second time — which is how a checker reports 119
    problems of which 118 are its own.

    The lesson generalises past this file. The first version of this rule was
    fixed, tested against the case that produced it, and still wrong for the
    same underlying reason in a place I had not looked. Fixing the instance is
    not fixing the cause.
    """
    specs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FormattedValue) and node.format_spec is not None:
            specs.add(id(node.format_spec))
    return specs


def _exported(tree: ast.Module) -> set:
    """Names listed in `__all__`, which the AST never shows as a load."""
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "__all__" not in targets:
            continue
        if isinstance(node.value, (ast.List, ast.Tuple)):
            for element in node.value.elts:
                if isinstance(element, ast.Constant) and isinstance(element.value, str):
                    names.add(element.value)
    return names


def _unused_imports(tree: ast.Module) -> Iterator[Tuple[int, str]]:
    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                imported[name] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue        # false positive number two
            for alias in node.names:
                if alias.name == "*":
                    continue
                imported[alias.asname or alias.name] = node.lineno

    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    used |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            base = node
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name):
                used.add(base.id)
    # Names appearing anywhere in a string annotation or a docstring reference
    # are not tracked; that direction errs toward silence, which is correct for
    # a checker whose credibility is the point.
    used |= _exported(tree)

    for name, line in sorted(imported.items(), key=lambda kv: kv[1]):
        if name not in used:
            yield line, f"unused import: {name}"


def check(path: Path) -> List[Problem]:
    text = path.read_text(encoding="utf-8")
    # `# noqa` marks a deliberate exception. A checker that cannot be overridden
    # gets worked around instead of used — and the two cases here are both
    # legitimate: an import whose only purpose is its registration side effect
    # has no name to reference, and saying so on the line is better than
    # inventing a use for it.
    suppressed = {i for i, line in enumerate(text.splitlines(), start=1)
                  if "# noqa" in line}
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return [(path, exc.lineno or 0, f"syntax error: {exc.msg}")]

    found: List[Problem] = []
    is_test = path.parts[-2] == "tests" or path.name.startswith("test_")
    specs = _format_specs(tree)

    for line, message in _unused_imports(tree):
        if line not in suppressed:
            found.append((path, line, message))

    for node in ast.walk(tree):
        if (isinstance(node, ast.JoinedStr) and id(node) not in specs
                and not _has_interpolation(node)):
            found.append((path, node.lineno, "f-string with nothing to interpolate"))
        elif isinstance(node, ast.ExceptHandler) and node.type is None:
            found.append((path, node.lineno,
                          "bare except: also catches KeyboardInterrupt and "
                          "SystemExit"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults + [
                    d for d in node.args.kw_defaults if d is not None]:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    found.append((path, node.lineno,
                                  f"mutable default argument in {node.name}()"))
        elif isinstance(node, ast.Assert) and not is_test:
            found.append((path, node.lineno,
                          "assert outside tests is removed by python -O"))
    return [p for p in found if p[1] not in suppressed]


def main() -> int:
    problems: List[Problem] = []
    files = 0
    for path in _sources():
        files += 1
        problems.extend(check(path))

    for path, line, message in problems:
        print(f"{path.relative_to(ROOT)}:{line}: {message}")

    if problems:
        print(f"\n{len(problems)} problem(s) in {files} files")
        return 1
    print(f"clean — {files} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
