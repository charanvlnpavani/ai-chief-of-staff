"""Architecture rules, enforced in CI.

Domain modules (and the AI layer) may use another module only through its public
`service`, `schemas` or `ai_tools` modules, never its models, repositories or routers.
"""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
PUBLIC_SURFACES = {"service", "schemas", "ai_tools"}


def _owner(path: Path) -> str | None:
    relative = path.relative_to(APP).parts
    if relative[0] == "modules" and len(relative) > 1:
        return relative[1]
    return relative[0]  # e.g. "ai", "api", "core"


def _violations_in(path: Path) -> list[str]:
    owner = _owner(path)
    problems: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        parts = node.module.split(".")
        if parts[:2] != ["app", "modules"] or len(parts) < 3:
            continue
        target = parts[2]
        if target == owner:
            continue
        # "from app.modules.x.service import f" or "from app.modules.x import service"
        surfaces = {parts[3]} if len(parts) >= 4 else {alias.name for alias in node.names}
        if not surfaces <= PUBLIC_SURFACES:
            problems.append(f"{path.relative_to(APP)} imports {node.module} {sorted(surfaces)}")
    return problems


def test_cross_module_access_goes_through_public_surfaces() -> None:
    checked_roots = [APP / "modules", APP / "ai"]
    violations: list[str] = []
    for root in checked_roots:
        if root.exists():
            for path in root.rglob("*.py"):
                violations.extend(_violations_in(path))
    assert not violations, "\n".join(violations)
