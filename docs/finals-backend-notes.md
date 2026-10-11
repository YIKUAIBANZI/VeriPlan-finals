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
