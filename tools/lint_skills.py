#!/usr/bin/env python3
"""Lint LaborShield's skill, methodology, command, and settings files.

Run from anywhere: python3 tools/lint_skills.py

Checks:
- Every SKILL.md (.claude/skills/*, .agents/skills/*) has valid YAML frontmatter
  with non-empty `name`, `description`, and `framework_version` keys
- Every methodology reference file (.claude/skills/arbitration-assistant/0*.md)
  has valid YAML frontmatter with `framework_version`
- Every .claude/commands/*.md starts with a `# /<command-name>` title matching its filename
- .claude/settings.json is valid JSON with a `permissions.allow` list, and any
  `python3 tools/<script>.py` entry points at an existing file in `tools/`

Exit code 0 on success, 1 with a failure list otherwise.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("lint_skills.py requires PyYAML: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent


def rel(path: Path, root: Path = ROOT) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def parse_frontmatter(path: Path, root: Path, errors: list[str]) -> dict | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        errors.append(f"{rel(path, root)}: missing YAML frontmatter (file must start with ---)")
        return None
    end = text.find("\n---", 4)
    if end == -1:
        errors.append(f"{rel(path, root)}: unterminated YAML frontmatter")
        return None
    try:
        data = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        errors.append(f"{rel(path, root)}: frontmatter is not valid YAML: {exc}")
        return None
    if not isinstance(data, dict):
        errors.append(f"{rel(path, root)}: frontmatter did not parse to a mapping")
        return None
    return data


def check_skill(path: Path, root: Path, errors: list[str]) -> None:
    data = parse_frontmatter(path, root, errors)
    if data is None:
        return
    for key in ("name", "description", "framework_version"):
        if not data.get(key):
            errors.append(f"{rel(path, root)}: frontmatter missing required key '{key}'")


def check_methodology_file(path: Path, root: Path, errors: list[str]) -> None:
    data = parse_frontmatter(path, root, errors)
    if data is None:
        return
    if not data.get("framework_version"):
        errors.append(f"{rel(path, root)}: frontmatter missing required key 'framework_version'")


def check_command(path: Path, root: Path, errors: list[str]) -> None:
    lines = path.read_text(encoding="utf-8").lstrip().splitlines()
    first = lines[0] if lines else ""
    expected_prefix = f"# /{path.stem}"
    if not first.startswith(expected_prefix):
        errors.append(
            f"{rel(path, root)}: command file must start with '{expected_prefix}' title (found: {first[:50]!r})"
        )


def check_settings(root: Path, errors: list[str]) -> None:
    path = root / ".claude" / "settings.json"
    if not path.is_file():
        errors.append(".claude/settings.json: file does not exist")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f".claude/settings.json: {exc}")
        return
    if not isinstance(data, dict):
        errors.append(".claude/settings.json: expected top-level JSON value to be an object")
        return
    permissions = data.get("permissions", {})
    if not isinstance(permissions, dict):
        errors.append(".claude/settings.json: expected permissions to be an object")
        return
    allow_list = permissions.get("allow")
    if not isinstance(allow_list, list):
        errors.append(".claude/settings.json: expected permissions.allow to be a list")
        return

    for entry in allow_list:
        if not isinstance(entry, str):
            continue
        m = re.search(r"python3?\s+(tools/[a-zA-Z0-9_.-]+\.py)", entry)
        if m:
            script_rel = m.group(1)
            if not (root / script_rel).is_file():
                errors.append(f".claude/settings.json: permissions.allow references missing tool '{script_rel}'")


def run_lint(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    skills = sorted(root.glob(".claude/skills/*/SKILL.md")) + sorted(root.glob(".agents/skills/*/SKILL.md"))
    methodologies = sorted(root.glob(".claude/skills/*/0*.md"))
    commands = sorted((root / ".claude" / "commands").glob("*.md"))

    if not skills:
        errors.append("no SKILL.md files found under .claude/skills/ or .agents/skills/")
    if not methodologies:
        errors.append("no methodology files (0*.md) found under .claude/skills/*/")
    if not commands:
        errors.append("no command files found under .claude/commands/")

    for skill in skills:
        check_skill(skill, root, errors)
    for mfile in methodologies:
        check_methodology_file(mfile, root, errors)
    for command in commands:
        check_command(command, root, errors)
    check_settings(root, errors)
    return errors


def main() -> int:
    errors = run_lint(ROOT)
    if errors:
        print(f"lint_skills: {len(errors)} failure(s)")
        for err in errors:
            print(f"  - {err}")
        return 1
    skills_count = len(list(ROOT.glob(".claude/skills/*/SKILL.md"))) + len(list(ROOT.glob(".agents/skills/*/SKILL.md")))
    method_count = len(list(ROOT.glob(".claude/skills/*/0*.md")))
    cmd_count = len(list((ROOT / ".claude" / "commands").glob("*.md")))
    print(f"lint_skills: OK ({skills_count} skills, {method_count} methodology files, {cmd_count} commands, settings.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
