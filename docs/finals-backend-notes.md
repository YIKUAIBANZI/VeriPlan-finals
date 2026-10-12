# 决赛后端实施记录

范围：`feat/backend-council`，仅 backend/、scripts/ 和本文件；无真实网络请求、无 key 文件读取、无 push。

## B1 场景通用化

- 已增加五场景、六种周期、已知风险和假设；创建输入不接受假设 ID，仓库分配 A1–A8。快照新增字段和 SQLite 迁移可重复执行。
- 时间由 horizon_days 派生；同时传旧字段时要求一致。旧 14 天及英文别名仍有效，其他合法周期也支持旧字段形式。旧记录保持原时间字符串，既有约束相等校验继续适用。
- 非 ai_tool_pilot prompt 排除客服基线；假设字段逐项白名单。Clarifying/Delivering 原本已经与上下文时间做相等校验，无需修改。
- TDD：新增测试先出现 8 failures；实现后全量 **222 passed**（基线 205 passed）。迁移测试覆盖连续打开、旧推荐枚举导出和写事件。

### 旧测试语义调整

1. `test_schemas.test_decision_window_rejects_unsupported_or_ambiguous_values`：30 days 已是合法周期，非法样例改成 31 days；错误文案从固定 14 天改为支持的周期。
2. `test_api.test_create_normalizes_supported_window_and_rejects_other_windows`：非法 30 天改为 31 天，同上；旧创建请求和门禁断言保留。
3. `test_deepseek_provider.test_provider_uses_responses_json_schema_and_minimal_context`：prompt 白名单预期加入四个新输入字段，仍拒绝私有/内部上下文泄露。

### 契约说明

- §4.1 将 scenario、horizon_days 等统称为 JSON 列；实际采用标量 TEXT/INTEGER/BOOLEAN 和列表/对象 JSON TEXT，沿用现有迁移风格，API 无偏离。
- 假设 label/unit 采用 1–200/1–80 字限制；数值必须有限；信心为 50–95 整数。未增加假设正负限制。

## 提交环境阻塞

B1 完成后执行要求的 `git add -A && git commit ...`，环境拒绝创建主仓库 `.git/worktrees/VeriPlan-finals-backend/index.lock`（Operation not permitted）。当前会话不允许提权。继续完成可独立进行的实现、TDD 和验证；每包保存已跟踪文件的累计 diff 到 `/tmp/veriplan-B<n>.patch`（B1–B5 不包含未跟踪的新文件，详见最终 Git 交接）。这些补丁不应逐个顺序 apply；提交尚未完成，不把补丁当成 Git 提交。

## B2 独立委员会

- ThreadPoolExecutor(3) 执行三个 MemberOpinion，冻结同一上下文后深复制给每个席位；移除其他委员产物、事件、Memo，角色指令由 prompt 层注入。
- 角色、证据和假设 ID 严格校验；代码计算 disagreement。council 席位 started/completed 事件和 analyzing:role provider 操作名已接入。
- 任何席位失败不保存半成品；等待本轮线程结束，再从整个 analyzing 阶段显式重试。
- TDD：并行屏障、上下文隔离、失败重试新增测试先失败；全量 **228 passed**。
- 可选 P1 异构模型映射暂不实现，默认三位使用同一 provider。

### B2 旧测试语义调整

4. `test_workflow.test_demo_workflow_requires_confirmation_then_runs_remaining_stages`：阶段完成序列排除新增 council 子事件，人工闸门断言不变。
5. `test_workflow.test_demo_outputs_reference_synthetic_evidence_and_constraints`：三条 analyses 改为三条 members。
6. `test_stage_contracts.test_contract_requires_each_analysis_perspective_once` 改名并校验三个角色各出现一次，符合冻结 MemberOpinion 契约。
7. `test_live_workflow_integration.test_live_workflow_joins_bounded_search_and_all_model_stages`：模型调用数由 5 改为 7，analyzing 连续三次；搜索上限不变。

## B3 反方事前验尸

- 结构化 premortem、1–6 objections、hidden_assumptions；拒绝未知假设/证据/风险下标、重复意见 ID。每个偏差警告必须被至少一条意见完整覆盖。
- novel_objection_count 代码计算；calibration_warnings 由可信上下文深复制注入。模型若回传不同的数字/警告，直接拒收。
- 新生成 Memo 使用新推荐枚举；blocker 禁止 go，conditions 覆盖全部 blocker。既有证据缺口封顶 59 保留。
- objection-labels 支持审批前后重复覆盖；校验模式、人工闸门、意见 ID，未知 ID 返回 422。
- TDD：新增测试先 9 failures；实现后全量 **238 passed**。Git 提交仍受上述 index.lock 权限限制。

### B3 旧测试语义调整

8. `test_stage_contracts.test_contract_rejects_unknown_evidence_reference`：原 challenging 顶层 evidence_ids 改为 objections[0].evidence_ids，仍测试同一拒绝规则。
9. `test_workflow.test_demo_workflow_requires_confirmation_then_runs_remaining_stages`：新生成推荐由 pilot_before_rollout 改为 small_test_first；旧快照仍按 dict 读取、导出兼容旧值。

### B3 最小偏离 + 原因

- S3 要求每条意见关联假设或已知风险，但 §3 允许两者均为空，且 B5 要求 novel objection。没有任何假设时允许空 targets_assumption_ids 的 novel 风险；只要存在假设，就要求至少关联假设或合法已知风险。这样旧请求仍能运行，不伪造用户输入。
- 模型 JSON Schema 仅要求模型负责的字段；代码生成字段在校验后注入最终快照，避免让模型计算数字。外部快照字段与 §3 一致。

## B4 校准引擎

- 纯函数计算有符号误差、均值、命中率、平均信心与信心落差；0 预测/超出数值范围返回 null 和不可计算说明，不纳入均值。命中率使用未舍入误差判断，避免边界失真。
- 仅已审批任务和回溯终态参与画像；严格按 mode 隔离。样本保留来源、模式、决策/假设 ID、检查点与时间；同一决策同一假设取最近回填，避免伪增样本。
- n≥2 且 |bias|≥20 时生成当前同类假设的参考值；警告文案包含“不是预测”，代码决定方向。challenging 自动注入并强制引用。
- outcomes 只允许三种已审批状态，节点覆盖写；未知/重复假设和客户端 error_pct 拒绝。retrospective 一次事务创建终态，无合法出边。
- TDD：新增 8 项先失败；最终全量 **248 passed**。补充跨模式新端点、负预测和命中边界测试。旧测试无语义变化。

### 回溯与画像的补充请求/响应定义（§3 未给出逐字段 JSON）

`POST /api/retrospectives`：必填 question（12–1000）、scenario、decision_date（ISO 日期）、assumptions（1–8，沿用创建输入）、actuals（1–8，assumption_id/actual_value）；note 可选、≤1000 字。服务端分配 A1…；可以只回填部分假设。日期与备注保存到 `outputs.retrospective`，实际值保存到 `outcomes[0]`（checkpoint=custom）。不需要客户端提供预算/目标/周期，快照使用 0/回溯校准/90 天占位；不进入分析，不将这些占位当作历史输入事实。

`GET /api/calibration`：`{mode, categories: [{category,n,mean_bias_pct,hit_rate,mean_confidence,overconfidence_gap}], samples: [{decision_id,assumption_id,category,predicted_value,actual_value,confidence,error_pct,source,mode,checkpoint,recorded_at,is_synthetic,...}]}`。hit_rate 为 0–1 比例；source 为 live/demo/retrospective；回溯仍另带 mode 以隔离数据。合成标记只由服务端种子生成，普通请求不能自设。

`POST .../outcomes` 返回更新后的完整快照；actuals 至少 1 条，note 默认为空。同一 checkpoint 替换该节点全部 actuals，未回填的其他节点保留。未知引用 422，错误状态/模式 409，缺记录 404，Live 未解锁 503。

### B4 规格示例矛盾的处理

- §3 示例 `bias_pct=+38.5` 同时写“高估”并给出更低参考值，与 §4.4 的有符号误差公式冲突。以 §4.4 公式为准：收入高估时 bias_pct 为负、参考值下调；未改任何字段名。

## B5 Provider 与 Demo

- 新增 openai_compat Chat Completions；主机仅 dashscope.aliyuncs.com/api.deepseek.com，HTTPS、禁止凭据 URL/非标准端口/query/fragment，禁止重定向和代理环境继承。
- 默认 json_schema；仅明确“不支持 response_format/json_schema”的 400/422 降级 json_object。Schema 仍随系统指令发送，每次结果继续 Pydantic/引用/数字校验。降级与超时/429/5xx 重试合计最多 3 次，每次记录脱敏账本；无效响应不重试。
- 环境配置：MODEL_PROVIDER=deepseek（默认）或 openai_compat；OPENAI_COMPAT_BASE_URL（默认 https://dashscope.aliyuncs.com/compatible-mode/v1）、OPENAI_COMPAT_API_KEY、OPENAI_COMPAT_MODEL（默认 deepseek-v4.1-flash）。DeepSeek 兼容地址可使用 https://api.deepseek.com/v1。兼容通道复用 DEEPSEEK_TIMEOUT_SECONDS / DEEPSEEK_MAX_OUTPUT_TOKENS 的有界配置。
- Live 门禁依旧要求模式、显式开关、当前所选模型的非空 key、Tavily key 全部满足；另一个 provider 的 key 不能代替。模型名仅为配置默认，未进行真实服务可用性验证。
- 五场景均给确定性分歧/blocker/novel 意见与按 horizon 划分的行动计划。非客服场景不使用工单分析。Demo 无校准历史时，在首次 challenging 前懒加载两条固定 ID、明确“合成”的回溯样本，覆盖六个类别；已有校准数据则不追加种子，Live 永不种入。种子排在用户决策之后。
- 测试自动阻断 connect/connect_ex/DNS；所有供应商响应均由 MockTransport/Fake 提供。
- TDD：B5 新测试先 21 failures；最终全量 **283 passed**，含兼容通道完整 Live 模式离线流程（7 次模型账本）、错误脱敏、降级总预算、畸形响应、模式门禁与五场景验证。既有测试无需更改语义。

## B6 导出与验证

- Markdown 增加数字假设、已知风险、三席分歧表、推理与引用、反方验尸、意见严重度/新风险数/用户标注、代码偏差警告、blocker 条件和回填对照。非客服场景不展示客服基线；旧枚举/缺少新字段的历史 Memo 继续可导出。
- verify_demo 保留原业务基线与双闸门证明，新增委员会分歧、blocker、novel risk、警告、标注、回填与画像断言；清除三种供应商 key，阻断 connect/connect_ex/DNS。
- live_smoke CLI 和 Python 入口都要求显式授权；还必须满足现有 APP_MODE、ENABLE_LIVE_WORKFLOW 和所选模型/Tavily key 门禁。用临时数据库跑 general 到 deferred，输出各阶段/席位耗时、调用数、双闸门和 120 秒判定；异常不打印原始内容/凭证。超过 120 秒标记失败；不宣称已满足真实耗时目标。
- ablation 接收含 question_id + DecisionCreate 字段的 JSONL。A 用同一模型实例单次生成风险，B 跑完整流程并停在 deferred；输出 risks.csv 和 summary.md，label 留空。默认 Demo 严格禁网；真实实验另需 --live --i-authorize-live 和 Live 环境门禁。
- TDD：新增 B6 测试先 5 failures；最终 **291 passed in 6.63s**。覆盖 Live smoke 全链路 MockTransport（7 模型 + 2 搜索账本）、拒绝未授权调用、Fake 消融、离线 CLI、新导出和 verifier。
- 最终复核补出极大但有限数值的均值溢出回归：测试先复现 OverflowError，改用 Decimal 累加后求均值，避免合法输入令画像端点报 500。
- `test_demo_verifier.test_verifier_proves_offline_demo_gates_and_export` 只扩展断言，没有删改旧验收语义；新增兼容模型 key 不泄露检查。

### 脚本使用

```bash
backend/.venv/bin/python scripts/verify_demo.py --output /tmp/vd.json --force
backend/.venv/bin/python scripts/ablation.py --input /path/questions.jsonl --output-dir /tmp/ablation-output
# 仅由获得真实网络授权的操作人执行；key 必须已在进程环境中：
backend/.venv/bin/python scripts/live_smoke.py --i-authorize-live --output /tmp/live-smoke.json
backend/.venv/bin/python scripts/ablation.py --live --i-authorize-live --input /path/questions.jsonl --output-dir /tmp/ablation-live
```

questions.jsonl 每行示例：

```json
{"question_id":"Q1","question":"是否应该为工作室招聘第一个全职设计师？","scenario":"first_hire","horizon_days":90,"budget_limit":30000,"primary_goal":"提高接单产能","known_risks":["订单不稳定"],"assumptions":[{"label":"月新增收入","category":"revenue","value":20000,"unit":"元/月","confidence":70}]}
```

### Git 交接

各包完成后都执行了指定的 add/commit（提交信息含要求的 Co-Authored-By），但 add 阶段均因 index.lock 权限被拒绝，故实际没有创建任何提交。分支仍是 feat/backend-council，未 push。

`/tmp/veriplan-B1.patch` 至 B5 为当时已跟踪文件的累计 diff，**不含当时未跟踪的新文件**，不能视作完整包快照或顺序应用。最终 `/tmp/veriplan-B6.patch` 包含已跟踪改动及所有新增文件；`/tmp/veriplan-backend-final.tar.gz` 包含全部改动文件，供有 Git 元数据写权限的集成人接手。最终代码也完整保留在当前 worktree。

待提交信息应保留 B1–B6 工作包前缀，并在空行后附：`Co-Authored-By: Codex gpt-6-astra <noreply@openai.com>`。由于无法在包完成时提交，不能把当前工作区称为已有六个独立历史提交；集成人应审查并拆分提交。

## 最终完成情况（2026-10-12）

| 工作包 | 完成情况 | 包完成时全量测试 |
|---|---|---:|
| B1 | 五场景/周期/假设、白名单、旧请求与可重复迁移 | 222 passed |
| B2 | 三席并行、上下文隔离、角色契约、席位事件、整阶段重试 | 228 passed |
| B3 | 结构化验尸、代码新风险计数、blocker 交付条件、标注接口 | 238 passed |
| B4 | 纯代码校准、回填覆盖、回溯终态、模式隔离和警告注入 | 248 passed |
| B5 | 兼容通道、Live 门禁、五场景 Demo、两条合成回溯种子 | 283 passed |
| B6 | 新旧 Markdown、禁网证明、受保护 Live smoke、离线消融 | 291 passed |

最终 `cd backend && .venv/bin/python -m pytest -q`：**291 passed in 6.63s**。`git diff --check` 无错误；文件改动限于 backend/、scripts/ 与本文件。

指定命令 `backend/.venv/bin/python scripts/verify_demo.py --output /tmp/vd.json --force`：退出码 **0**。证据：双闸门完整；opportunity=support、cfo=oppose、risk=conditional；is_split=true；blocker=1、新风险=1、偏差警告=1；A1 实际值 12000、误差 -40%；画像 13 个假设样本（两条合成回溯各 6 项 + 本次回填 1 项）；3 条合成证据；真实请求 0；provider_calls=[]；Markdown 含最终回填。

已知限制：

- 六次 Git 提交均被沙箱对 worktree Git 元数据的写权限阻塞，尚未完成提交；代码与验证已完成，无 push。
- 没有进行任何真实网络请求；S6 真实链路与 ≤120 秒仍待另行授权验证。供应商当前模型名、json_schema 支持情况没有在线核验。
- 可选 P1 异构 COUNCIL_MODEL_MAP 未实现；默认同一模型三个独立并行调用。
- Demo 全部是合成材料，种子只在空 Demo 校准历史中生成。画像不是预测；小样本不能证明真实改进。
- 消融输出只提供风险条数与人工标注表，未做质量结论；B 额外研究/调用成本未控制。
- 延续单进程 SQLite 运行边界；没有增加多用户鉴权或多进程协调。回溯记录无 Memo，因此现有 Markdown 导出端点仍返回 409。

## Live 加固（2026-10-12，feat/live-hardening）

本节取代上文“无效响应不重试”“确认字段逐字相等拒收”的旧行为。全部使用 Fake / MockTransport，未读取 key 文件、未发真实网络请求，未尝试提交。

- **A：确认约束由服务端注入。** clarifying 的 question/time_window/budget_limit/primary_goal，以及 delivering 已有的 time_window/budget_limit/primary_goal，在 Pydantic 前覆盖，返回时再次写入服务端原值（避免字符串规范化改变旧记录）。缺失或类型错误也不能成为模型改写确认字段的渠道；输入 payload 不原地修改。delivering 契约原本没有 question，最终快照/导出的问题仍来自决策本身，未扩展 Memo schema。委员身份、引用、行动预算、blocker 条件、校准数字仍严格校验；不把模型生成的其他文本当作已确认值。
- **B：每个 Live 模型操作最多一次修复。** DeepSeek 和 openai_compat 共用校验/修复流程；JSON（包含响应信封）解析、Pydantic、引用、业务契约和截断失败均可触发。第二次输入增加 repair_errors，只含受控字段路径和规则；不回传模型原文、Pydantic input/msg/ctx 或未知额外字段名，摘要最多 8 条。成功后才记 succeeded、落阶段产物；再次失败保留最后一次具体子码。委员会每席独立补一次，其他席位不重跑、不共享产物；任何席位最终失败仍不落委员会半成品。
- **重试预算：** 正常输出错误为原调用 + 1 次 `:repair`；原调用保留已有最多 3 次传输/HTTP/兼容格式降级预算。修复严格只发 1 次 HTTP，不再嵌套传输重试，所以每操作物理请求上限 4 次。兼容通道已降级 json_object 时，修复沿用该格式，Schema 继续随 system 输入发送。认证、余额、审计错误等不触发模型修复。Demo 没有新增模型调用或自动修复。
- **C：稳定子码。** 新失败使用 model_incomplete、model_invalid_json、model_contract_violation，原先 transport/auth 等分类保留。provider attempt 与 snapshot.failure.code 一致；incomplete_reason 仅允许 max_output_tokens/content_filter/unknown（Chat finish_reason=length 映射为 max_output_tokens）。账本新增可空列，旧 SQLite 迁移可重复执行；旧 model_invalid_response 记录保持原样。工作流对 Fake/自定义 provider 的契约失败也返回 model_contract_violation。
- **前端兼容检查：** types.ts 的 failure.code 为 string；App.tsx 展示 failure.message，其余 failure 使用只涉及 stage。无需新枚举或文案映射，前端未改。
- **D：控制截断。** 两个 provider 默认预算 8192；共用配置 DEEPSEEK_MAX_OUTPUT_TOKENS 范围 512–16384。prompt 要求 summary ≤120 字、reasoning ≤200 字、objection text ≤120 字、premortem ≤200 字及其他单条文本尽量 ≤120 字。未收紧已有 Pydantic 文本长度，Demo/旧契约仍兼容；文本简洁要求不替代完整引用和条件。
- **E：smoke 可定位。** JSON 新增 provider_calls，逐次只输出 logical_operation/status/error_code，包含失败与 `:repair`；已有计数、阶段耗时、failure 和双人工闸门指标保留。截断原因可从 failure.incomplete_reason 查看，逐调用数组不扩展其他字段。

### 旧测试语义变化

1. test_stage_contracts 的 confirmed_constraint_rewrite：从“预算改写必须抛错”改为“预算必须被确认值覆盖”。test_finals_scenarios 的六种周期同理：模型写 999 天必须恢复真实周期。
2. test_stage_contracts 的 planning 查询重复用例：从“契约暂允许、workflow 去重后拒绝”改为“契约先拒绝少于两条不同查询”。这样真实 provider 能在记成功前修复，仍由工作流规范化并限制最多三个搜索查询。
3. test_deepseek_provider 的 invalid_responses、test_openai_compat 的 malformed_completion：从不重试、统一 model_invalid_response，改为一次修复、具体子码、两条闭合账本。空白文本属于 model_invalid_json；缺失/多段文本属于 model_contract_violation；未完成状态属于 model_incomplete。
4. test_provider_boundaries 的非法/重复 planning 输出仍在搜索之前失败，Demo/Fake 不增加自动重试，只更新期待错误码为 model_contract_violation；显式人工重试恢复语义保留。
5. test_live_configuration 与 DeepSeek 请求断言：默认 4096→8192，配置非法上界样例 8193→16385。
6. test_finals_delivery 的完整 smoke：补充逐调用字段白名单及成功状态断言，原有授权、计数、耗时、人工闸门与凭据不泄漏断言保留。

### 离线验证与交接

- TDD：A 新用例先复现 6 个失败；B/C 首批 20 个参数用例先失败；D 默认预算 2 个用例先失败；E smoke 先因缺 provider_calls 失败，再实现。
- 新增 test_live_hardening 覆盖约束改写/缺失/非法类型、快照与导出、两个 provider 的 JSON/Pydantic/引用/blocker/代码计数/查询错误、脱敏修复、两次失败上限、三席并发与独立修复、不落半成品、截断原因白名单与持久化、重复迁移、格式降级继承、修复传输失败不再重试，以及 challenging/delivering 修复成功/失败的完整 smoke。
- 各项完成后均执行后端全量 pytest：A 298 passed；B 318 passed；C 334 passed；D/E 336 passed（随后追加整链路用例，最终结果见下）。测试 fixture 阻断真实 connect/connect_ex/DNS。前端未改，未运行条件要求之外的 Vitest。
- 不宣称已提高真实 DeepSeek 跑通率或达到真实 ≤120 秒；集成人需用现有授权 smoke 复跑。修复与提高输出预算可能增加耗时，仍保留脚本的 120 秒判定。

最终验收：`cd backend && .venv/bin/python -m pytest -q` → **344 passed in 6.85s**；`git diff --check` 无错误。分支核对为 `feat/live-hardening`。修改仅在 backend/、scripts/ 和本文件；未改前端，未执行 git commit。

## 开发包 C（2026-10-12，feat/council-v2）

本节取代上文三席及“异构模型未实现”的状态。按 C1 → C2 → C3 实施，修改限于 backend/、frontend/src/、scripts/ 和本记录。未读取任何 key 文件（包括 ~/.config），未发真实网络请求，未执行 git add/commit/push；由集成人审查提交。

### 完成对照

| 包 | 完成内容 | 包完成时后端 | 前端 Vitest | build |
|---|---|---:|---:|---|
| C1 | 五种专家白名单、planning 选择/场景兜底、四席并发隔离、专家事件、四席反方输入、新旧记录导出 | 375 passed | 67 passed | 成功 |
| C2 | 席位 map、四个 profile、请求差异、门禁、单次备用请求、模型标签、账本迁移、smoke/ablation 共用路由 | 425 passed | 67 passed | 成功 |
| C3 / 最终复核 | 专家卡片与理由、模型/备用标记、2×2 与窄屏纵排、旧三席兼容、fixtures；补充 provider 边界回归 | 429 passed | 71 passed | 成功 |

- **C1：** `providers/council.py` 集中专家身份、场景默认和角色指令；planning 的 expert_kind/reason 在 Pydantic 前规范化，expert_source 由代码生成，重复校验保持来源。专家必须回传与规划一致的 kind；普通席位不能冒充专家。四个 worker 各取独立深复制，只有规划、研究、证据与原始约束，互不可见。新聚合严格要求四种角色各一次；历史 JSON 快照读取和 Markdown 不强制套新生成契约。Demo 五场景均使用确定性默认专家，导出包含专家名称与理由。
- **C2：** `COUNCIL_MODEL_MAP` 使用 `role=profile[:model]`，允许省略席位，未知角色/profile、重复席位、空条目、非法模型标识立即拒绝。未映射席位复用默认 provider；只路由 analyzing，planning/challenging/delivering 与消融 A/C 仍使用默认模型。应用工厂统一组装，smoke 和 Live ablation 因而共用同一 map，不另建路由。
- **门禁与安全：** 默认模型 key、map 中每个 profile 的非空 key、Tavily key、Live 模式与开关均满足才开放写操作；Fake 注入也不能绕过 key 门禁。缺失信息只列 profile 名称。新增域名保持 HTTPS、禁凭据 URL/非标准端口/query/fragment、禁重定向/代理继承；DeepSeek 客户端也显式禁用重定向与代理继承。qwen3 系列请求固定 `enable_thinking=false`，Moonshot 请求固定 `temperature=1`；Schema 降级与修复均保留这些参数。
- **修复与备用：** 映射到独立 provider 的席位耗尽原有有界修复/传输预算后，默认 provider 仅发 **1 次物理请求**，不再嵌套修复、重试或 Schema 降级。成功写入 fallback_from 和实际使用模型的 model_label；失败则整个 analyzing 失败，不落半成品。备用操作名为 `analyzing:<role>:fallback`，原有 `:repair` 独立记录；各席不串行、不重跑其他席。审计失败立即终止，不能用备用模型绕过账本。
- **元数据：** model_label/fallback_from 不在单席模型输出 Schema 内，模型伪造会触发契约错误；工作流在校验后注入。账本新增可空 profile/model 列，可重复迁移，旧记录保留 null，搜索无模型名。provider 字段继续表示适配器（deepseek/openai_compat/tavily），profile 表示席位配置；原默认 openai_compat 通道保持同名 profile。smoke 新增 `council[role]={profile,model,fallback_from}`，逐次 provider_calls 白名单增加 profile/model；失败且无聚合时 council 为空，失败请求仍可查账本。
- **C3：** 完成态按已有 members 渲染，旧三席不会出现空专家卡；执行中/重试等待四席，第四席未完成前不展示本轮分歧。专家标题为“本题加派：…专家”，显示理由及场景默认标记；有产物后显示模型角标和备用提示。桌面采用 2×2，≤760px 纵排；旧三席保留三列。开发 fixtures 增加专家和模型标签，按场景生成规划及专家身份；仍为合成演示，不发送 fetch/provider 请求。

### 配置与调用预算

```text
COUNCIL_MODEL_MAP=opportunity=bailian:qwen3.8-flash,cfo=deepseek,risk=minimax:MiniMax-M2.5-highspeed,expert=deepseek
```

环境 key 名：DEEPSEEK_API_KEY、BAILIAN_API_KEY、MINIMAX_API_KEY、KIMI_API_KEY，以及 TAVILY_API_KEY；默认 openai_compat 继续使用 OPENAI_COMPAT_API_KEY。配置只来自进程环境，不加载 env/key 文件。省略模型名时：deepseek 沿用 DEEPSEEK_MODEL，bailian 为 qwen3.8-flash，minimax 为 MiniMax-M2.5-highspeed，kimi 为 kimi-k2.5；均未做供应商在线可用性核验，支持 map 显式覆盖。

正常完整工作流为 **8 次模型调用**（四席 + 其他四阶段），搜索独立计数。单席原 provider 物理请求上限仍为 4（初始传输/兼容格式预算至多 3 + 修复 1），发生备用后上限为 5；无模型输出错误时不额外修复。新四席调用增加耗时/费用的可能性尚未通过真实链路测量。

### TDD 与旧测试语义变化

- C1 新增 31 个参数化用例先全部失败，再实现通过；四席 Barrier(4) 证明调用重叠，深复制变异用例证明席位隔离。覆盖五场景非法/缺失类型与理由兜底、专家类型相等、反方输入、旧记录 HTTP 读取/导出、新聚合拒绝三席。
- C2 首批 29 个用例先全部失败，再实现；追加 URL 边界、禁代理/重定向、消融 map、Demo 隔离、元数据防伪、审计失败不可绕过、qwen/Kimi 参数跨降级与修复保持、非默认专家整链路测试。最终新增后端用例共 **85** 个（C1 32 + C2 53）。最后一项 C1 回归先复现：模型合法选择但理由恰为“按场景默认”时，不得仅凭文案误标来源，已修正。
- C3 新增四项测试，其中专家展示、第四席完成门槛、fixture 专家链三项先失败；历史三席兼容项原本通过。随后实现并保留原审批、模式、失败/重试测试。

既有测试的调整逐项如下：

1. `test_council.py`：三席屏障/角色列表/重跑计数改为四席；隔离、整阶段失败、显式重试的语义不变。
2. `test_workflow.py`：新输出 members 数 3→4；人工闸门与原约束断言保留。
3. `test_live_workflow_integration.py`：analyzing 增加一次，正常模型调用 7→8；搜索上限不变。
4. `test_openai_compat.py`：Mock 按四种角色识别请求，并恢复 prompt 中的 planning 供专家引用；账本正常模型数 7→8。
5. `test_live_hardening.py`：三席 Barrier 改四席，Mock 解码保留 planning；仍要求财务席独立修复、其他席仅一次，失败无半成品。smoke 白名单增加 profile/model，原 logical_operation/status/error_code 的精确断言保留。
6. `test_finals_delivery.py`：消融 A/B/C 总模型调用 9→10、analyzing 3→4；smoke 由 7 模型+2搜索变为 8模型+2搜索（总数 9→10）。导出新增专家与理由断言，输出白名单同上。
7. `test_deepseek_provider.py` 的 AttemptSpy 接受新增 profile/model 参数，原调用计数、闭合账本和脱敏断言保留。
8. `test_demo_verifier.py`：新增四席和专家断言，并注入三个新 profile 的假 key 与 map 验证禁网清理/不泄漏；原门禁、回填、预算与导出断言保留。
9. `CouncilPanel.test.tsx`：新运行的同时思考席位由 3→4，完成一席后剩 3；保留没有专家信息的历史失败事件三席行为，另加完成态旧三席兼容用例。`mockApi.test.ts` 多等待第四席完成后再进入审批，双闸门语义不变。

### 偏离+原因

- 原 B2 的可选 map 示例为 `cfo:bailian`，C2 明确改为 `cfo=bailian[:model]`；以新 C2 为准，旧冒号语法拒绝，避免两种解析歧义。
- C1 只明确非法/缺失 kind 的兜底，没有说明理由缺失、空白或超过 80 字；采用同一场景默认兜底整个选择，不让辅助说明导致 planning 失败，且不截断成可能改变含义的理由。
- “未配置 map 时行为与现在完全一致”与“某席失败用默认 provider 再调用”在默认 provider 自身失败时有冲突。采用最小增量：只有映射到不同 provider 实例才启用备用；未映射或显式复用默认实例继续原有失败/修复行为。另保留审计失败直接终止，优先遵守安全纪律。
- 原 Live 加固说明 smoke 逐次数组只含三个字段；新 C2 要求实际 profile/model 可查，故仅增加两个代码持有字段，不输出请求体、key、响应原文或模型推理。
- 新规格未给省略模型名时的三个兼容 profile 默认值；采用上表固定默认，允许显式覆盖并标明未经真实核验。默认旧 openai_compat 不自动改名或改用新 key，保持既有配置兼容。

### 最终验证与已知限制

最终 pytest **429 passed**；Vitest **71 passed / 14 files**；`npm run build` 成功。`git diff --check` 无错误。指定 `backend/.venv/bin/python scripts/verify_demo.py --output /tmp/vd.json --force` 退出码 0：四席含 expert=oppose、is_split=true；customer 专家、理由“按场景默认”；blocker=1、新风险=1、偏差警告=1；A1 回填误差 -40%；两道人工闸门；provider_calls=[]、真实请求 0。

限制：没有真实供应商联调，模型可用性、请求参数在线兼容性、成功率、费用及 ≤120 秒目标仍待集成人授权验证。前端完成 Vitest、类型/生产构建与响应式样式检查，未执行浏览器截图或投影/真机验收。Demo 和 fixtures 均是合成数据；模型标签只是示例或配置身份，不能作为真实多模型效果证据。仍沿用单进程 SQLite 边界；所有改动未提交。

## 开发包 D（2026-10-12，feat/depth）

按 D1 → D2 → D3 → D4 → 消融脚本顺序 TDD 实施。修改仅在 backend/、scripts/ 和本文件；未读取 key 文件，未发真实网络请求，未对当前仓库执行 git add/commit/push。现有测试文件及断言语义未改，新增离线用例集中在 `backend/tests/test_depth.py`。本 worktree 没有 mmr.md，交接记录按本任务白名单保存在这里。

### 开关与行为

| 配置 | 默认 | 启用效果 |
|---|---|---|
| SKEPTIC_INPUT | council | independent 只给反方约束、假设、已知风险、研究、证据、代码基线及 calibration_warnings；过滤委员会、事件、Memo 等产物 |
| DEEPSEEK_REASONING_EFFORT | low | low / medium / high，传入 DeepSeek Responses 的 reasoning.effort |
| REASONING_EFFORT_STAGES | 空 | 如 challenging:high,delivering:high；未列阶段使用全局值，重复/未知阶段或非法 effort 拒绝 |
| SKEPTIC_REVIEW_PASS | false | 校验首稿后追加 challenging:review；通过则替换，输出/传输失败保留首稿并记录事件 |
| RESEARCH_ROUNDS | 1 | 2 时首轮仍最多 3 条，再调用 planning:followup 生成 1–2 条补充查询，总上限 5 |

- **D1：** 独立模式同时在 workflow 的 provider 输入和 prompt 白名单隔离委员会产物；delivering 仍读取委员会与最终反方稿。默认 council 的 prompt 内容和阶段顺序保持不变，四位委员仍并行且互不可见。
- **D2：** 应用默认 DeepSeek 与映射到 DeepSeek 的席位均接入配置；重试、修复沿用所属模型阶段的 effort。审查及其修复使用 challenging 覆盖，补充规划使用 planning 覆盖。此配置只作用于 DeepSeek Responses，其他适配器参数保持原状。
- **D3：** 审查输入为首稿与原上下文的独立深复制；指令要求逐条补足假设/证据关联与可核验条件、补充阻断风险、最多 6 条。复用完整 schema、引用、偏差警告覆盖和代码字段防伪校验；最终稿重新计算 novel_objection_count，并注入可信 calibration_warnings。Live 适配器沿用至多一次脱敏修复，操作名为 challenging:review:repair；Fake/Demo 不另加自动修复。开始、成功、失败事件使用固定文案，不保存异常原文。交付继续覆盖最终稿全部 blocker。
- **D4：** 采用只有 queries 的小契约（1–2 条、每条 ≤400 字、规范化后互异且不重复首轮），三个模型适配器均使用该 schema 与既有修复机制。输入仅含约束/假设、白名单证据摘要、研究缺口和已有查询。通过校验的补充计划先写 `outputs['planning:followup']`，再扩展持久化查询；已有查询及 ID 不重写。重启后复用补充计划，跳过成功查询，仅显式重试失败/中断查询。恢复同一任务应保留 RESEARCH_ROUNDS=2。
- 第二轮沿用 URL 规范化及标题/摘要去重、证据所属查询、搜索安全与缺口规则；不会在同一次阶段执行内再次请求首轮失败查询。Live 首轮无证据时允许第二轮补救，两轮后仍无证据则继续报 research_no_safe_evidence；失败查询的缺口不会被抹去，支持度封顶仍有效。Demo 补充两条确定性查询和明确标记的 demo.invalid 合成证据。
- **消融：** `--b-only` 仅调用 B，仍经过两道人为闸门并停在 deferred；返回计数、CSV 与 summary 只包含 B。B 读取当前进程开关（也支持 Python 入口显式 Settings），summary 记录白名单深度配置。默认不传此参数仍运行 A/B/C/D；Demo 禁网、Live 的双授权及 key 门禁不变。

### 偏离+原因

1. D1 按规格明确允许的简化方案，只隔离输入，未让反方与委员会并行。这样不增加状态机分支、跨阶段半成品或恢复规则；因此不宣称本包缩短总耗时。
2. D3 的“审查失败保留首稿”与原有“审计失败立即终止”在 provider_audit_failed 时冲突。保留安全优先级：该错误中止阶段，不能通过首稿回退绕过账本；普通审查失败仍按规格回退。
3. D4 首轮最多 3 条、补充最多 2 条，未把首轮扩大到 5 条，否则无法同时满足追加检索与总上限。查询响应 ordinal 从 0–2 扩为 0–4 以读取第二轮记录；默认仓库写入上限仍为 3，仅显式两轮路径允许追加至 5，无数据库结构迁移。
4. D4 补充查询拒绝与首轮重复，沿用现有 planning 对不同查询的纪律，避免付费执行无新增内容的补充规划；模型可用原有一次修复纠正。

### TDD 与验证

| 包 | 新用例先失败 | 包完成时全量 pytest |
|---|---:|---:|
| 基线 | — | 435 passed |
| D1 | 3（默认模式对照原本通过） | 439 passed |
| D2 | 9 | 448 passed |
| D3 | 9 | 457 passed |
| D4 | 5（随后补充恢复/空证据边界） | 472 passed |
| --b-only | 3 | 475 passed |

最终 `cd backend && .venv/bin/python -m pytest -q`：**475 passed in 9.64s**。覆盖默认行为回归、独立输入与交付双输入、全局/分阶段 effort（含映射席位和修复）、审查成功/修复/回退/警告覆盖/审计失败、五查询上限、跨轮 URL 与内容去重、两处中断后的恢复、空首轮补救与最终无证据失败、三个适配器的补充契约，以及全部开关的 B-only 离线整链路和 CLI 授权边界。所有 provider I/O 均为 Fake / MockTransport，测试 fixture 阻断 connect/connect_ex/DNS。

离线使用示例（questions.jsonl 格式沿用上文，输出目录须未存在同名产物）：

```bash
SKEPTIC_INPUT=independent SKEPTIC_REVIEW_PASS=true RESEARCH_ROUNDS=2 \
  DEEPSEEK_REASONING_EFFORT=low REASONING_EFFORT_STAGES=challenging:high,delivering:high \
  backend/.venv/bin/python scripts/ablation.py --b-only \
  --input /path/questions.jsonl --output-dir /tmp/ablation-depth
```

本轮未开展真实消融，不能由离线通过推断质量、耗时或成本改善。正常 B 为 8 次模型操作；同时开启审查和第二轮时为 10 次，另有最多 5 条搜索查询，传输重试/修复预算沿用原规则。

指定 `backend/.venv/bin/python scripts/verify_demo.py --output /tmp/vd.json --force` 已通过（退出码 0）：默认 3 条合成证据、四席分歧、两道人为确认/审批闸门、blocker=1、新风险=1、偏差警告=1、13 个校准样本；provider_calls=[]、真实请求 0。验证报告在 `/tmp/vd.json`。最终 `git diff --check` 无错误，修改范围符合白名单。
