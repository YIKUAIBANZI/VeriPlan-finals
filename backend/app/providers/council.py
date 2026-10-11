"""Code-owned council identities and deterministic expert selection."""
from typing import Literal, get_args

ExpertKind = Literal['legal_compliance', 'customer', 'operations', 'platform_rules', 'personal_longterm']
EXPERT_KINDS = get_args(ExpertKind)
EXPERT_LABELS = dict(zip(EXPERT_KINDS, ('法务合规', '客户视角', '运营产能', '平台规则', '个人长期发展')))
SCENARIO_EXPERTS = {'first_hire': 'legal_compliance', 'big_order': 'operations',
                    'marketing_spend': 'platform_rules', 'ai_tool_pilot': 'customer',
                    'general': 'personal_longterm'}
EXPERT_INSTRUCTIONS = {
    'legal_compliance': '审查合同、用工和合规的不确定性，指出需要专业核验的事项。',
    'customer': '从客户需求、使用体验和接受条件审查方案。',
    'operations': '审查交付产能、流程、资源瓶颈和履约条件。',
    'platform_rules': '审查平台政策、流量依赖和规则变化；未经证据核验不得断言规则。',
    'personal_longterm': '审查长期目标、个人能力积累和机会成本。',
}


def select_expert(payload, context):
    kind, reason = payload.get('expert_kind'), payload.get('expert_reason')
    default = SCENARIO_EXPERTS.get(context.get('scenario', 'ai_tool_pilot'), 'personal_longterm')
    if kind not in EXPERT_KINDS or not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 80:
        return dict(expert_kind=default, expert_reason='按场景默认', expert_source='scenario_default')
    # Preserve the code-owned fallback on a second contract validation.
    source = ('scenario_default' if payload.get('expert_source') == 'scenario_default'
              and kind == default and reason == '按场景默认' else 'model')
    return dict(expert_kind=kind, expert_reason=reason.strip(), expert_source=source)


def selected_expert(context):
    return select_expert(context.get('outputs', {}).get('planning', {}), context)['expert_kind']
