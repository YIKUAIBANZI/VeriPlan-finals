#!/usr/bin/env python3
"""Run the complete VeriPlan demo offline and emit machine-readable evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PAYLOAD = {
    "question": "Should our small cross-border ecommerce team pilot AI support before rollout?",
    "scenario": "ai_tool_pilot",
    "horizon_days": 14,
    "assumptions": [{"label": "新增收入", "category": "revenue", "value": 20000, "unit": "元/月", "confidence": 80}],
    "known_risks": ["真实样本不足"],
    "budget_limit": 8_000,
    "primary_goal": "Reduce repetitive support workload without unsafe customer promises",
    "business_baseline": {
        "monthly_ticket_volume": 1_200,
        "repetitive_ticket_rate": 60,
        "average_handle_minutes": 8,
        "loaded_hourly_cost": 45,
        "expected_ai_resolution_rate": 70,
        "review_minutes_per_ai_ticket": 1.5,
        "monthly_tool_cost": 1_200,
        "max_acceptable_error_rate": 2,
    },
}


class VerificationError(RuntimeError):
    """The offline demo did not satisfy its evidence contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _offline_environment(database: Path) -> None:
    os.environ["APP_MODE"] = "demo"
    os.environ["ENABLE_LIVE_WORKFLOW"] = "false"
    os.environ["DATABASE_URL"] = f"sqlite:///{database}"
    os.environ.pop("DEEPSEEK_API_KEY", None)
    os.environ.pop("TAVILY_API_KEY", None)
    os.environ.pop("OPENAI_COMPAT_API_KEY", None)


def verify() -> dict:
    with tempfile.TemporaryDirectory(prefix="veriplan-offline-demo-") as temporary:
        temporary_path = Path(temporary)
        _offline_environment(temporary_path / "module-import.db")
        sys.path.insert(0, str(BACKEND))
        from fastapi.testclient import TestClient
        from app import main as main_module

        checkpoints: list[str] = []
        try:
            app = main_module.create_app(temporary_path / "demo.db")
            with patch(
                "socket.socket.connect",
                side_effect=RuntimeError("network access blocked by demo verifier"),
            ), patch("socket.socket.connect_ex", side_effect=RuntimeError("network access blocked")), patch("socket.getaddrinfo", side_effect=RuntimeError("DNS blocked")):
                with TestClient(app) as client:
                    health = client.get("/api/health")
                    _require(health.status_code == 200, "health check failed")
                    _require(health.json()["mode"] == "demo", "app is not in demo mode")
                    _require(
                        health.json()["live_available"] is False,
                        "live workflow unexpectedly became available",
                    )

                    created_response = client.post("/api/decisions", json=PAYLOAD)
                    _require(created_response.status_code == 201, "decision creation failed")
                    created = created_response.json()
                    decision_id = created["id"]
                    decision_url = f"/api/decisions/{decision_id}"
                    checkpoints.append(created["status"])

                    first_run = client.post(decision_url + "/run")
                    _require(first_run.status_code == 202, "clarification run failed")
                    awaiting_confirmation = client.get(decision_url).json()
                    _require(
                        awaiting_confirmation["status"] == "awaiting_confirmation",
                        "first human gate was skipped",
                    )
                    checkpoints.append(awaiting_confirmation["status"])

                    confirmed = client.post(decision_url + "/confirm")
                    _require(confirmed.status_code == 200, "clarification confirmation failed")
                    _require(confirmed.json()["status"] == "planning", "planning did not start")
                    checkpoints.append(confirmed.json()["status"])

                    second_run = client.post(decision_url + "/run")
                    _require(second_run.status_code == 202, "delivery run failed")
                    delivered = client.get(decision_url).json()
                    _require(
                        delivered["status"] == "awaiting_review",
                        "final human review gate was skipped",
                    )
                    checkpoints.append(delivered["status"])

                    council = delivered['outputs']['analyzing']['disagreement']
                    challenge = delivered['outputs']['challenging']
                    blockers = [item for item in challenge['objections'] if item['severity'] == 'blocker']
                    _require(council['is_split'], 'council has no disagreement')
                    _require(bool(blockers), 'challenge has no blocker')
                    _require(challenge['novel_objection_count'] >= 1, 'no novel risk')
                    _require(bool(challenge['calibration_warnings']), 'missing historical bias warning')
                    _require(delivered['memo']['recommendation'] != 'go', 'blocker did not prevent go')
                    labeled = client.post(decision_url + '/objection-labels', json={'labels': {blockers[0]['id']: 'adopted'}})
                    _require(labeled.status_code == 200, 'objection labeling failed')

                    evidence = delivered["evidence"]
                    _require(len(evidence) >= 3, "demo evidence is incomplete")
                    _require(
                        all(item["is_demo"] for item in evidence),
                        "non-demo evidence appeared in offline verification",
                    )
                    domains = sorted({urlsplit(item["source_url"]).hostname for item in evidence})
                    _require(domains == ["demo.invalid"], "unexpected evidence source")

                    baseline = delivered["baseline_analysis"]
                    _require(baseline["known_field_count"] == 8, "baseline is incomplete")
                    _require(baseline["is_calculable"] is True, "baseline is not calculable")
                    _require(
                        baseline["estimated_monthly_net_savings"] == 1_257.0,
                        "baseline calculation changed",
                    )

                    memo = delivered["memo"]
                    _require(memo is not None, "decision memo is missing")
                    gaps = memo["research_gaps"]
                    _require(bool(gaps), "demo research gaps were hidden")
                    actions = memo["action_plan"]
                    action_budget_total = sum(item["budget_limit"] for item in actions)
                    _require(action_budget_total <= 8_000, "action budget exceeds input")

                    exported = client.get(decision_url + "/export.md")
                    _require(exported.status_code == 200, "Markdown export failed")
                    markdown = exported.content
                    _require(b"demo.invalid" in markdown, "export omitted demo evidence")

                    reviewed = client.post(
                        decision_url + "/review",
                        json={
                            "action": "deferred",
                            "note": "Offline verification only; real evidence remains required.",
                        },
                    )
                    _require(reviewed.status_code == 200, "final review failed")
                    _require(reviewed.json()["status"] == "deferred", "review was not recorded")
                    checkpoints.append(reviewed.json()["status"])

                    outcome_response = client.post(decision_url + '/outcomes', json={
                        'checkpoint': 'day_30', 'actuals': [{'assumption_id': 'A1', 'actual_value': 12000}],
                        'note': '合成离线回填，仅用于验证。',
                    })
                    _require(outcome_response.status_code == 200, 'outcome recording failed')
                    actual = outcome_response.json()['outcomes'][0]['actuals'][0]
                    _require(actual['error_pct'] == -40, 'outcome error calculation changed')
                    calibration = client.get('/api/calibration').json()
                    _require(len(calibration['samples']) >= 3, 'calibration samples missing')
                    exported = client.get(decision_url + '/export.md')
                    _require(exported.status_code == 200 and '回填对照' in exported.text, 'final export is incomplete')
                    markdown = exported.content
                    provider_calls = app.state.repository.list_provider_calls(decision_id)
                    _require(provider_calls == [], "provider calls occurred in demo verification")
        finally:
            main_module.app.state.repository._engine.dispose()

    return {
        "schema_version": 1,
        "verification_mode": "offline_demo",
        "network_access": "blocked",
        "real_provider_requests": 0,
        "provider_calls": provider_calls,
        "decision_id": decision_id,
        "council": council,
        "challenge": {"blocker_count": len(blockers), "novel_objection_count": challenge['novel_objection_count'],
                      "calibration_warning_count": len(challenge['calibration_warnings'])},
        "outcome": actual,
        "calibration": {"sample_count": len(calibration['samples']), "categories": calibration['categories']},
        "checkpoints": checkpoints,
        "human_gates": {
            "clarification_confirmed": True,
            "final_review": "deferred",
        },
        "all_evidence_demo": True,
        "evidence_domains": domains,
        "evidence_count": len(evidence),
        "baseline_analysis": {
            "known_field_count": baseline["known_field_count"],
            "is_calculable": baseline["is_calculable"],
            "estimated_monthly_net_savings": baseline[
                "estimated_monthly_net_savings"
            ],
            "disclaimer": baseline["disclaimer"],
        },
        "memo": {
            "support_score": memo["support_score"],
            "research_gap_count": len(gaps),
            "action_count": len(actions),
            "action_budget_total": action_budget_total,
            "markdown_bytes": len(markdown),
            "markdown_sha256": hashlib.sha256(markdown).hexdigest(),
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    output = args.output.resolve()
    if output.exists() and not args.force:
        print("demo verification failed: output already exists", file=sys.stderr)
        return 1
    try:
        evidence = verify()
    except Exception as error:
        print(f"demo verification failed: {error}", file=sys.stderr)
        return 1
    rendered = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(output)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
