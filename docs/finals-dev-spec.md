# VeriPlan 决赛开发报告：一人公司的 AI 决策委员会

> 更新：2026-10-11　目标：10-18 前功能冻结，10-31 决赛现场 Live 演示
> 论证依据：[[VeriPlan决赛方向-证据报告]]
> 执行：Claude 负责规格、契约、审查、集成和真实联调；代码由 Codex 写（前后端都用 gpt-6-astra）

---

## 0. 结论

一共改 4 件事：
1. **场景通用化**：去掉"14 天、客服基线"的写死逻辑，让用户填带信心的数字假设；
2. **独立委员会**：三个委员并行、互相看不见，再由反方做事前验尸；
3. **会说不可度量**：统计反方提出了多少条"你没写过的风险"，由用户在审批时标注是否采纳；
4. **会记仇**：回填实际结果，由代码算出偏差画像，下次决策时强制反方引用。

底座（双闸门、证据门控、状态机、Live 门禁）不动，只扩展。

**不做：** 设备投入、人员配置、文件上传、多用户登录、资金方视图（只在路演里讲）。

---

## 1. 代码基线：本地仓库已损坏，必须先说清楚

| 位置 | 状态 |
|---|---|
| `~/Desktop/bs/HAIC/` | ❌ `.git` 只剩 index，134 个 blob **全部丢失**；源码只剩 13 个文件（缺 `main.py`、`schemas.py`、`deepseek.py` 等），**无法运行** |
| GitHub `YIKUAIBANZI/VeriPlan` | 只有 2026-09-08 的初版单提交，比快照旧 |
| `HAIC/artifacts/VeriPlan.zip`（与参赛包里的 `VeriPlan-whitelist-snapshot.zip` 字节一致） | ✅ 源提交 `16a93af`，2026-09-18 的发布快照。**我已实测：后端 205 passed，前端 31 passed** |

**决定：以快照作为新基线。** 新建 `~/Desktop/bs/VeriPlan-finals/`，`git init` 后提交快照作为 `main`。原 HAIC 目录**不动**，留作文档和素材库。

**代价：** 9-18 之后的设备投入（D1/D2）和人员配置代码只剩残片。新方向下它们本来就降级了，不恢复。

---

## 2. 成功标准（验收清单）

| # | 标准 | 怎么验 |
|---|---|---|
| S1 | 原有测试全部通过；改动语义的旧测试必须在 PR 说明里逐条解释 | `pytest`、`vitest` |
| S2 | 三位委员**并行**调用，且彼此看不到对方的输出 | 单测：每位委员的 prompt 输入里不含其他委员的产物；Fake provider 记录调用时间有重叠 |
| S3 | 反方的每条意见都关联到假设或用户已知风险；"新增风险数"由代码计算 | 契约校验 + 单测 |
| S4 | 偏差画像**纯由代码计算**，模型不能改写数字 | 单测：模型输出里的数字和画像不一致时拒收 |
| S5 | Demo 模式能完整演示：分歧、否决、偏差警告、回填 | 更新后的 `verify_demo.py` 通过 |
| S6 | Live 模式（DeepSeek 或百炼 + Tavily）真实跑通一次，从创建到审批，耗时 ≤ 120 秒 | 我执行 `scripts/live_smoke.py`，结果落盘 |
| S7 | 消融实验脚本能输出"单模型 vs 委员会"的风险对照表 | `scripts/ablation.py` 能离线跑通；Live 由我跑 |

---

## 3. 冻结的 API 契约（前后端并行开发的唯一依据）

### 3.1 创建决策 `POST /api/decisions`

```jsonc
{
  "scenario": "general",          // ai_tool_pilot | first_hire | big_order | marketing_spend | general
  "question": "要不要花 3 万给工作室招第一个全职设计师？",  // 12–1000 字
  "horizon_days": 90,             // 7 | 14 | 30 | 90 | 180 | 365
  "budget_limit": 30000,          // 0–10,000,000
  "primary_goal": "三个月内接单产能翻倍",       // 1–200
  "known_risks": ["招错人", "单量不稳"],        // 0–5 条，每条 ≤ 200 字。用户已经想到的风险
  "assumptions": [                // 0–8 条
    {"label": "月新增订单收入", "category": "revenue", "value": 20000, "unit": "元/月", "confidence": 70}
  ],
  "business_baseline": { }        // 可选，仅 ai_tool_pilot 使用，保留原 8 项
}
```

- `category` 取值：`revenue | cost | volume | time | conversion | other`。
- `confidence` 取值 50–95，含义是"我有多大把握实际值落在 ±20% 以内"。
- 服务端给假设分配 ID：`A1`…`A8`。
- `time_window` 由服务端派生为 `"{horizon_days} 天"`，保持旧字段兼容。
- **兼容：** 旧请求只带 `time_window: "14 天"`、不带 `scenario` 时，按 `ai_tool_pilot` 和 `horizon_days=14` 处理，原 `test_api` 必须继续通过。

### 3.2 新增的快照字段（`DecisionSnapshot`）

```jsonc
{
  "scenario": "general",
  "horizon_days": 90,
  "known_risks": ["..."],
  "assumptions": [{"id": "A1", "label": "...", "category": "revenue", "value": 20000, "unit": "元/月", "confidence": 70}],
  "is_retrospective": false,
  "outputs": {
    "analyzing": {
      "summary": "...",
      "members": [
        {"role": "opportunity", "stance": "support", "headline": "≤60字",
         "reasoning": "...", "key_points": ["1–4条"], "challenged_assumption_ids": ["A1"],
         "evidence_ids": ["3"], "confidence": 65}
        // 另外两位：cfo、risk
      ],
      "disagreement": {"stances": {"opportunity": "support", "cfo": "oppose", "risk": "conditional"},
                       "is_split": true}               // 代码计算：同时出现 support 和 oppose 即为分歧
    },
    "challenging": {
      "summary": "...",
      "premortem": "假设 90 天后这件事失败了，最可能的经过是……",
      "objections": [
        {"id": "O1", "text": "...", "severity": "blocker",   // blocker | major | minor
         "targets_assumption_ids": ["A1"],
         "overlaps_known_risk_index": null,                   // null 表示用户没想到的新风险
         "evidence_ids": []}
      ],
      "hidden_assumptions": ["..."],
      "calibration_warnings": [                               // 由代码生成并注入，模型不能改
        {"category": "revenue", "bias_pct": 38.5, "sample_size": 3, "assumption_ids": ["A1"],
         "adjusted_reference": {"A1": 12300},
         "message": "你过去 3 次收入类预测平均高估 38.5%"}
      ],
      "novel_objection_count": 3                              // 代码计算
    },
    "delivering": {
      "recommendation": "small_test_first",   // go | go_with_conditions | small_test_first | defer | no_go
      "conditions": [{"objection_id": "O1", "condition": "..."}]
      // 其余字段沿用原 DeliveringOutput
    }
  },
  "objection_labels": {"O1": "adopted"},      // adopted | already_known | disagree
  "outcomes": [
    {"checkpoint": "day_30", "recorded_at": "...", "note": "...",
     "actuals": [{"assumption_id": "A1", "actual_value": 12000, "error_pct": -40.0}]}
  ]
}
```

旧记录里的 `recommendation` 可能是 `pilot_before_rollout`、`do_not_pilot`、`defer`，前端必须能显示，导出不能报错。

### 3.3 新增端点

| 端点 | 规则 |
|---|---|
| `POST /api/decisions/{id}/objection-labels` `{"labels": {"O1": "adopted"}}` | 状态为 `awaiting_review` 或已审批时才允许；ID 必须存在；可以重复覆盖 |
| `POST /api/decisions/{id}/outcomes` `{"checkpoint": "day_30", "actuals": [...], "note": "..."}` | 只在 `accepted`、`revised`、`deferred` 后允许；`checkpoint` 取 `day_30 \| day_90 \| day_180 \| custom`；同一节点覆盖写入；`assumption_id` 必须存在 |
| `POST /api/retrospectives` | **回溯样本**：录入一个过去的决定（问题、场景、决策日期、带信心的假设、实际值、备注），直接生成 `status="retrospective"`、`is_retrospective=true` 的终态记录，不走工作流。用于在 20 天内诚实地攒出校准数据 |
| `GET /api/calibration` | 返回偏差画像（见 §4.4），同时列出每个样本的来源：`live`、`demo` 或 `retrospective` |

新增状态 `retrospective` 必须写进 `DecisionStatus`，加入状态机，并且没有任何合法的出边。

---

## 4. 后端工作包（Codex A：gpt-6-astra）

### B1 场景通用化

- 改 `schemas.py`：加 `scenario`、`horizon_days`、`known_risks`、`assumptions`（`Assumption` 模型）；放开只允许 `"14 天"` 的校验，同时保留旧请求兼容（见 §3.1）。
- 改 `models.py` 和 `repository.py`：加 JSON 列 `scenario`、`horizon_days`、`known_risks_json`、`assumptions_json`、`objection_labels_json`、`outcomes_json`、`is_retrospective`。沿用现有的 `_migrate_schema_columns` 风格做**可重复执行的 SQLite 迁移**，旧库打开后旧任务必须能正常读取和导出。
- 改 `prompts.py`：白名单加入新字段；`business_baseline` 只在 `ai_tool_pilot` 场景传入。
- 改 `contracts.py`：放开 `ClarifyingOutput` 和 `DeliveringOutput` 对 `time_window` 的约束，改为等于派生值。

### B2 独立委员会（会吵）

- `analyzing` 阶段从**一次调用**改为**三次并行调用**：`opportunity`（机会官）、`cfo`（财务官）、`risk`（风险官），用 `ThreadPoolExecutor(max_workers=3)` 实现。
- 新契约 `MemberOpinion`（字段见 §3.2），按角色校验：`role` 必须和本次调用一致；`evidence_ids` 必须存在；`challenged_assumption_ids` 必须是现有假设的 ID。
- `build_prompt` 新增 `stage="analyzing"` 加 `member=role` 的组装方式：每位委员拿到**完全相同的上下文**（约束、假设、研究结果、证据），加上各自的角色指令，**不能拿到任何其他委员的产物**。必须有测试断言这一点。
- 每次调用的 `ProviderCallContext.logical_operation = "analyzing:{role}"`，便于 provider attempt 账本区分。
- 事件：每位委员开始和完成时各写一条，`stage="council:{role}"`，`status` 取 `started` 或 `completed`，`summary` 形如 `"财务官：反对——{headline}"`。前端靠这些事件显示席位动画。
- `disagreement` 由代码计算，不让模型写。
- 任一委员失败，整个阶段就失败；重试时整个 `analyzing` 阶段重跑。这是为了简单，成本可以接受。
- **可选（P1）：** 支持按角色配置不同模型（异构委员会），配置项为 `COUNCIL_MODEL_MAP=cfo:bailian,...`。默认三位委员都用同一个 provider。

### B3 反方事前验尸（会说不）

- `challenging` 的输入是三位委员的产物、证据、假设、`known_risks`，以及代码生成的 `calibration_warnings`。
- 新 `ChallengingOutput`：`premortem`、`objections`（1–6 条）、`hidden_assumptions`。校验规则：
  - `targets_assumption_ids` 必须存在；
  - `overlaps_known_risk_index` 为 null，或是 `known_risks` 的合法下标；
  - **如果 `calibration_warnings` 非空，至少要有一条 objection 的 `targets_assumption_ids` 覆盖每个警告里的 `assumption_ids`**（强制反方引用你的历史偏差）。
- 代码计算 `novel_objection_count`，即 `overlaps_known_risk_index` 为 null 的条数。
- `delivering` 新增校验：存在 `severity=blocker` 的 objection 时，`recommendation` 不能是 `go`，而且 `conditions` 必须逐条覆盖所有 blocker 的 ID。原有的支持度封顶 59 规则保留。

### B4 校准引擎（会记仇）

新建 `backend/app/calibration.py`，全部是纯函数，不调用模型：

- 单个假设的误差：`error_pct = (actual - predicted) / |predicted| × 100`。`predicted == 0` 时跳过，并标注"不可计算"。
- 按 `category` 汇总：
  - `n`；
  - `mean_bias_pct`：误差平均值，正数表示实际比预测高；
  - `hit_rate`：|error_pct| ≤ 20 的比例；
  - `mean_confidence`；
  - `overconfidence_gap = mean_confidence - hit_rate × 100`。
- **生成警告：** 某个类别 `n ≥ 2` 且 |mean_bias_pct| ≥ 20，同时当前决策有同类别的假设，就生成 warning，并给出 `adjusted_reference = value × (1 + mean_bias_pct / 100)`。界面上必须标注"按你历史偏差修正的参考值，不是预测"。
- 文案方向由代码决定：收入、销量、转化类用"高估/低估"；成本、时间类在实际值更高时用"低估了成本/耗时"。
- 数据来源包括已审批决策的 `outcomes` 和回溯样本。**Demo 和 Live 样本按 `mode` 隔离**，与现有的模式隔离规则一致。
- `challenging` 运行前，由工作流调用校准引擎生成警告，写入上下文和产物；模型只负责引用，不能修改。

### B5 Provider 与 Demo

- 新增 `providers/openai_compat.py`，走 Chat Completions，`response_format` 用 `json_schema`，不支持时降级为 `json_object` 再做 Pydantic 校验。
  - 主机白名单固定为 `dashscope.aliyuncs.com` 和 `api.deepseek.com`，沿用现有的脱敏和有界重试模式。
  - 配置：`MODEL_PROVIDER=deepseek|openai_compat`，`OPENAI_COMPAT_BASE_URL`，`OPENAI_COMPAT_API_KEY`，`OPENAI_COMPAT_MODEL`（例如百炼的 `deepseek-v4.1-flash`）。
  - Live 门禁保持不变：缺 key 就不开放写操作。
- 更新 `providers/demo.py`，让 5 个场景都有确定性输出，而且 **Demo 必须演示出分歧**：至少一位委员 `oppose`，至少一条 `blocker`，至少一条 novel objection。
- 新增 Demo 种子：两条回溯样本（标注"合成"），让 Demo 一跑就能出现偏差警告。

### B6 导出与验证

- `markdown_export.py`：加入委员会的分歧表、反方验尸、新增风险数、用户标注、偏差警告和回填对照。旧记录导出不能报错。
- `scripts/verify_demo.py`：禁网跑完新流程，断言分歧、blocker、警告、回填和校准这几项都出现。
- `scripts/live_smoke.py`：需要显式传 `--i-authorize-live` 才运行；读取环境变量里的 key；用临时数据库跑完一个 `general` 场景，从创建一路到审批；输出每阶段耗时和 provider 调用数到 JSON；**输出中不得包含 key**。
- `scripts/ablation.py`：
  - 输入：问题 JSONL。
  - 对每个问题，A 组用同一模型单次调用"评估这个决定并列出所有风险"，B 组跑完整工作流。
  - 输出：CSV（列为 `question_id, arm, risk_text, label`，`label` 留空给人工标注）和汇总 Markdown（每组风险条数）。
  - 用 Fake provider 必须能离线跑通测试。

---

## 5. 前端工作包（Codex B：gpt-6-astra）

按 §3 契约开发。后端没合并之前，用 `api.ts` 的 mock 和测试 fixture 开发。

- **F1 创建页**
  - 5 张场景卡，每张都能"填入示例"。其中 `ai_tool_pilot` 保留原来的客服示例和业务基线。
  - 输入项：周期选择、"你已经想到的风险"（0–5 条）、假设表编辑器（标签、类别、数值、单位、信心滑块 50–95）。
- **F2 委员会面板**（核心演示画面）
  - 三个席位卡同时显示"思考中"，根据 `council:{role}` 事件逐个翻出结论，用颜色区分立场；出现分歧时顶部显示"委员会意见分裂"。
  - 反方区：先放验尸故事；每条 objection 带严重度，并标出"🆕 你没想到"或"你已提到"；顶部大字显示"反方提出 N 条你没写过的风险"。
  - **删除**"不是三个独立 Agent"这类文案。Demo 模式的标识保留，但缩小成角标。
- **F3 审批闸门增强**：审批前可以给每条 objection 标注"采纳 / 已知 / 不同意"，审批后显示"M 条改变了方案"（M = adopted 的数量）。
- **F4 记仇面板**
  - 已审批决策显示"回填实际结果"表单，节点可选 30/90/180 天或自定义，每个假设填实际值，提交后显示误差。
  - 左栏新增"我的偏差画像"页：按类别展示偏差、命中率和信心落差，样本来源用标签区分 Live / 回溯 / 合成。
  - 提供"录入一个过去的决定"入口，对接 retrospectives 端点。
  - 新决策的反方区如果出现 `calibration_warnings`，用醒目的卡片显示："你过去 3 次收入预测平均高估 38%，本次 A1 修正参考值 12,300（不是预测）"。
- **F5** 推荐结论 label 兼容新旧两套枚举。原有组件测试更新后必须通过，新组件都要有 Vitest 测试。`npm run build` 必须成功。

---

## 6. 分工与流程

```
Claude  ──① 建 VeriPlan-finals 仓库（快照提交为 main）+ 写入本报告 docs/finals-dev-spec.md
        │
        ├─② Codex A（gpt-6-astra, effort=high）  worktree: feat/backend-council   → B1–B6
        └─② Codex B（gpt-6-astra, effort=high）  worktree: feat/frontend-council  → F1–F5（并行）
        │
Claude  ──③ 逐个审查 diff、跑全量测试，先合后端再合前端，修集成问题
        ──④ Live 联调（需要你提供 key）→ live_smoke → ablation 实跑
```

- 两边都只能在自己的 worktree 里工作，**不碰对方的目录**，不 push。
- 每个工作包完成后提交一次，提交信息写清楚改了什么、测试结果如何。
- Codex 自报"通过"不算数，由 Claude 独立复跑验证。

## 7. 排期

| 日期 | 里程碑 |
|---|---|
| 10-12 | 建仓库，派发两边任务；你联系赛事小助手 |
| 10-13～10-15 | 后端 B1–B6、前端 F1–F5 完成 |
| 10-16 | 集成，全量测试，Demo 验收 |
| 10-17 | Live 联调，跑消融实验（10 个问题左右） |
| 10-18 | **功能冻结** |
| 10-19～10-24 | 真实用户 3～5 人加回溯样本；只修 bug |
| 10-25～10-30 | 路演 PPT、讲稿、彩排、离线兜底包 |

## 8. 需要你提供的东西

1. **DeepSeek key 和 Tavily key**。我在 `~/.config/huhua/llm-keys.env` 里只看到百炼等几家，没有 DeepSeek 和 Tavily。也可以先用百炼的 `deepseek-v4.1-flash` 走 B5 的兼容通道。
2. 10 个左右"真实感"的决策问题，用于消融实验，可以来自你身边的人。
3. 是否推送到 GitHub（新仓库，或覆盖旧仓库的 `main`），等代码完成后再问你。
