"""Unit tests for tools/lint_skills.py."""

from __future__ import annotations

from pathlib import Path

from tools.lint_skills import ROOT, run_lint


def test_workspace_skills_and_commands_pass_lint() -> None:
    errors = run_lint(ROOT)
    assert errors == [], f"Expected zero lint errors in workspace, got: {errors}"


def test_lint_catches_malformed_skill_and_command(tmp_path: Path) -> None:
    # Create a broken mini workspace tree
    skill_dir = tmp_path / ".claude" / "skills" / "broken-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: broken\n---\nNo description or framework_version", encoding="utf-8")
    (skill_dir / "01-profile.md").write_text("# Missing frontmatter", encoding="utf-8")

    cmd_dir = tmp_path / ".claude" / "commands"
    cmd_dir.mkdir(parents=True)
    (cmd_dir / "audit.md").write_text("# Wrong Title\n", encoding="utf-8")

    (tmp_path / ".claude" / "settings.json").write_text('{"permissions": {"allow": ["Bash(python3 tools/missing.py:*)"]}}', encoding="utf-8")

    errors = run_lint(tmp_path)
    joined = "\n".join(errors)
    assert "missing required key 'description'" in joined
    assert "missing required key 'framework_version'" in joined
    assert "missing YAML frontmatter" in joined
    assert "command file must start with '# /audit'" in joined
    assert "references missing tool 'tools/missing.py'" in joined
