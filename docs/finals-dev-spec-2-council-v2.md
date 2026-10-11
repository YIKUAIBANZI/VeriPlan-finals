# 开发包 C：专家席 + 异构委员会（2026-10-12）

前置：docs/finals-dev-spec.md、docs/finals-backend-notes.md（含 Live 加固）。原纪律全部保留：密钥只读环境、Live 门禁、模式隔离、人工闸门、数字由代码算、委员互相不可见、修复重试脱敏。

## C1 专家席（3 固定 + 1 动态）

- 白名单 `EXPERT_KINDS`：
  - `legal_compliance` 法务合规
  - `customer` 客户视角
  - `operations` 运营产能
  - `platform_rules` 平台规则
  - `personal_longterm` 个人长期发展
- `planning` 产物新增 `expert_kind`（白名单枚举）与 `expert_reason`（≤80 字）。模型给出非法值或缺失时，**不失败**，按场景兜底：
  - `first_hire` → `legal_compliance`
  - `big_order` → `operations`
  - `marketing_spend` → `platform_rules`
  - `ai_tool_pilot` → `customer`
  - `general` → `personal_longterm`
  - 兜底时 `expert_reason` 由代码写"按场景默认"，并在产物中写 `expert_source: "model" | "scenario_default"`。
- `analyzing` 并行 4 席：`opportunity`、`cfo`、`risk`、`expert`（`max_workers=4`）。
  - `MemberOpinion.role` 增加 `expert`，专家席产物额外带 `expert_kind`（必须等于 planning 选定值）。
  - 专家席与其他三席同样上下文隔离。角色指令按 `expert_kind` 注入。
  - 事件为 `council:expert`，`summary` 形如"法务合规专家：反对——…"。
- `disagreement.stances` 包含 expert；`is_split` 规则不变。
- 兼容：旧记录只有 3 席，读取、导出、前端渲染都不报错；契约校验仅对新记录要求 4 席。
- 反方 `challenging` 的输入包含 4 席。

## C2 异构模型（按席位配置 provider）

- 新配置 `COUNCIL_MODEL_MAP`，例如：
  `opportunity=bailian:qwen3.8-flash,cfo=deepseek,risk=minimax:MiniMax-M2.5-highspeed,expert=deepseek`。
  未配置时所有席位使用默认 provider，行为与现在完全一致。
- provider profile：
  - `deepseek`：现有 Responses 适配器，使用 `DEEPSEEK_API_KEY`。
  - `bailian`：openai_compat，`https://dashscope.aliyuncs.com/compatible-mode/v1`，key 为 `BAILIAN_API_KEY`。**qwen3.x 必须在请求体传 `enable_thinking: false`**。
  - `minimax`：openai_compat，`https://api.minimaxi.com/v1`，key 为 `MINIMAX_API_KEY`。
  - `kimi`：openai_compat，`https://api.moonshot.cn/v1`，key 为 `KIMI_API_KEY`。**只能 `temperature=1`**。
- 主机白名单扩充为：dashscope.aliyuncs.com、api.deepseek.com、api.minimaxi.com、api.moonshot.cn。原有的 URL 安全规则（HTTPS、无凭据、无 query、禁重定向、禁代理继承）不变。
- Live 门禁：map 中用到的每个 profile 都必须有非空 key，外加 Tavily key，否则 Live 不开放。错误信息只说缺哪个 **profile 名**，不打印值。
- **席位兜底**：某席位的 provider 在修复重试后仍失败时，用默认 provider 再调用 1 次。
  - 成功则该席产物标 `fallback_from: "<profile>"`；仍失败才判整阶段失败。
  - 账本 `logical_operation` 记 `analyzing:<role>:fallback`。
- 每席产物增加 `model_label`（如 `"通义千问 qwen3.8-flash"`、`"DeepSeek v4-flash"`、`"MiniMax M2.5"`），由代码按 profile 写入，不由模型生成。
- provider attempt 账本记录 profile 与 model 名。
- `live_smoke.py` 与 `ablation.py` 走同一套 map。smoke 输出每席实际使用的 profile，以及是否触发 fallback。

## C3 前端

- 委员会面板显示 4 个席位：桌面端一行 4 列，或 2×2，以投影可读为准；窄屏纵排。
- 专家席卡片标题写"本题加派：法务合规专家"，下方显示 `expert_reason`。`expert_source` 为场景兜底时标"按场景默认"。
- 每席显示 `model_label` 小角标。`fallback_from` 存在时显示"已切换备用模型"。
- 旧的 3 席记录正常显示，不出现空的第 4 席。
- 更新 fixtures，并补 Vitest 测试。

## 验收

- 后端 pytest、前端 vitest 全绿，`npm run build` 成功，`verify_demo.py` 通过（Demo 也演示 4 席与专家理由）。
- 新增测试至少覆盖：
  - 专家白名单与场景兜底；
  - 4 席并行、上下文隔离；
  - map 解析与非法 map 拒绝；
  - 每个 profile 的请求体差异（qwen 的 `enable_thinking`、kimi 的 `temperature`）；
  - 席位兜底与账本记录；
  - 缺 key 时的门禁；
  - 旧 3 席记录的读取与导出。
- 在 `docs/finals-backend-notes.md` 末尾追加"开发包 C"一节，写清旧测试的语义变化。
