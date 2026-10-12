"""Allowlisted council routing. No secrets, URLs or arbitrary options in the map."""
import re

from app.providers.contracts import COUNCIL_ROLES

PROFILE_URLS = {
    'bailian': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    'minimax': 'https://api.minimaxi.com/v1',
    'kimi': 'https://api.moonshot.cn/v1',
    # 并行智算云 (Paratera), the track sponsor's model platform.
    'paratera': 'https://llmapi.paratera.com/v1',
}
PROFILE_MODELS = {'bailian': 'qwen3.8-flash', 'minimax': 'MiniMax-M2.5-highspeed', 'kimi': 'kimi-k2.6', 'paratera': 'Qwen3.8-Flash'}
PROFILES = ('deepseek', *PROFILE_URLS)


def parse_council_model_map(value: str) -> dict[str, tuple[str, str | None]]:
    if not value.strip():
        return {}
    result = {}
    for entry in value.split(','):
        match = re.fullmatch(r'\s*([a-z_]+)\s*=\s*([a-z_]+)(?::([A-Za-z0-9][A-Za-z0-9._-]{0,127}))?\s*', entry)
        if not match:
            raise ValueError('Invalid COUNCIL_MODEL_MAP syntax')
        role, profile, model = match.groups()
        if role not in COUNCIL_ROLES or profile not in PROFILES or role in result:
            raise ValueError('Invalid or duplicate COUNCIL_MODEL_MAP seat/profile')
        result[role] = (profile, model)
    return result


def model_label(profile: str, model: str) -> str:
    if profile == 'deepseek':
        return 'DeepSeek ' + model.removeprefix('deepseek-')
    if profile == 'bailian':
        return ('通义千问 ' if model.lower().startswith('qwen') else '百炼 ') + model
    if profile == 'minimax':
        return 'MiniMax ' + model.removeprefix('MiniMax-')
    if profile == 'kimi':
        return 'Kimi ' + model
    if profile == 'paratera':
        return '并行智算云 ' + model
    return f'{profile} {model}'
