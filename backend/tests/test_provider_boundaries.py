"""Adversarial provider and persistence checks for the local runner boundary."""
from threading import Event, Thread
import pytest
from fastapi.testclient import TestClient
from tests.helpers import login

from app.main import create_app
from app.providers.base import ProviderError
from app.providers.demo import DemoModelProvider, DemoSearchProvider
from app.repository import DecisionRepository
from app.schemas import DecisionStatus, EvidenceCard
from app.workflow import WorkflowEngine
from tests.test_api import payload
from tests.test_repository import sample_decision
from tests.test_workflow import ready


class OverconfidentModel(DemoModelProvider):
    def generate(self, stage, context, *, call_context=None):
        output = super().generate(stage, context, call_context=call_context)
        if stage == 'delivering':
            output['support_score'] = 99
        return output


class ExtraFieldModel(DemoModelProvider):
    def generate(self, stage, context, *, call_context=None):
        output = super().generate(stage, context, call_context=call_context)
        if stage == 'clarifying':
            output['untrusted_extra'] = 'must not persist'
        return output


def real_evidence(title, summary, source_url, reliability="medium"):
    return EvidenceCard(
        is_demo=False,
        title=title,
        summary=summary,
        source_url=source_url,
        stance="context",
        reliability=reliability,
    )


def run_research_stage(repository, search_provider):
    decision = repository.create(sample_decision())
    repository.save_stage_output(
        decision.id,
        "planning",
        {
            "summary": "Search two independent angles.",
            "queries": ["baseline", "risk"],
            "research_questions": ["真实业务基线是什么？"],
        },
    )
    engine = WorkflowEngine(repository, search_provider=search_provider)
    output = engine._run_stage("researching", repository.get(decision.id))
    return output, repository.get(decision.id)


def test_workflow_rejects_invalid_provider_output_before_persistence(tmp_path):
    repository = DecisionRepository(tmp_path / 'db')
    engine = WorkflowEngine(repository, model_provider=ExtraFieldModel())
    decision = repository.create(sample_decision())

    failed = engine.run(decision.id)

    assert failed.status is DecisionStatus.failed
    assert failed.failure['stage'] == 'clarifying'
    assert 'clarifying' not in failed.outputs
    assert 'untrusted_extra' not in failed.model_dump_json()


@pytest.mark.parametrize('count', [0, 1, 3])
def test_engine_caps_provider_score_when_only_demo_or_missing_evidence(tmp_path, count):
    class LimitedSearch(DemoSearchProvider):
        def search(self, query, *, call_context=None):
            cards = super().search(
                'baseline', call_context=call_context
            ) + super().search('risk', call_context=call_context)
            return cards[:count]
    repository = DecisionRepository(tmp_path / 'db')
    engine = WorkflowEngine(repository, OverconfidentModel(), LimitedSearch())
    result = engine.run(ready(repository, engine))
    assert result.status is DecisionStatus.awaiting_review
    assert result.memo['support_score'] == 59


def test_live_partial_search_failure_continues_and_caps_support(tmp_path):
    class PartialSearch:
        def search(self, query, *, call_context=None):
            if query == "risk":
                raise ProviderError("search_timeout")
            return [
                real_evidence(
                    query,
                    f"Evidence for {query}",
                    f"https://{query}.example/report",
                )
            ]

    repository = DecisionRepository(tmp_path / "db")
    decision = repository.create(sample_decision(), mode="live")
    repository.save_stage_output(
        decision.id,
        "planning",
        {
            "summary": "Plan",
            "queries": ["baseline", "risk", "cost"],
            "research_questions": ["哪些风险会改变建议？"],
        },
    )
    engine = WorkflowEngine(
        repository,
        OverconfidentModel(),
        PartialSearch(),
        mode="live",
    )

    output = engine._run_stage("researching", repository.get(decision.id))
    repository.save_stage_output(decision.id, "researching", output)
    repository.save_stage_output(
        decision.id,
        "challenging",
        {"summary": "Challenge", "objection": "Evidence remains incomplete."},
    )
    delivered = engine._run_stage("delivering", repository.get(decision.id))

    assert len(repository.get(decision.id).evidence) == 2
    assert repository.get(decision.id).research_queries[1].status == "failed"
    assert any("risk" in gap for gap in output["research_gaps"])
    assert delivered["support_score"] == 59


def test_live_zero_evidence_fails_but_retry_skips_successful_empty_query(tmp_path):
    calls = []

    class RecoveringSearch:
        recovered = False

        def search(self, query, *, call_context=None):
            calls.append(query)
            if query == "baseline":
                return []
            if not self.recovered:
                raise ProviderError("search_upstream_unavailable")
            return [
                real_evidence(
                    query,
                    "Recovered",
                    f"https://{query}.example/report",
                )
            ]

    class TwoQueryModel(DemoModelProvider):
        def generate(self, stage, context, *, call_context=None):
            output = super().generate(stage, context, call_context=call_context)
            if stage == "planning":
                output["queries"] = ["baseline", "risk"]
            return output

    search = RecoveringSearch()
    repository = DecisionRepository(tmp_path / "db")
    engine = WorkflowEngine(
        repository,
        model_provider=TwoQueryModel(),
        search_provider=search,
        mode="live",
    )
    decision_id = ready(repository, engine, mode="live")

    failed = engine.run(decision_id)
    assert failed.failure["code"] == "research_no_safe_evidence"
    assert calls.count("baseline") == 1

    search.recovered = True
    result = engine.retry(decision_id)
    assert result.status is DecisionStatus.awaiting_review
    assert calls.count("baseline") == 1


def test_research_deduplicates_canonical_urls_and_mirrored_content(tmp_path):
    class OverlappingRealSearch:
        def search(self, query, *, call_context=None):
            if query == "baseline":
                return [
                    real_evidence(
                        "Primary report",
                        "Measured baseline finding.",
                        "https://source.example/report?utm_source=mail&id=7#part",
                        "high",
                    ),
                    real_evidence(
                        "Shared report",
                        "The same published finding.",
                        "https://first.example/shared",
                    ),
                ]
            return [
                real_evidence(
                    "Primary report duplicate",
                    "Different snippet for the same canonical page.",
                    "https://SOURCE.EXAMPLE:443/report?id=7",
                    "high",
                ),
                real_evidence(
                    "  shared REPORT ",
                    "The   same published finding.",
                    "https://mirror.example/shared",
                ),
                real_evidence(
                    "Risk report",
                    "A distinct counterexample.",
                    "https://risk.example/report",
                ),
            ]

    repository = DecisionRepository(tmp_path / "db")
    output, snapshot = run_research_stage(repository, OverlappingRealSearch())

    assert [card.source_url for card in snapshot.evidence] == [
        "https://source.example/report?id=7",
        "https://first.example/shared",
        "https://risk.example/report",
    ]
    assert snapshot.evidence[0].title == "Primary report"
    assert snapshot.evidence[0].reliability == "high"
    assert output["evidence_ids"] == [card.id for card in snapshot.evidence]
    assert output["summary"] == (
        "联网搜索返回的来源摘要已保存，内容仍需人工核验。"
    )
    assert output["research_gaps"] == []


def test_research_with_real_and_demo_evidence_does_not_claim_all_sources_are_demo(
    tmp_path,
):
    class MixedSearch:
        def search(self, query, *, call_context=None):
            if query == "baseline":
                return DemoSearchProvider().search("baseline")[:1]
            return [
                real_evidence(
                    "Real risk source",
                    "A third-party source snippet.",
                    "https://source.example/risk",
                )
            ]

    output, snapshot = run_research_stage(
        DecisionRepository(tmp_path / "db"),
        MixedSearch(),
    )

    assert {card.is_demo for card in snapshot.evidence} == {True, False}
    assert output["summary"] == (
        "联网搜索返回的来源摘要已保存，内容仍需人工核验。"
    )
    assert "只有合成演示材料，没有经过核实的现实证据。" not in output[
        "research_gaps"
    ]


def test_research_without_results_records_an_explicit_gap_and_non_demo_summary(
    tmp_path,
):
    class EmptySearch:
        def search(self, query, *, call_context=None):
            return []

    output, snapshot = run_research_stage(
        DecisionRepository(tmp_path / "db"),
        EmptySearch(),
    )

    assert snapshot.evidence == []
    assert output["evidence_ids"] == []
    assert output["summary"] == "研究未检索到可用来源；没有生成证据。"
    assert "未检索到可用来源。" in output["research_gaps"]
    assert "缺少足量可信来源。" in output["research_gaps"]


def test_demo_only_research_retains_explicit_synthetic_summary_and_gap(tmp_path):
    output, snapshot = run_research_stage(
        DecisionRepository(tmp_path / "db"),
        DemoSearchProvider(),
    )

    assert snapshot.evidence and all(card.is_demo for card in snapshot.evidence)
    assert output["summary"] == "演示研究：合成材料已去重；没有执行真实搜索。"
    assert "只有合成演示材料，没有经过核实的现实证据。" in output[
        "research_gaps"
    ]


def test_delivering_cannot_delete_system_research_gaps(tmp_path):
    class DeletingGapModel(OverconfidentModel):
        def generate(self, stage, context, *, call_context=None):
            output = super().generate(stage, context, call_context=call_context)
            if stage == "delivering":
                output["research_gaps"] = []
                output["score_explanation"] = "The evidence is highly supportive."
            return output

    repository = DecisionRepository(tmp_path / "gaps.db")
    decision = repository.create(sample_decision(), mode="live")
    for index in range(2):
        repository.save_evidence(
            decision.id,
            real_evidence(
                f"Source {index}",
                f"Independent finding {index}",
                f"https://source{index}.example/report",
                "high",
            ),
        )
    repository.save_stage_output(
        decision.id,
        "researching",
        {
            "summary": "One query failed.",
            "queries": ["baseline", "risk"],
            "evidence_ids": [card.id for card in repository.get(decision.id).evidence],
            "research_gaps": ["查询「risk」未完成（search_timeout）。"],
        },
    )
    repository.save_stage_output(
        decision.id,
        "challenging",
        {"summary": "Challenge", "objection": "Evidence remains incomplete."},
    )

    output = WorkflowEngine(
        repository,
        model_provider=DeletingGapModel(),
        mode="live",
    )._run_stage("delivering", repository.get(decision.id))

    assert output["research_gaps"] == ["查询「risk」未完成（search_timeout）。"]
    assert output["support_score"] == 59
    assert "按规则上限调整为 59" in output["score_explanation"]


def test_delivering_stably_merges_model_and_system_gaps(tmp_path):
    class AddingGapModel(OverconfidentModel):
        def generate(self, stage, context, *, call_context=None):
            output = super().generate(stage, context, call_context=call_context)
            if stage == "delivering":
                output["research_gaps"] = [
                    "  missing baseline  ",
                    "仍缺团队真实升级率。",
                ]
            return output

    repository = DecisionRepository(tmp_path / "merge.db")
    decision = repository.create(sample_decision(), mode="live")
    for index in range(2):
        repository.save_evidence(
            decision.id,
            real_evidence(
                f"Source {index}",
                f"Finding {index}",
                f"https://merge{index}.example/report",
                "high",
            ),
        )
    repository.save_stage_output(
        decision.id,
        "researching",
        {
            "summary": "Research complete with one known gap.",
            "research_gaps": ["Missing BASELINE"],
        },
    )
    repository.save_stage_output(
        decision.id,
        "challenging",
        {"summary": "Challenge", "objection": "Check assumptions."},
    )

    output = WorkflowEngine(
        repository,
        model_provider=AddingGapModel(),
        mode="live",
    )._run_stage("delivering", repository.get(decision.id))

    assert output["research_gaps"] == [
        "Missing BASELINE",
        "仍缺团队真实升级率。",
    ]


def test_complete_live_research_is_not_permanently_capped(tmp_path):
    class CompleteSearch:
        def search(self, query, *, call_context=None):
            return [
                real_evidence(
                    query,
                    f"Independent finding for {query}",
                    f"https://{query}.example/report",
                    "high",
                )
            ]

    repository = DecisionRepository(tmp_path / "complete.db")
    engine = WorkflowEngine(
        repository,
        model_provider=OverconfidentModel(),
        search_provider=CompleteSearch(),
        mode="live",
    )
    decision_id = ready(repository, engine, mode="live")

    result = engine.run(decision_id)

    assert result.outputs["researching"]["research_gaps"] == []
    assert result.memo["research_gaps"] == []
    assert result.memo["support_score"] == 99


def test_invalid_planning_query_fails_before_search_and_recovers_on_retry(tmp_path):
    class CorrectingModel(DemoModelProvider):
        planning_calls = 0

        def generate(self, stage, context, *, call_context=None):
            output = super().generate(stage, context, call_context=call_context)
            if stage == "planning":
                self.planning_calls += 1
                output["queries"] = (
                    ["q" * 401, "risk"]
                    if self.planning_calls == 1
                    else ["baseline", "risk"]
                )
            return output

    class CountingSearch(DemoSearchProvider):
        calls = 0

        def search(self, query, *, call_context=None):
            self.calls += 1
            return super().search(query, call_context=call_context)

    model = CorrectingModel()
    search = CountingSearch()
    repository = DecisionRepository(tmp_path / "retry-query.db")
    engine = WorkflowEngine(repository, model_provider=model, search_provider=search)
    decision_id = ready(repository, engine)

    failed = engine.run(decision_id)

    assert failed.failure == {
        "stage": "planning",
        "code": "model_contract_violation",
        "message": "阶段执行失败，请重试；已完成输出已保留。",
    }
    assert failed.research_queries == []
    assert search.calls == 0

    recovered = engine.retry(decision_id)

    assert recovered.status is DecisionStatus.awaiting_review
    assert [query.query for query in recovered.research_queries] == ["baseline", "risk"]
    assert search.calls == 2


@pytest.mark.parametrize(
    "queries",
    [
        ["   ", "risk"],
        ["baseline", " BASELINE "],
    ],
)
def test_invalid_or_duplicate_planning_queries_fail_before_search(tmp_path, queries):
    class InvalidQueryModel(DemoModelProvider):
        def generate(self, stage, context, *, call_context=None):
            output = super().generate(stage, context, call_context=call_context)
            if stage == "planning":
                output["queries"] = queries
            return output

    class NoSearch:
        def search(self, query, *, call_context=None):
            raise AssertionError("invalid planning query reached search")

    repository = DecisionRepository(tmp_path / "invalid-query.db")
    engine = WorkflowEngine(
        repository,
        model_provider=InvalidQueryModel(),
        search_provider=NoSearch(),
    )
    decision_id = ready(repository, engine)

    failed = engine.run(decision_id)

    assert failed.failure["stage"] == "planning"
    assert failed.failure["code"] == "model_contract_violation"
    assert failed.research_queries == []


def test_http_duplicate_run_is_rejected_while_background_provider_is_blocked(tmp_path):
    app = create_app(tmp_path / 'db')
    client = TestClient(app)
    login(client)
    decision_id = client.post('/api/decisions', json=payload()).json()['id']
    url = '/api/decisions/' + decision_id
    entered, release = Event(), Event()
    original = app.state.workflow._run_stage
    def blocked(stage, snapshot):
        entered.set()
        assert release.wait(5), 'test failed to release provider'
        return original(stage, snapshot)
    app.state.workflow._run_stage = blocked
    response = []
    thread = Thread(target=lambda: response.append(client.post(url + '/run')))
    thread.start()
    try:
        assert entered.wait(5)
        assert client.get(url).json()['status'] == 'clarifying'
        assert client.post(url + '/run').status_code == 409
    finally:
        release.set()
        thread.join(5)
    assert response[0].status_code == 202
    assert client.get(url).json()['status'] == 'awaiting_confirmation'


def test_http_retry_returns_202_then_polling_reads_completion(tmp_path):
    app = create_app(tmp_path / 'db')
    client = TestClient(app)
    login(client)
    decision_id = client.post('/api/decisions', json=payload()).json()['id']
    url = '/api/decisions/' + decision_id
    original = app.state.workflow._run_stage
    def failing(stage, snapshot):
        raise RuntimeError('private API key')
    app.state.workflow._run_stage = failing
    assert client.post(url + '/run').status_code == 202
    failed = client.get(url)
    assert failed.json()['failure']['stage'] == 'clarifying'
    assert 'private API key' not in failed.text
    app.state.workflow._run_stage = original
    retried = client.post(url + '/retry')
    assert retried.status_code == 202
    assert retried.json()['status'] == 'retrying'
    assert client.get(url).json()['status'] == 'awaiting_confirmation'
    assert client.post(url + '/retry').status_code == 409


def test_startup_recovers_queued_runs_but_preserves_human_gates(tmp_path):
    path = tmp_path / 'db'
    app = create_app(path)
    repository, engine = app.state.repository, app.state.workflow
    queued = repository.create(sample_decision())
    engine.prepare_run(queued.id)
    waiting = repository.create(sample_decision())
    engine.run(waiting.id)
    confirmed_id = ready(repository, engine)
    with TestClient(create_app(path)) as client:
        login(client)
        repository.claim_legacy('test_user')
        assert client.get('/api/decisions/' + queued.id).json()['failure']['code'] == 'interrupted'
        assert client.get('/api/decisions/' + waiting.id).json()['status'] == 'awaiting_confirmation'
        assert client.get('/api/decisions/' + confirmed_id).json()['status'] == 'planning'
        assert client.post('/api/decisions/' + queued.id + '/retry').status_code == 202
        assert client.get('/api/decisions/' + queued.id).json()['status'] == 'awaiting_confirmation'
