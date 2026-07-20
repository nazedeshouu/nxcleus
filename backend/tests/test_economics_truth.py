from app.api import economics as economics_api


async def test_economics_does_not_invent_missing_run_evidence(monkeypatch):
    async def list_processes():
        return [{"id": "process-1", "slug": "claims", "created_from_job": "job-1"}]

    async def list_runs(_process_id):
        return [{
            "id": "run-1",
            "started_at": None,
            "status": "done",
            "stats": {"units": 4},
            "cost": {"total_usd": 0.12},
        }]

    async def invoice(_scope):
        return {"total_usd": 0.4, "frontier_calls": 1}

    monkeypatch.setattr(economics_api.dao, "list_processes", list_processes)
    monkeypatch.setattr(economics_api.dao, "list_runs", list_runs)
    monkeypatch.setattr(economics_api, "build_invoice", invoice)

    payload = await economics_api.economics_summary()
    run = payload["processes"][0]["runs"][0]
    assert run["cost_usd"] == 0.12
    assert run["cost_per_unit"] is None
    assert run["frontier_calls"] is None
    assert run["cost_verification"] == "unverified"
    assert run["verification"] == "unverified"
    assert run["verification_reasons"] == []
