# VeriPlan 决赛前端交接

更新：2026-10-12。工作分支：`feat/frontend-council`；基线：`da0060b3ad9e679b69775323751b5419e4a03010`。
只修改 `frontend/` 和本文；未改后端或 scripts，未调用真实 API / 模型 / 搜索，未 push。

## F1–F5 完成对照

| 工作包 | 完成内容 | 本包完成时验证 |
| --- | --- | --- |
| F1 | 5 张场景卡及合成示例；7/14/30/90/180/365 天；0–5 已知风险；0–8 数字假设（类别/值/单位/50–95 信心）；客服场景保留原 8 项业务基线；新契约类型与四个新端点 | Vitest 35 passed；build 成功 |
| F2 | 全宽三席委员会，同时思考、按 council 事件逐席展示；立场配色、分歧横幅；重试不沿用旧完成状态、失败停止思考；反方验尸、严重度、已知/新增风险与服务端新增数；Demo 角标 | Vitest 40 passed；build 成功 |
| F3 | 每条反方意见即时保存采纳/已知/不同意；保存期间锁住审批；保存失败保留原值并报错；审批后按已保存 adopted 数显示“M 条改变了方案”；跨模式只读 | Vitest 43 passed；build 成功 |
| F4 | 已审批记录回填 30/90/180 天或 custom；显示服务端误差（含不可计算）；左栏偏差画像、来源标签、回溯录入与终态账本；历史警告及修正参考值声明；无网络本地 mock | Vitest 54 passed；build 成功 |
| F5 | 5 个新推荐枚举及 2 个旧枚举中文 label；旧记录显示和导出入口；多周期与 blocker 条件展示；Live 未解锁时禁止写入但保留导出；测试全局 fetch 防漏网 | **Vitest 67 passed（14 文件）；npm run build 成功** |

每包先增改测试、确认失败，再实现并运行完整 Vitest 和构建。最终 `git diff --check` 无空白错误。

原测试语义变更：

- `App.test.tsx` 中固定 14 天与 readonly 断言改为 6 个可选周期；无 horizon_days 的旧记录复制默认 14 天，新记录保留周期、已知风险和数字假设，去掉服务端分配的假设 ID。
- `DecisionResult.test.tsx` 中“旧模板未受当前 14 天约束校验”改为“历史周期未对应当前可选范围”；新 90 天记录不会出现过时警告。历史 3 days 记录仍提示人工复核。
- 原有证据来源、业务基线、双人工闸门、轮询停止、请求竞态、下载释放 URL 等回归均保留通过。

## 本地开发与视觉验证

```sh
cd frontend
npm run dev
```

打开 `http://127.0.0.1:5173/?fixtures=1`。此参数仅 dev 构建有效：注入 `src/fixtures/mockApi.ts`，不调用 fetch；刷新会重置内存。普通入口继续使用 `api.ts` 对接后端。生产构建不包含此 mock。

Fixture 覆盖分歧、blocker、novel objection、历史偏差警告、已保存 outcomes 和 `pilot_before_rollout` 旧记录。可以从新建 → 确认 → 三席逐步完成 → 标注 → 审批 → 回填跑完整流程。

本次浏览器验证只允许本地前端静态资源，拦截 `/api/` 和所有外部请求。实际走完上述流程并打开偏差画像；控制台无错误。1440×1000 桌面确认三席并排与反方/修正参考值可读；390×844 窄屏三席纵排，页面 scrollWidth=390，无页面横向溢出。减少动态模式使用现有媒体查询关闭动画。

截图在 `/private/tmp/veriplan-council-desktop.png`、`veriplan-challenge-desktop.png`、`veriplan-council-mobile.png`、`veriplan-calibration.png`。

## 后端契约待核对

冻结文档没有以下精确 JSON，这些假定集中在 `types.ts` 和 `api.ts`，需合并时核对：

1. `POST /api/retrospectives` 暂定请求为：
   ```json
   {"question":"过去的决定","scenario":"general","decision_date":"2026-07-01","assumptions":[{"label":"收入","category":"revenue","value":20000,"unit":"元/月","confidence":70,"actual_value":12000}],"note":"回溯备注"}
   ```
2. `GET /api/calibration` 暂定为 `{mode, categories: [{category,n,mean_bias_pct,hit_rate,mean_confidence,overconfidence_gap}], samples: [{decision_id,assumption_id,category,source}]}`。hit_rate 按 0–1 展示为百分比；其他偏差百分数不乘 100。source 为 live/demo/retrospective，整个响应按 mode 隔离。
3. 三个新写入端点暂按返回完整 `DecisionSnapshot` 处理，与已有写入端点一致。若后端返回局部数据，应在 API 层写入后重新获取快照。
4. §3 只保证 council 事件有 status/summary，未保证每席完成时 members 已发布。因此先原样显示完成事件摘要；摘要形如“财务官：反对——…”时按明确立场配色，未知措辞保持中性；完整快照到达后显示结构化理由、引用和信心。分歧标志只读取服务端 `disagreement.is_split`。
5. custom 只是一种 checkpoint，未擅自添加自定义日期字段；具体回填时间写备注。同节点保存覆盖已有结果。误差 null 展示“不可计算”。

## 已知限制与验收边界

- 本地 mock 的校准汇总是固定合成画像；新增回溯只追加来源标签，不模拟后端完整聚合。它验证页面交互，不证明公式或数据隔离实现正确。
- 反方新增数、偏差警告、误差都读取服务端结果；前端仅格式化，不替模型或后端重算生产指标。
- “M 条改变了方案”指用户保存为 adopted 的条目数，未宣称系统已自动重写方案或产生真实经营效果。
- 旧字段可缺省以读取旧快照；本次没有运行后端导出器，仅验证新旧推荐的显示及 Markdown 下载调用链。
- 未做真实后端联调、Live smoke、消融或投影仪实机检查。S1 的后端部分及 S2–S7 后端/Live 验收仍需集成人员完成。

## Git 提交阻塞与逐包恢复

**工作包代码已完成，但要求的五个 Git 提交尚未生成。** 执行 `git add -A` 时，环境拒绝创建：

```text
/Users/yikuaibanz1/Desktop/bs/VeriPlan-finals/.git/worktrees/VeriPlan-finals-frontend/index.lock
Operation not permitted
```

当前会话不允许提权。没有修改 Git 配置、绕过沙箱或重置工作树。

各包完成时的源码快照、增量补丁和带指定 Co-Author 的提交消息保存于 `/private/tmp/veriplan-packages/`：`F1.patch` … `F5.patch`、`F1.message.txt` … `F5.message.txt`。补丁按上述基线依次应用，包含每阶段新增文件。它们是交接文件，不是已提交记录；临时目录可能被系统清理，应在交接时保留副本。

恢复 Git 写权限后，可在该基线的另一干净工作树按 F1→F5 逐包执行（替换 N）：

```sh
git apply /private/tmp/veriplan-packages/FN.patch
(cd frontend && npx vitest run && npm run build)
git add -A
git commit -F /private/tmp/veriplan-packages/FN.message.txt
```

不要把补丁再次应用到当前已有全部修改的工作树，也不需要删除当前成果。所有提交消息末尾均为：

```text
Co-Authored-By: Codex gpt-6-astra <noreply@openai.com>
```
