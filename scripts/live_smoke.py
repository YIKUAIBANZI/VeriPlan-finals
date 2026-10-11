#!/usr/bin/env python3
"""Explicitly authorized Live smoke; keys come only from process environment."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from time import monotonic
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = dict(question='是否应该为独立工作室投入三万元扩展交付业务？', scenario='general',
               horizon_days=90, budget_limit=30000, primary_goal='验证新增业务收益',
               known_risks=['需求不稳定'], assumptions=[dict(label='新增收入', category='revenue',
               value=20000, unit='元/月', confidence=70)])


def run_smoke(*, authorized: bool, settings=None, model_provider=None, search_provider=None) -> dict:
    if not authorized:
        raise ValueError('Explicit --i-authorize-live is required')
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.config import Settings
    settings = settings or Settings()
    if settings.app_mode != 'live' or not settings.enable_live_workflow:
        raise ValueError('APP_MODE=live and ENABLE_LIVE_WORKFLOW=true are required')
    with tempfile.TemporaryDirectory(prefix='veriplan-live-smoke-') as temporary:
        database = Path(temporary) / 'smoke.db'
        # Avoid creating a default database or adapters at module import.
        with patch.dict(os.environ, {'DATABASE_URL': f'sqlite:///{Path(temporary) / "import.db"}', 'APP_MODE': 'demo', 'ENABLE_LIVE_WORKFLOW': 'false'}):
            from app.main import create_app
        from fastapi.testclient import TestClient
        app = create_app(database, settings=settings, model_provider=model_provider, search_provider=search_provider)
        started = monotonic()
        decision_id = None
        snapshot = {}
        result = {'mode': 'live', 'passed': False, 'stages': {}, 'provider_call_count': 0,
                  'provider_calls_by_operation': {}, 'human_gates': [], 'error_code': None}
        with TestClient(app) as client:
            try:
                if not app.state.live_available:
                    raise ValueError('live_locked')
                response = client.post('/api/decisions', json=PAYLOAD)
                if response.status_code != 201:
                    raise ValueError('create_failed')
                decision_id = response.json()['id']
                url = '/api/decisions/' + decision_id
                client.post(url + '/run')
                snapshot = client.get(url).json()
                if snapshot['status'] != 'awaiting_confirmation':
                    raise ValueError('clarification_failed')
                if client.post(url + '/confirm').status_code != 200:
                    raise ValueError('confirmation_failed')
                result['human_gates'].append('clarification_confirmed_by_smoke_operator')
                client.post(url + '/run')
                snapshot = client.get(url).json()
                if snapshot['status'] != 'awaiting_review':
                    raise ValueError('workflow_failed')
                response = client.post(url + '/review', json={'action': 'deferred', 'note': 'Authorized smoke only; no business execution.'})
                if response.status_code != 200 or response.json()['status'] != 'deferred':
                    raise ValueError('review_failed')
                snapshot = response.json()
                result['human_gates'].append('deferred_by_smoke_operator')
                result['passed'] = True
            except Exception:
                # Neither exception messages nor model content may enter the artifact.
                result['error_code'] = 'smoke_failed'
            if decision_id:
                snapshot = client.get('/api/decisions/' + decision_id).json()
                calls = app.state.repository.list_provider_calls(decision_id)
                result['provider_call_count'] = len(calls)
                result['provider_calls_by_operation'] = dict(Counter(call['logical_operation'] for call in calls))
                starts = {}
                for event in snapshot['events']:
                    stage = event['stage']
                    at = datetime.fromisoformat(event['created_at'].replace('Z', '+00:00'))
                    if event['status'] == 'started':
                        starts[stage] = at
                    elif event['status'] in {'completed', 'failed'} and stage in starts:
                        result['stages'][stage] = round((at - starts[stage]).total_seconds(), 4)
                result['final_status'] = snapshot['status']
                # Failure codes are redacted stable identifiers, safe to record.
                result['failure'] = snapshot.get('failure')
        result['elapsed_seconds'] = round(monotonic() - started, 4)
        result['within_120_seconds'] = result['elapsed_seconds'] <= 120
        result['passed'] = result['passed'] and result['within_120_seconds']
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--i-authorize-live', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.i_authorize_live:
        parser.error('refusing Live requests without --i-authorize-live')
    if args.output.exists():
        parser.error('output already exists')
    try:
        result = run_smoke(authorized=True)
    except Exception:
        print('Live smoke unavailable; verify environment configuration. No secret details are printed.', file=sys.stderr)
        return 1
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding='utf-8')
    print(rendered, end='')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
