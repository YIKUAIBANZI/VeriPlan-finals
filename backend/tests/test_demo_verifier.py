import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_demo.py"


def _run(output: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["DEEPSEEK_API_KEY"] = "must-not-appear-deepseek"
    environment["TAVILY_API_KEY"] = "must-not-appear-tavily"
    environment["OPENAI_COMPAT_API_KEY"] = "must-not-appear-compat"
    for profile in ("BAILIAN", "MINIMAX", "KIMI"):
        environment[profile + "_API_KEY"] = "must-not-appear-" + profile.lower()
    environment["COUNCIL_MODEL_MAP"] = "expert=kimi"
    return subprocess.run(
        [sys.executable, '-m', 'tests.helpers', str(SCRIPT), "--output", str(output)],
        cwd=ROOT / 'backend',
        env=environment,
        capture_output=True,
        text=True,
    )


def test_verifier_proves_offline_demo_gates_and_export(tmp_path):
    output = tmp_path / "demo-verification.json"

    result = _run(output)

    assert result.returncode == 0, result.stderr
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert json.loads(result.stdout) == evidence
    assert evidence["schema_version"] == 1
    assert evidence["verification_mode"] == "offline_demo"
    assert evidence["network_access"] == "blocked"
    assert evidence["real_provider_requests"] == 0
    assert evidence["provider_calls"] == []
    assert evidence["checkpoints"] == [
        "draft",
        "awaiting_confirmation",
        "planning",
        "awaiting_review",
        "deferred",
    ]
    assert evidence["human_gates"] == {
        "clarification_confirmed": True,
        "final_review": "deferred",
    }
    assert evidence["council"]["is_split"] is True
    assert set(evidence["council"]["stances"]) == {"opportunity", "cfo", "risk", "expert"}
    assert evidence["expert"] == {"expert_kind": "customer", "expert_reason": "按场景默认", "expert_source": "scenario_default"}
    assert evidence["challenge"]["blocker_count"] >= 1
    assert evidence["challenge"]["novel_objection_count"] >= 1
    assert evidence["challenge"]["calibration_warning_count"] >= 1
    assert evidence["outcome"]["error_pct"] == -40
    assert evidence["calibration"]["sample_count"] >= 3
    assert evidence["all_evidence_demo"] is True
    assert evidence["evidence_domains"] == ["demo.invalid"]
    assert evidence["evidence_count"] >= 3
    assert evidence["baseline_analysis"] == {
        "known_field_count": 8,
        "is_calculable": True,
        "estimated_monthly_net_savings": 1257.0,
        "disclaimer": "用户输入试算，不是已验证收益",
    }
    assert evidence["memo"]["research_gap_count"] >= 1
    assert evidence["memo"]["action_count"] == 3
    assert evidence["memo"]["action_budget_total"] == 8000
    assert evidence["memo"]["markdown_bytes"] > 500
    assert len(evidence["memo"]["markdown_sha256"]) == 64
    rendered = output.read_text(encoding="utf-8") + result.stdout + result.stderr
    assert "must-not-appear-deepseek" not in rendered
    assert "must-not-appear-tavily" not in rendered
    assert "must-not-appear-compat" not in rendered
    assert "must-not-appear-" not in rendered


def test_verifier_refuses_to_overwrite_existing_evidence(tmp_path):
    output = tmp_path / "demo-verification.json"
    output.write_text("keep me\n", encoding="utf-8")

    result = _run(output)

    assert result.returncode != 0
    assert "already exists" in result.stderr.casefold()
    assert output.read_text(encoding="utf-8") == "keep me\n"
