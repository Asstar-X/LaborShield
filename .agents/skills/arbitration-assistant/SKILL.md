---
name: arbitration-assistant
description: >
  Portable thin-pointer skill entry for LaborShield (China Labor & Personnel Dispute Arbitration Framework).
  Routes Antigravity, Codex, Cursor, and Gemini CLI agents to the canonical workflow and reference files
  under .claude/skills/arbitration-assistant/ and .claude/commands/.
allowed-tools: Read, Glob, Grep, WebFetch, WebSearch, Bash, Edit, Write, AskUserQuestion
framework_version: 1.0.0
---

# LaborShield Portable Skill Pointer (`arbitration-assistant`)

This workspace uses a **Thin-Pointer Single Source of Truth** design (modeled on `ai-job-search`).
To avoid rule drift across agent runtimes, always load the canonical instructions and templates directly from:

1. **Master Skill & Workflow Specification**: [`.claude/skills/arbitration-assistant/SKILL.md`](../../../.claude/skills/arbitration-assistant/SKILL.md)
2. **Single Source of Truth Case Profile**: [`.claude/skills/arbitration-assistant/01-case-profile.md`](../../../.claude/skills/arbitration-assistant/01-case-profile.md) and [`CLAUDE.md`](../../../CLAUDE.md)
3. **Slash Command Workflows**:
   - `/case-setup`: [`.claude/commands/case-setup.md`](../../../.claude/commands/case-setup.md)
   - `/calc`: [`.claude/commands/calc.md`](../../../.claude/commands/calc.md)
   - `/audit`: [`.claude/commands/audit.md`](../../../.claude/commands/audit.md)
   - `/docket`: [`.claude/commands/docket.md`](../../../.claude/commands/docket.md)
   - `/hearing`: [`.claude/commands/hearing.md`](../../../.claude/commands/hearing.md)
   - `/track`: [`.claude/commands/track.md`](../../../.claude/commands/track.md)
4. **Deterministic Python Tools**:
   - `python3 tools/labor_calc.py`
   - `python3 tools/generate_docket_docx.py`
   - `python3 tools/verify_docket.py`
   - `python3 tools/evidence_timeline.py`
   - `python3 tools/lint_skills.py`
