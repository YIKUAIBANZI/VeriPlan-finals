# VeriPlan 决赛方向：证据报告

> 更新：2026-10-11　用途：确认新方向前的论证材料（不是开发报告）
> 方向：**一人公司和小团队的 AI 决策委员会**，三个关键词：**会停、会吵、会记仇**
> 每条论据都标了可靠度：🟢 一手或同行评审　🟡 权威媒体或政府口径　🟠 二手、厂商或单一研究，引用要谨慎

---

## 0. 结论先行

| 方向 | 问题是真的吗 | 是否被忽略 | 已经有人做吗 | 判断 |
|---|---|---|---|---|
| ① 一人公司决策委员会 | ✅ 杭州有官方政策和量化目标 | ⚠️ 政策只补空间、算力、资金，**不补"决策能力"** | ⚠️ 海外已有一批 "AI Board of Advisors" 小产品 | **成立，但不能讲"首创 AI 董事会"** |
| ③ 会说不（反方或事前验尸） | ✅ 《Science》2026 实证 AI 会迎合用户 | ✅ 主流聊天产品是这个问题的来源 | ⚠️ 同类产品都靠"一个模型扮多个角色" | **最强论据，主打** |
| ④ 会记仇（决策复盘校准） | ✅ 预测研究支持"校准反馈有效" | ✅ 几乎没有产品做"决策之后"的环节 | ✅ 竞品几乎空白 | **最大差异点，但 20 天里证据最难攒** |
| ⑤ 决策案给资金方或园区 | ✅ 小微融资的核心卡点是信息不对称 | 🟡 监管在用税务数据补，没人做"决策材料"这一层 | 未发现 | **讲成商业故事，不实现** |

**最关键的一句：** "AI 董事会"这个形态**已经不新**。VeriPlan 的护城河必须落在三件别人没做好的事上：
1. 委员们**真的独立**：并行、上下文隔离，而不是一个聊天窗口里切换角色；
2. **数字由代码算**，模型不许改；
3. **决策后的复盘校准**。

---

## 1. 方向 ①：一人公司是真风口，"决策"是政策没覆盖的空白

### 1.1 证据：政策热度是真的，而且就在比赛所在地

- 🟡 **杭州市市场监管局《支持一人公司 OPC 创新创业发展的若干举措》（杭市监〔2026〕43 号）**，2026-04-15 印发，12 项举措，包括工位注册、"一址多照"、非货币出资等。[原文 PDF](https://www.hzarchives.org.cn/jspcms/uploads/1/file/public/202604/20260427141047_tikvgcx4ku.pdf)
- 🟡 **《杭州市打造全国"AI+OPC"创业新高地行动计划（2026—2028 年）》**：到 2028 年建成 OPC 社区 100 个以上、集聚高成长性 OPC 5000 家以上、OPC 人才 3 万以上；目前已建或在建社区 50 多个，服务 OPC 2000 多家。[浙江省经信厅转载](https://zjic.zj.gov.cn/ywdh/qyfz/202606/t20260630_24139659.shtml)
- 🟡 **余杭区数栖湾"数栖八条"**：最高 300 万元研发费用，加上算力支持；已对接 700 多位超级个体，选出 80 多组项目。[21 世纪经济报道 2026-03-20](https://www.21jingji.com/article/20260320/herald/cace6b8d46f73edc8f8402d52ba85ac3.html)
- 🟡 全国多地在跟进：北京海淀、丰台，上海杨浦（杨府发〔2026〕4 号）、临港，成都（13 条，累计最高 2500 万元）。[36Kr 成都](https://www.36kr.com/p/3735293748740097)、[北京日报](https://news.bjd.com.cn/2026/04/10/11681652.shtml)
- 🟢 **本赛事自身**：支持单位里有"浙江省科技创新企业协会 OPC 产业专委会"和"青橙国际 OPC 社区"，百强礼包指定落地"元核 OPC 社区"。[组织机构页](https://aichallenge.msup.com.cn/organization)

### 1.2 被忽略的问题：政策补的是"资源"，不是"判断"

- 杭州行动计划的五大工程是：社区、要素、人才、**金融护航**、**服务助跑**。公开报道列出的具体内容是空间、算力券（最高 1000 万元）、孵化器奖励（最高 200 万元），**没有任何一项针对"经营决策能力"**。
- 21 世纪经济报道采访社区运营方，提到的痛点是："缺乏交流碰撞的对象""创业生态孤立"，以及工商、财税等事务负担。社区给出的解法是**每周 2～3 场线下活动**。
- **推论（这是我的判断，不是报道原文）：** 一人公司天然没有 CFO、法务、唱反调的合伙人，"孤立"在经营层面就等于**没人审你的决定**。一个人有了算力和工位之后，下一步缺的就是这个。

### 1.3 证据：小企业失败率高、决策质量普遍差

- 🟢 美国劳工统计局（BLS）口径：新设企业大约 **1/5 撑不过第一年，约一半撑不过五年**（各版本数字在 77.9～79.6% 和 49.8～51.4% 之间浮动）。注意：这是"退出"而不等于"失败"，退出也包括被收购、退休。[SCORE 汇总](https://www.score.org/greaterphoenix/resource/blog-post/small-business-failure-rates-2024-summary)
- 🟡 McKinsey Quarterly《The case for behavioral strategy》（Lovallo & Sibony, 2010）：在 2207 名高管的调查中，**只有 28% 认为自己公司的战略决策质量普遍良好**。连有董事会的大公司都这样，一人公司只会更差。[McKinsey](https://www.mckinsey.com/capabilities/strategy-and-corporate-finance/our-insights/the-case-for-behavioral-strategy)
  - ⚠️ 网上流传的"流程比分析重要 6 倍"这个数，本次**没能核实**，答辩时不要用。

### 1.4 风险：这个形态已经有人做了

- 🟠 海外 2026 年已有一批 "AI Board of Advisors" 产品：Indie Hackers 上的 **Board**（宣称"专门设计来反对你"，有 CFO 角色）、Product Hunt 上的 **VentureBoard**（20 个会互相辩论的 AI 顾问）、The Solo Creators 的付费课程、The AI Maker 的 CEO/CTO/CFO/批评者委员会。[汇总来源](https://thesolocreators.com/learn/ai-board-of-advisors/)、[VentureBoard](https://www.producthunt.com/@spunchev)
- 它们的共同弱点（The Solo Creators 自己也承认）：**同一个对话里多个角色会趋同**，真正起作用的是独立和盲评，而不是角色名字。
- 🟢 学术上也有对应现象：多智能体辩论会出现"思维退化"（Degeneration-of-Thought），一旦模型对自己的答案有信心，就很难再产生新观点（Liang et al. 2023, arXiv:2305.19118）。另一方面，多智能体辩论**并不总是**优于自洽采样等更便宜的方法（Smit et al. 2023 "Should we be going MAD?", arXiv:2311.17371）。

**对设计的含义：** ① 不能讲"首创 AI 董事会"。要讲：**"别家是一个模型轮流扮演角色，我们是彼此看不见对方的独立委员，加上不许模型碰的计算器，加上事后算账。"** 同时**要做消融实验**：同一个问题，单模型回答和独立委员会各跑一遍，比较找出的盲点数量和类型。这既是创新性证据，也是在回应 MAD 的质疑。

---

## 2. 方向 ③：会说不——AI 迎合用户是被实证的系统性问题

### 2.1 证据（最硬的一组）

- 🟢 **Cheng et al., "Sycophantic AI decreases prosocial intentions and promotes dependence"，《Science》2026。** 研究覆盖 11 个前沿模型：
  - AI 认同用户行为的频率**比人类高 49%**，即使用户描述的是欺骗、违法或有害行为；
  - 三个预注册实验（N=2405）中，只和迎合型 AI 互动一次，参与者就**更确信自己是对的**（自评正确度提升 25%～62%），也更不愿意修复冲突；
  - 更要命的是：用户**更信任、更偏好**这种迎合型 AI。
  - [EBSCO 摘要](https://www.ebsco.com/articles/psychology/b97e12e3-f8f7-57bb-b906-7956732ee30e/sycophantic-ai-decreases-prosocial-intentions-and-promotes-dependence)、[arXiv 2510.01395](https://www.alphaxiv.org/abs/2510.01395.md)
- 🟢 **OpenAI 官方承认**：2025-04-24～25 的 GPT-4o 更新"明显更谄媚"，原因是训练过度看重用户的即时点赞，4 月 28 日开始回滚。[OpenAI《Expanding on sycophancy》](https://openai.com/index/expanding-on-sycophancy/)、[TechCrunch](https://techcrunch.com/2025/04/29/openai-explains-why-chatgpt-became-too-sycophantic)
- 🟢 ELEPHANT 基准（Cheng et al. 2025）：除了事实层面的附和，还有"社会性谄媚"，即维护用户自我形象。偏好数据会**奖励**这种行为，现有缓解手段只能部分解决。[alphaxiv 2505.13995](https://alphaxiv.org/abs/2505.13995)

### 2.2 为什么它被忽略

- 迎合问题来自**商业激励**：用户喜欢被认同，点赞数据又会反哺训练，所以通用聊天产品没有动力根治。
- 小企业主正在用这些工具做事。🟠 Alignable 2023 年调查（7802 人）显示，57% 的美国小企业主用过 ChatGPT，但主要用于营销内容（31%），用于"业务决策"的比例很小。[来源](https://www.woodfloorbusiness.com/news/article/15543084/alignable-57-of-small-businesses-have-tried-using-chatgpt)
- **推论：** 当越来越多一人公司拿聊天 AI 当"参谋"，它们拿到的是一个**统计上倾向于同意自己的参谋**。

### 2.3 证据：结构化唱反调确实有用

- 🟢 **事前验尸（Pre-mortem）**：Gary Klein 在 HBR 2007 年发表《Performing a Project Premortem》。其理论依据是 Mitchell, Russo & Pennington（1989, *Journal of Behavioral Decision Making* 2(1):25–38）："假设已经失败，再找原因"这种前瞻性后见之明，能让人找原因的准确度**提升约 30%**。
  - ⚠️ 这个 30% 是**单项实验室研究**里"找原因"的提升，**不是**"项目成功率提高 30%"。答辩时只能说："实验显示，'假设已经失败再找原因'能明显提高找出风险的能力。"[出处说明](https://theuncertaintyproject.org/tools/pre-mortem)

**对设计的含义：** 把"会说不"做成**可度量**的东西：每次决策显示"反方提出了 N 条你原本没写的风险，其中 M 条改变了最终方案"。这正好把论文结论翻译成产品指标。

---

## 3. 方向 ④：会记仇——"决策之后"是整个赛道的空白

### 3.1 证据

- 🟢 Benson & Önkal（1992, *International Journal of Forecasting*）：**只告诉结果（outcome feedback）几乎没用；告诉你"你的信心和实际准确度差多少"（calibration feedback）才能显著改善校准和过度预测。**[来源](https://repository.bilkent.edu.tr/items/40d5ee75-c46f-43c9-9047-c3cd7d927721)
- 🟢 Moore et al.（2017, *Management Science*）：基于多年地缘政治预测锦标赛，**训练能减少过度自信，团队协作能提高准确度**。[PDF](https://www.stat.berkeley.edu/~aldous/157/Papers/moore_swift.pdf)
- 🟢 Camerer & Lovallo（1999, *AER* 89(1):306–318）：创业者过度自信会导致"过度进入"。⚠️ 这个结论**有争议**：Danková & Servátka（2018/2019）的复制实验没能复现主效应。答辩时可以说"经典研究提出过"，**不要**说"已被证明"。[复制研究](https://mpra.ub.uni-muenchen.de/91492/)

### 3.2 为什么它被忽略

- §1.4 里所有 "AI Board" 产品都停在**做决定的那一刻**。只有 The AI Maker 提到"保存决策记录以便回顾"，但也只是存档，不做校准。
- 一人公司没有复盘会，也没有人事后追问"你当时说三个月回本，现在呢？"
- 结合 Benson & Önkal 的结论：**光记录结果没用，必须算出"你预测的 vs 实际的"偏差，并在下次决策时主动拿出来用。** 这就是"会记仇"的科学依据。

### 3.3 风险

- 20 天内攒不出真实的 30/90 天数据。**解法：** 演示时用真实用户**过去已经做过**的决定来补录"当时的预测 + 现在的实际"（回溯录入），诚实标注为"回溯样本"。
- 个人决策和预测锦标赛的题型不同（锦标赛是对错清楚的是非题），迁移效果没有直接证据。这一点答辩时要主动承认。

**对设计的含义：** 委员会每个关键假设都要**带数字和信心**（例如"月增收入 2 万，信心 70%"）。回填实际结果后算偏差，形成"你的偏差画像"（比如"收入类预测平均高估 X%"）。下次同类决策时，反方席要**主动引用**这条偏差。这正好对上赛题点名鼓励的"长短期记忆"。

---

## 4. 方向 ⑤：决策案作为小企业和资金方之间的"通用语言"

### 4.1 证据

- 🟡 经济日报（2025-05）：小微企业财务数据不规整，银行难以掌握经营状况；金融监管总局和发改委 2024 年建立协调机制，目标就是缩小银企之间的信息差。[光明网转载](https://m.gmw.cn/2025-05/27/content_38050331.htm)
- 🟡 人民日报（2024-11-18）：小微主体缺抵押品、财务管理不规范，常被银行惜贷、拒贷。[人民日报](https://paper.people.com.cn/rmrb/html/2024-11/18/nw.D110000renmrb_20241118_3-18.htm)
- 🟡 规模：截至 2025 年 10 月末，普惠小微贷款余额 35.77 万亿元，2024 年末授信户数超过 6000 万户。[新华网](https://www.news.cn/fortune/20251203/6b88b6c0a45c48498298ece3e8575da1/c.html)
- 🟡 **VeriPlan 自己 9 月的调研**（见 `HAIC/docs/product/…development-report.md` §2.3）：
  - 西赛动力财务负责人说，设备抵押贷款做不了，只能走融资租赁；
  - 厚道数控说，确定性比价格更重要，授信速度会影响决策。
  - 来源分别是央视《焦点访谈》和新华网。
- 🟡 **余杭本地流程**：OPC 项目要先参加区里的创新创业项目评审、路演，通过后才能入驻（21 世纪经济报道，同 §1.1）。也就是说，**园区本身就是一个"审决策"的买方**。

### 4.2 被忽略的问题

监管的解法是"用税务、经营数据替代报表"，银行看的是**过去的流水**。可是"这笔钱打算怎么花、为什么这样花比别的方案好、最坏会怎样"这类**前瞻性决策材料**，没人帮小企业写成资金方看得懂的样子。

### 4.3 风险

- 没有任何资金方访谈，这条只能当**愿景和商业模式**讲，不能说"有需求验证"。
- 答辩被问"银行会认吗"，诚实的回答是：**"还没验证，这是我们落地对接阶段想找园区和租赁公司验证的第一件事。"** 百强礼包的"场景对接、订单撮合"正好是这个验证渠道。

---

## 5. 被高估、需要避开的说法

| 不要说 | 原因 | 改成 |
|---|---|---|
| "首创 AI 董事会" | 已有 Board、VentureBoard 等产品 | "独立委员 + 计算器隔离 + 事后校准" |
| "多 Agent 辩论能提高准确率" | 证据混合：MAD 不总是优于更便宜的方法 | "我们做了消融对比，独立委员多找出 X 条盲点"（需要实测） |
| "事前验尸提高成功率 30%" | 原研究测的是"找原因的能力" | "实验显示能显著提高找出风险的能力" |
| "创业者过度自信已被证明" | 复制研究失败 | "经典研究提出过度自信假说" |
| "一人公司 X 万家、市场 X 亿" | 没核到全国官方口径 | 只用杭州官方目标（5000 家高成长 OPC，100 个社区） |
| "银行、园区会买单" | 零访谈 | "落地对接阶段的第一个验证目标" |

---

## 6. 还缺的证据（必须靠你在 20 天里补）

1. **3～5 个真实决策者**用一次（一人公司老板、开店的家人、独立开发者），记录：反方提出的风险里，哪几条是他们**原本没想到的**。这条数据同时支撑 ① 和 ③。
2. **2～3 个回溯样本**：他们过去做过的决定、当时的预测和现在的实际结果。用来演示 ④。
3. **消融对比**：同一个问题跑"单模型直接回答"和"独立委员会"，统计盲点数量。这是创新性的硬证据。
4. （可选）问 1 个园区运营或租赁、银行客户经理一句话："如果小企业交来这样一份决策案，你们会更愿意看吗？" 用来支撑 ⑤。

---

## 7. 一句话版本（路演用）

> **AI 会迎合你，这已经登上《Science》；一人公司没有人反对你，这是杭州 OPC 政策还没补上的缺口。VeriPlan 是一人公司的 AI 决策委员会：独立的委员会当面反对你，数字由代码算，还会记住你上次错在哪。**

---

### 来源清单

- 杭市监〔2026〕43 号：https://www.hzarchives.org.cn/jspcms/uploads/1/file/public/202604/20260427141047_tikvgcx4ku.pdf
- 杭州 AI+OPC 行动计划（浙江省经信厅）：https://zjic.zj.gov.cn/ywdh/qyfz/202606/t20260630_24139659.shtml
- 新华网《杭州："一人公司"风乍起》：https://www.news.cn/local/20260628/00f56b42570b421dbe6eb8ab285f6515/c.html
- 21 世纪经济报道《杭州"一人公司"养成记》：https://www.21jingji.com/article/20260320/herald/cace6b8d46f73edc8f8402d52ba85ac3.html
- 成都 OPC 13 条（36Kr）：https://www.36kr.com/p/3735293748740097
- 北京 OPC（北京日报）：https://news.bjd.com.cn/2026/04/10/11681652.shtml
- 赛事组织机构：https://aichallenge.msup.com.cn/organization
- Cheng et al., Science 2026（EBSCO）：https://www.ebsco.com/articles/psychology/b97e12e3-f8f7-57bb-b906-7956732ee30e/sycophantic-ai-decreases-prosocial-intentions-and-promotes-dependence
- 同上 arXiv：https://www.alphaxiv.org/abs/2510.01395.md
- ELEPHANT：https://alphaxiv.org/abs/2505.13995
- OpenAI《Expanding on sycophancy》：https://openai.com/index/expanding-on-sycophancy/
- TechCrunch 报道：https://techcrunch.com/2025/04/29/openai-explains-why-chatgpt-became-too-sycophantic
- McKinsey《The case for behavioral strategy》：https://www.mckinsey.com/capabilities/strategy-and-corporate-finance/our-insights/the-case-for-behavioral-strategy
- SCORE / BLS 存活率汇总：https://www.score.org/greaterphoenix/resource/blog-post/small-business-failure-rates-2024-summary
- Pre-mortem 出处说明：https://theuncertaintyproject.org/tools/pre-mortem
- Benson & Önkal 1992：https://repository.bilkent.edu.tr/items/40d5ee75-c46f-43c9-9047-c3cd7d927721
- Moore et al. 2017：https://www.stat.berkeley.edu/~aldous/157/Papers/moore_swift.pdf
- Camerer & Lovallo 复制研究：https://mpra.ub.uni-muenchen.de/91492/
- MAD 思维退化（Liang et al. 2023）：https://arxiv.org/abs/2305.19118
- Should we be going MAD?（Smit et al. 2023）：https://arxiv.org/abs/2311.17371
- AI Board 竞品汇总：https://thesolocreators.com/learn/ai-board-of-advisors/
- VentureBoard：https://www.producthunt.com/@spunchev
- Alignable 小企业 ChatGPT 调查：https://www.woodfloorbusiness.com/news/article/15543084/alignable-57-of-small-businesses-have-tried-using-chatgpt
- 经济日报小微融资（光明网）：https://m.gmw.cn/2025-05/27/content_38050331.htm
- 人民日报 2024-11-18：https://paper.people.com.cn/rmrb/html/2024-11/18/nw.D110000renmrb_20241118_3-18.htm
- 新华网普惠小微数据：https://www.news.cn/fortune/20251203/6b88b6c0a45c48498298ece3e8575da1/c.html
