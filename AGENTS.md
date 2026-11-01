---
framework_version: 1.0.0
---

# Agent Guidelines: LaborShield (中国劳动人事争议仲裁技能体系)

本工作区用于管理中国劳动人事争议仲裁案件建档、法定赔偿金确定性精算、证据三性诊断、立案标准六件套（`.docx`）生成、庭审质证准备与法定期限追踪。

## Thin-Pointer Design (Single Source of Truth)

为防止在不同 AI Agent 运行时（Claude Code、Google Antigravity、Codex、Cursor、Gemini CLI 等）之间出现规则漂移或配置重复，本工作区严格采用对标 `ai-job-search` 的**统一薄指针（Thin-Pointer）设计**。所有 Agent 运行时均应从以下唯一真实数据源加载规范与案件档案：

1. **案件唯一事实基准 (Single Source of Truth Case Profile)**：
   - 申请人与被申请人主体信息、用工时间轴、离职前 12 个月应得工资明细及确认诉求定义在 [CLAUDE.md](CLAUDE.md) 及 [.claude/skills/arbitration-assistant/01-case-profile.md](.claude/skills/arbitration-assistant/01-case-profile.md) 中。
   - 任何对话轮次中确认的新事实必须遵循 **Standing Rule** 立即同步写回上述文件。
2. **标准工作流与专业方法论库 (Canonical Workflow Specifications)**：
   - 六大核心阶段（`/case-setup`, `/calc`, `/audit`, `/docket`, `/hearing`, `/track`）的分步执行指令与法律准据定义在 [.claude/commands/](.claude/commands/) 与 [.claude/skills/arbitration-assistant/](.claude/skills/arbitration-assistant/)（`01-*.md` 至 `07-*.md`）中。
   - 请勿在其他目录复制或分叉这些规则，始终将 `.claude/` 视为唯一规范源。
3. **跨平台便携技能入口 (Portable Agent Skills)**：
   - [.agents/skills/arbitration-assistant/SKILL.md](.agents/skills/arbitration-assistant/SKILL.md) 提供面向 Antigravity 与 Codex 自动发现的薄指针入口。
4. **本地确定性工具链 (Deterministic Python Tools)**：
   - 所有赔偿金计算、`.docx` 司法公文渲染、静态合规验证、证据页码编排与技能语法校验均由 [tools/](tools/) 目录下的 Python 脚本确定性执行。
