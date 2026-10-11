#!/usr/bin/env python3
"""Single-model versus council risk extraction. Demo is offline by default."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def run_ablation(questions: list[dict], *, output_dir: Path, model_provider=None,
                 search_provider=None, mode='demo', authorized=False, settings=None) -> dict:
    if mode not in {'demo', 'live'} or (mode == 'live' and not authorized):
        raise ValueError('Live ablation requires explicit authorization')
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.config import Settings
    from app.providers.demo import DemoModelProvider, DemoSearchProvider
    from app.providers.base import ProviderCallContext
    from app.providers.contracts import validate_stage_output
    from app.repository import DecisionRepository
    from app.schemas import DecisionCreate
    from app.workflow import WorkflowEngine
    ids = [item.get('question_id') for item in questions]
    if not questions or any(not isinstance(item, str) or not item.strip() for item in ids) or len(set(ids)) != len(ids):
        raise ValueError('Questions require unique nonempty question_id values')
    # Validate every input before any paid work or output writes.
    payloads = [DecisionCreate(**{key: value for key, value in item.items() if key != 'question_id'}) for item in questions]
    if settings is None:
        settings = Settings(app_mode='demo', enable_live_workflow=False) if mode == 'demo' else Settings()
    if mode == 'live' and (settings.app_mode != 'live' or not settings.enable_live_workflow):
        raise ValueError('Live configuration remains locked')
    output_dir = Path(output_dir)
    if any((output_dir / name).exists() for name in ('risks.csv', 'summary.md')):
        raise ValueError('Output already exists')
    rows, counts = [], {'A': 0, 'B': 0}
    with tempfile.TemporaryDirectory(prefix='veriplan-ablation-') as temporary, ExitStack() as stack:
        if mode == 'demo':
            def blocked(*args, **kwargs):
                raise RuntimeError('Network blocked during offline ablation')
            for target in ('socket.socket.connect', 'socket.socket.connect_ex', 'socket.getaddrinfo'):
                stack.enter_context(patch(target, side_effect=blocked))
        database = Path(temporary) / 'ablation.db'
        if mode == 'live':
            with patch.dict(os.environ, {'APP_MODE': 'demo', 'ENABLE_LIVE_WORKFLOW': 'false', 'DATABASE_URL': f'sqlite:///{Path(temporary) / "import.db"}'}):
                from app.main import create_app
            from fastapi.testclient import TestClient
            app = create_app(database, settings=settings, model_provider=model_provider, search_provider=search_provider)
            stack.enter_context(TestClient(app))
            if not app.state.live_available:
                raise ValueError('Live providers are not configured')
            repo, engine = app.state.repository, app.state.workflow
            model = engine._model
        else:
            repo = DecisionRepository(database)
            stack.callback(repo._engine.dispose)
            model = model_provider or DemoModelProvider()
            engine = WorkflowEngine(repo, model_provider=model, search_provider=search_provider or DemoSearchProvider(), mode=mode)
        for question_id, payload in zip(ids, payloads):
            # Both arms use the very same model instance and original input constraints.
            decision = repo.create(payload, mode=mode)
            context = decision.model_dump(mode='json')
            single = validate_stage_output('ablation', model.generate('ablation', context,
                call_context=ProviderCallContext(decision.id, 'ablation:A', stage='ablation')), context)
            for risk in single['risks']:
                rows.append(dict(question_id=question_id, arm='A', risk_text=risk, label=''))
                counts['A'] += 1
            if engine.run(decision.id).status.value != 'awaiting_confirmation':
                raise RuntimeError('Arm B clarification failed')
            engine.confirm_clarification(decision.id)
            result = engine.run(decision.id)
            if result.status.value != 'awaiting_review':
                raise RuntimeError('Arm B workflow failed')
            engine.apply_review(decision.id, action='deferred', note='Ablation only; no business execution.')
            for objection in result.outputs['challenging']['objections']:
                rows.append(dict(question_id=question_id, arm='B', risk_text=objection['text'], label=''))
                counts['B'] += 1
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / 'risks.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['question_id', 'arm', 'risk_text', 'label'])
        writer.writeheader()
        writer.writerows(rows)
    lines = ['# 风险对照实验', '', f'模式：{mode}；问题数：{len(questions)}', '',
             '| 组别 | 风险条数 |', '|---|---:|', f"| A 单模型单次调用 | {counts['A']} |", f"| B 完整委员会工作流 | {counts['B']} |", '',
             'label 留空供人工标注；条数不等于风险质量，也不证明委员会更优。',
             'B 包含额外研究和多次调用，当前对照未控制上下文和调用成本；Demo 是合成输出。', '']
    (output_dir / 'summary.md').write_text('\n'.join(lines), encoding='utf-8')
    return dict(mode=mode, question_count=len(questions), risk_counts=counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--i-authorize-live', action='store_true')
    args = parser.parse_args()
    if args.live and not args.i_authorize_live:
        parser.error('--live requires --i-authorize-live')
    try:
        questions = [json.loads(line) for line in args.input.read_text(encoding='utf-8').splitlines() if line.strip()]
        result = run_ablation(questions, output_dir=args.output_dir, mode='live' if args.live else 'demo', authorized=args.i_authorize_live)
    except Exception:
        print('Ablation failed; check input, output path and provider configuration. No private error details are printed.', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
