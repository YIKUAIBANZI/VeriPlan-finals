"""Synthetic fixtures, never fetched research or independent real-world sources."""
from app.baseline import analyze_business_baseline
from app.providers.contracts import validate_stage_output
from app.providers.base import ProviderCallContext
from app.schemas import BusinessBaseline, EvidenceCard


class DemoSearchProvider:
    def search(
        self,
        query: str,
        *,
        call_context: ProviderCallContext | None = None,
    ) -> list[EvidenceCard]:
        fixtures = [
            ('模拟：重复工单基线', '模拟工单记录：重复问题可先由人工标记，尚未验证真实占比。', 'baseline', 'context'),
            ('模拟：人工升级流程', '模拟流程文档：退款、投诉和低置信度回复需要人工确认。', 'handoff', 'supports'),
            ('模拟：误答风险案例', '模拟风险案例：错误承诺可能增加返工，灰度也需要停机条件。', 'risk', 'opposes'),
        ]
        chosen = fixtures[1:] if 'risk' in query.lower() else fixtures[:2]
        return [EvidenceCard(title=title, summary=summary, source_url=f'https://demo.invalid/{slug}', stance=stance, reliability='low', is_demo=True) for title, summary, slug, stance in chosen]


class DemoModelProvider:
    def generate(
        self,
        stage: str,
        context: dict,
        *,
        call_context: ProviderCallContext | None = None,
    ) -> dict:
        return validate_stage_output(stage, self._generate(stage, context), context)

    def _generate(self, stage: str, context: dict) -> dict:
        goal, budget, window = context['primary_goal'], context['budget_limit'], context['time_window']
        refs = [card['id'] for card in context['evidence']]
        baseline_analysis = context.get('baseline_analysis')
        if baseline_analysis is None:
            baseline_analysis = analyze_business_baseline(
                BusinessBaseline.model_validate(context.get('business_baseline', {}))
            ).model_dump(mode='json')
        if baseline_analysis['is_calculable']:
            baseline_note = (
                f"{baseline_analysis['disclaimer']}：预计月净节省 "
                f"{baseline_analysis['estimated_monthly_net_savings']} 元。"
            )
            first_baseline_action = '复核用户输入基线并记录试点实际值，禁止把试算当成结果。'
        else:
            first_baseline_action = baseline_analysis['collection_tasks'][0]
            baseline_note = f'内部业务基线仍不完整；首项采集任务：{first_baseline_action}'
        if stage == 'clarifying':
            return {'summary': '演示澄清：请确认目标和约束后再继续。', 'question': context['question'], 'time_window': window, 'budget_limit': budget, 'primary_goal': goal, 'assumptions': ['当前仅演示 AI 售后客服的受限试点流程。', '所有来源材料均为合成示例，尚无真实业务数据。', baseline_note], 'questions': ['你是否确认上述目标、预算、时间约束，并同意先评估受限试点？']}
        if stage == 'planning':
            return {'summary': '演示研究计划：分别检查业务基线与失败风险。', 'queries': [f'AI support baseline workload cost {goal} {window} budget {budget}', f'AI support risk escalation failure counterevidence {goal}'], 'research_questions': ['真实业务基线是否支持受限试点？', '哪些失败风险会改变试点建议？']}
        if stage == 'analyzing':
            return {'summary': '演示分析：增长、成本、风险三个视角。', 'analyses': [
                {'perspective': '增长', 'conclusion': f'推断：需要先验证试点是否推动「{goal}」，不能由模拟材料断言收益。', 'evidence_ids': refs[:1]},
                {'perspective': '成本', 'conclusion': f'推断：预算上限 {budget} 元。{baseline_note}', 'evidence_ids': refs[1:2]},
                {'perspective': '风险', 'conclusion': '推断：退款、投诉和错误承诺必须由人工接管。', 'evidence_ids': refs[-1:]},
            ]}
        if stage == 'challenging':
            return {'summary': '演示反方审查：真实准确率与节省均未证实。', 'objection': '合成材料无法支持全量上线；高风险工单不可自动执行。', 'hidden_assumptions': ['重复工单占比足以覆盖试点成本。', f'团队能在「{window}」内收集有效反馈。', f'{budget} 元预算包含人工审核和返工。'], 'evidence_ids': refs}
        if stage == 'delivering':
            challenge = context['outputs']['challenging']
            gaps = context['outputs']['researching']['research_gaps']
            allocations = [budget // 5, budget * 3 // 5, budget - budget // 5 - budget * 3 // 5]
            actions = [
                {'days': '1–3', 'action': f'{first_baseline_action} 用户时间约束为「{window}」。', 'owner': '运营负责人', 'metric': '记录业务基线输入、数据来源和采集时间', 'stop_condition': '无法获取合法可用的工单样本则暂停', 'budget_limit': allocations[0]},
                {'days': '4–10', 'action': f'仅低风险工单开展人工审核试点，验证「{goal}」。', 'owner': '客服负责人', 'metric': '逐条记录误答、转人工比例和处理时长', 'stop_condition': '出现高风险误答或累计成本达到预算上限则停止', 'budget_limit': allocations[1]},
                {'days': '11–14', 'action': f'对照「{goal}」复盘并由人决定继续、调整或暂缓。', 'owner': '决策负责人', 'metric': f'比较基线与试点结果；总花费不超过 {budget} 元', 'stop_condition': '缺少可信对照数据或时间窗口不足则暂缓扩量', 'budget_limit': allocations[2]},
            ]
            return {'summary': '演示建议：先补真实证据，再由人决定是否试点。', 'recommendation': 'pilot_before_rollout', 'support_score': 45, 'score_explanation': '决策支持度不是成功概率；仅有模拟材料且存在关键研究缺口，最高 59。', 'facts': [{'text': '演示材料陈述（非已核实的现实事实）：' + card['summary'], 'evidence_ids': [card['id']]} for card in context['evidence']], 'inferences': [{'text': f'在预算 {budget} 元、时间约束「{window}」下，可先评估受限试点是否有助于「{goal}」；以下是待确认的 14 天模板，窗口不足时应调整或暂缓。', 'evidence_ids': refs}, {'text': baseline_note, 'evidence_ids': []}], 'objections': [challenge['objection']], 'action_plan': actions, 'time_window': window, 'budget_limit': budget, 'primary_goal': goal, 'research_gaps': gaps}
        raise ValueError('Unsupported demo stage')
