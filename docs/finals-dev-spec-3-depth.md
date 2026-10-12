# 开发包 D：推理深度开关（2026-10-12）

背景：docs/ablation/SUMMARY.md。三轮消融显示，单次调用 + 反方提示词（D 臂）的可执行比例 ≥ 委员会（B 臂）。推测原因是反方读了委员会产出后倾向于汇总。用户希望"思考更深更全面"。本包把四种"加深"做成**开关**，默认关闭（保持现状），由消融决定去留。

原纪律全部保留：密钥只读环境、Live 门禁、模式隔离、人工闸门、数字由代码算、委员互相不可见、修复重试脱敏、契约校验（含偏差警告覆盖、blocker→conditions）。

## D1 反方独立（`SKEPTIC_INPUT=council|independent`，默认 `council`）

- `independent` 模式：challenging 的 prompt **不包含** analyzing 产物，只包含约束、假设、已知风险、研究、证据、calibration_warnings。
- 该模式下 challenging 与 analyzing 四席**并行**执行。若并行改动状态机代价大，**允许只做"不传产物"而不并行**，在说明中记录。
- delivering 照常同时读取委员会与反方。

## D2 推理深度（`DEEPSEEK_REASONING_EFFORT=low|medium|high`，默认 `low`）

- DeepSeek Responses 请求的 `reasoning.effort` 改为读取该配置（当前硬编码 low）。
- 可选按阶段覆盖：`REASONING_EFFORT_STAGES=challenging:high,delivering:high`，未列出阶段使用全局值。

## D3 反方自审（`SKEPTIC_REVIEW_PASS=true|false`，默认 false）

- challenging 首稿通过校验后，再调用一次模型（`logical_operation="challenging:review"`），输入为首稿 + 相同上下文。
- 指令：逐条审查。不具体（没有挂到假设 ID 或证据、或没有可核验条件）的改写或删除；补充遗漏的阻断性风险；仍最多 6 条；输出同一 schema。
- 审查稿走完整契约校验与一次修复。审查失败时**保留首稿**并在事件中记录，不让阶段失败。
- 代码字段（novel_objection_count、calibration_warnings）按最终稿重新计算或注入。

## D4 两轮检索（`RESEARCH_ROUNDS=1|2`，默认 1）

- 为 2 时，在 researching 内追加一次模型调用（`logical_operation="planning:followup"`）。输入：约束、假设、已有证据摘要、research_gaps。输出 1–2 条补充查询（复用 PlanningOutput 的 queries 约束或新增小契约），执行检索，去重后入库。
- 总查询数上限从 3 提到 5（仅在 2 轮时）。查询与证据照常持久化，可恢复。
- Demo 模式下给出确定性的补充查询与合成证据。

## 消融脚本

- `scripts/ablation.py` 新增 `--b-only`：只跑 B 臂，便于比较不同开关组合；B 臂读取当前进程环境中的上述开关。

## 验收

- pytest 全绿；`verify_demo.py` 通过；默认开关下行为与现在完全一致（现有测试不改语义）。
- 每个开关都有离线测试：
  - D1：independent 模式下 prompt 中不含委员产物；
  - D2：请求体中的 effort 取值正确；
  - D3：审查成功时替换首稿、失败时保留首稿，calibration 覆盖规则仍然生效；
  - D4：第 2 轮查询被执行，查询上限为 5，证据去重。
- 在 `docs/finals-backend-notes.md` 末尾追加"开发包 D"一节。
