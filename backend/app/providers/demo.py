"""Synthetic fixtures, never fetched research or independent real-world sources."""
from app.baseline import analyze_business_baseline
from app.providers.contracts import COUNCIL_ROLES, council_disagreement, validate_stage_output
from app.providers.base import ProviderCallContext
from app.providers.council import selected_expert
from app.schemas import BusinessBaseline, EvidenceCard


class DemoSearchProvider:
    def search(
        self,
        query: str,
        *,
        call_context: ProviderCallContext | None = None,
    ) -> list[EvidenceCard]:
        if query.startswith('veriplan followup '):
            topic = 'market' if 'market' in query else 'cost' if 'cost' in query else 'risk'
            return [EvidenceCard(title=f'模拟：补充核验 {topic}',
                summary=f'合成补充材料 {topic}：需采集真实对照数据并核验停止条件。',
                source_url=f'https://demo.invalid/followup-{topic}',
                stance='context', reliability='low', is_demo=True)]
        fixtures = [
            ('模拟：输入基线', '模拟内部记录：数字假设需核对来源，尚未验证真实收益。', 'baseline', 'context'),
            ('模拟：人工升级流程', '模拟流程文档：扩大投入和重大承诺需要人工确认。', 'handoff', 'supports'),
            ('模拟：失败风险案例', '模拟风险案例：错误承诺可能增加返工，小规模试验也需要停止条件。', 'risk', 'opposes'),
        ]
        chosen = fixtures[1:] if 'risk' in query.lower() else fixtures[:2]
        return [EvidenceCard(title=title, summary=summary, source_url=f'https://demo.invalid/{slug}', stance=stance, reliability='low', is_demo=True) for title, summary, slug, stance in chosen]


class DemoModelProvider:
    profile = 'demo'
    model_label = 'Demo · 合成模型'
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
        scenario = context.get('scenario', 'ai_tool_pilot')
        scenario_labels = {'ai_tool_pilot': 'AI 售后客服试点', 'first_hire': '首位员工招聘',
                           'big_order': '大订单承接', 'marketing_spend': '营销投入', 'general': '经营决策'}
        subject = scenario_labels[scenario]
        if scenario != 'ai_tool_pilot':
            baseline_note = '用户的数字假设需要实际结果验证，当前未验证收益。'
            first_baseline_action = '核对数字假设与来源，明确负责人和停止条件。'
        elif baseline_analysis['is_calculable']:
            baseline_note = (
                f"{baseline_analysis['disclaimer']}：预计月净节省 "
                f"{baseline_analysis['estimated_monthly_net_savings']} 元。"
            )
            first_baseline_action = '复核用户输入基线并记录试点实际值，禁止把试算当成结果。'
        else:
            first_baseline_action = baseline_analysis['collection_tasks'][0]
            baseline_note = f'内部业务基线仍不完整；首项采集任务：{first_baseline_action}'
        if stage == 'ablation':
            return {'risks': [f'{subject}的预期收益可能无法兑现。', '实际成本可能超过预算，需要停止条件。']}
        if stage == 'clarifying':
            return {'summary': '演示澄清：请确认目标和约束后再继续。', 'question': context['question'], 'time_window': window, 'budget_limit': budget, 'primary_goal': goal, 'assumptions': [f'当前演示{subject}，尚无真实业务结果。', '所有来源材料均为合成示例，尚无真实业务数据。', baseline_note], 'questions': ['你是否确认上述目标、预算、时间约束，并同意先评估受限试点？']}
        if stage == 'planning':
            if context.get('_research_followup'):
                return {'queries': [f'veriplan followup {subject} market 客户满意度 投诉 流失案例',
                                    f'veriplan followup {subject} cost 人工监督 返工 隐性成本']}
            return {
                'summary': '演示研究计划：分别检查可行性与失败案例、成本收益、合规规则，并补查客户影响。',
                'queries': [
                    f'{subject} 能力边界 真实案例 失败案例 交付质量 risk',
                    f'{subject} 价格 行业基准 隐性成本',
                    f'{subject} 法律 平台规则 合同',
                ],
                'research_questions': ['能力边界和真实失败案例是否支持执行？',
                                       '收益能否覆盖价格、人工监督与返工成本？',
                                       '法律、平台规则和合同有哪些限制？',
                                       '客户体验与市场需求会受到什么影响？'],
            }
        if stage == 'analyzing':
            role = context.get('_council_member')
            if role is None:
                members = [self._generate(stage, dict(context, _council_member=member)) for member in COUNCIL_ROLES]
                return {'summary': '演示委员会：四位独立委员意见分裂。', 'members': members, 'disagreement': council_disagreement(members)}
            stances = {'opportunity': 'support', 'cfo': 'oppose', 'risk': 'conditional', 'expert': 'oppose'}
            headlines = {'opportunity': '值得验证目标收益', 'cfo': '当前证据不足以承诺预算', 'risk': '必须先明确停止条件', 'expert': '专业条件尚未核实，不宜直接投入'}
            return {**({'expert_kind': selected_expert(context)} if role == 'expert' else {}), 'role': role, 'stance': stances[role], 'headline': headlines[role],
                    'reasoning': f'推断：在 {window}、预算 {budget} 元内验证「{goal}」。{baseline_note}',
                    'key_points': ['演示材料不构成真实收益证明。'],
                    'challenged_assumption_ids': [item['id'] for item in context.get('assumptions', []) if 'id' in item],
                    'evidence_ids': refs[:1], 'confidence': 65}
        if stage == 'challenging':
            ids = [item['id'] for item in context.get('assumptions', []) if 'id' in item]
            return {'summary': '演示反方：关键收益尚未证实。',
                    'premortem': f'假设 {window} 后失败：预期收益未兑现，预算耗尽，缺少及时停止的依据。',
                    'objections': [{'id': 'O1', 'text': '尚无可信对照验证收益，不能承诺全面投入。',
                                    'severity': 'blocker', 'targets_assumption_ids': ids,
                                    'overlaps_known_risk_index': None, 'evidence_ids': refs}],
                    'hidden_assumptions': ['预期收益能覆盖全部执行和返工成本。']}
        if stage == 'delivering':
            challenge = context['outputs']['challenging']
            gaps = context['outputs']['researching']['research_gaps']
            allocations = [budget // 5, budget * 3 // 5, budget - budget // 5 - budget * 3 // 5]
            days = context.get('horizon_days', 14)
            first_end, second_end = max(1, days * 3 // 14), max(2, days * 10 // 14)
            actions = [
                {'days': f'1–{first_end}', 'action': f'{first_baseline_action} 用户时间约束为「{window}」。', 'owner': '运营负责人', 'metric': '记录业务基线输入、数据来源和采集时间', 'stop_condition': '无法取得合法可用的验证样本则暂停', 'budget_limit': allocations[0]},
                {'days': f'{first_end + 1}–{second_end}', 'action': f'以受限投入验证{subject}是否有助于「{goal}」，保留人工审核。', 'owner': '执行负责人', 'metric': '记录实际成本、收益与失败案例', 'stop_condition': '出现不可接受损失或累计成本达到预算上限则停止', 'budget_limit': allocations[1]},
                {'days': f'{second_end + 1}–{days}', 'action': f'对照「{goal}」复盘并由人决定继续、调整或暂缓。', 'owner': '决策负责人', 'metric': f'比较基线与试点结果；总花费不超过 {budget} 元', 'stop_condition': '缺少可信对照数据或时间窗口不足则暂缓扩量', 'budget_limit': allocations[2]},
            ]
            return {'summary': '演示建议：先补真实证据，再由人决定是否试点。', 'recommendation': 'small_test_first', 'conditions': [{'objection_id': item['id'], 'condition': '先取得真实对照证据并经人工复核，未满足则暂停投入。'} for item in challenge.get('objections', []) if item['severity'] == 'blocker'], 'support_score': 45, 'score_explanation': '决策支持度不是成功概率；仅有模拟材料且存在关键研究缺口，最高 59。', 'facts': [{'text': '演示材料陈述（非已核实的现实事实）：' + card['summary'], 'evidence_ids': [card['id']]} for card in context['evidence']], 'inferences': [{'text': f'在预算 {budget} 元、时间约束「{window}」下，可先评估受限试点是否有助于「{goal}」；以下是待确认的 {window}行动计划，窗口不足时应调整或暂缓。', 'evidence_ids': refs}, {'text': baseline_note, 'evidence_ids': []}], 'objections': [item['text'] for item in challenge.get('objections', [])] or [challenge.get('objection', '证据仍需核验。')], 'action_plan': actions, 'time_window': window, 'budget_limit': budget, 'primary_goal': goal, 'research_gaps': gaps}
        raise ValueError('Unsupported demo stage')


def ensure_demo_calibration_seeds(repository):
    """Seed only an empty demo calibration history; never add samples to Live."""
    from app.calibration import calibration_profile
    from app.schemas import RetrospectiveCreate
    if calibration_profile(repository.list(), mode='demo')['samples']:
        return
    for index in (1, 2):
        seed_id = f'00000000-0000-0000-0000-00000000000{index}'
        try:
            repository.get(seed_id)
            continue
        except KeyError:
            pass
        categories = ('revenue', 'cost', 'volume', 'time', 'conversion', 'other')
        repository.create_retrospective(RetrospectiveCreate(
            question=f'合成回溯样本 {index}：过去是否应该增加业务投入？', scenario='general',
            decision_date=f'2026-08-0{index}', note='合成 Demo 种子，不是真实用户结果。',
            assumptions=[dict(label=f'合成{category}假设', category=category, value=100,
                              unit='合成单位', confidence=80) for category in categories],
            actuals=[dict(assumption_id=f'A{i}', actual_value=140 if category in {'cost', 'time'} else 60)
                     for i, category in enumerate(categories, 1)],
        ), mode='demo', seed_id=seed_id)
