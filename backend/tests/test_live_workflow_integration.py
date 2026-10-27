from fastapi.testclient import TestClient
from tests.helpers import login

from app.config import Settings
from app.main import create_app
from app.providers.demo import DemoModelProvider
from app.schemas import EvidenceCard
from tests.test_api import payload


class CountingModel(DemoModelProvider):
    def __init__(self):
        self.stages: list[str] = []

    def generate(self, stage, context, *, call_context=None):
        self.stages.append(stage)
        output = super().generate(stage, context, call_context=call_context)
        if stage == "planning":
            output["queries"] = ["baseline", "risk", "cost", "market"]
        return output


class CountingSearch:
    def __init__(self):
        self.queries: list[str] = []

    def search(self, query, *, call_context=None):
        self.queries.append(query)
        return [
            EvidenceCard(
                is_demo=False,
                title=f"{query} source",
                summary=f"Third-party summary for {query}.",
                source_url=f"https://{query}.example/report",
                stance="context",
                reliability="medium",
            )
        ]


def test_live_workflow_joins_bounded_search_and_all_model_stages(tmp_path):
    model = CountingModel()
    search = CountingSearch()
    settings = Settings(
        app_mode="live",
        enable_live_workflow=True,
        deepseek_api_key="test-model-key",
        tavily_api_key="test-search-key",
    )
    app = create_app(
        tmp_path / "veriplan.db",
        settings=settings,
        model_provider=model,
        search_provider=search,
    )

    with TestClient(app) as client:
        login(client)
        created = client.post("/api/decisions", json=payload())
        assert created.status_code == 201
        decision_id = created.json()["id"]
        url = f"/api/decisions/{decision_id}"

        first = client.post(url + "/run")
        assert first.status_code == 202
        assert client.get(url).json()["status"] == "awaiting_confirmation"

        assert client.post(url + "/confirm").status_code == 200
        second = client.post(url + "/run")
        assert second.status_code == 202
        snapshot = client.get(url).json()

        assert snapshot["status"] == "awaiting_review"
        assert snapshot["mode"] == "live"
        assert [item["query"] for item in snapshot["research_queries"]] == [
            "baseline",
            "risk",
            "cost",
        ]
        assert model.stages == [
            "clarifying",
            "planning",
            "analyzing",
            "analyzing",
            "analyzing",
            "analyzing",
            "challenging",
            "delivering",
        ]
        assert search.queries == ["baseline", "risk", "cost"]
        assert all(not item["is_demo"] for item in snapshot["evidence"])

        reviewed = client.post(
            url + "/review",
            json={
                "action": "accepted",
                "note": "Offline joined-flow acceptance",
            },
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["status"] == "accepted"
