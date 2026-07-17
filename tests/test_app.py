import asyncio
from functools import partial

import asyncpg
import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agent.agent import run_agent
from app import db
from app.config import settings
from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    # db may be down in CI; the key contract is the endpoint answers
    assert isinstance(body["db"], bool)


def test_ask_rag_without_embeddings_returns_503():
    """In the pre-backfill state the baseline refuses fast, before spending an
    embed call. Once embeddings exist this state cannot be exercised (and the
    request would go live), so skip."""

    async def _embedded() -> int:
        conn = await asyncpg.connect(settings.database_url)
        try:
            return await conn.fetchval(
                "SELECT count(*) FROM kb_chunks WHERE embedding IS NOT NULL")
        finally:
            await conn.close()

    asyncio.run(db.close_pool())
    with TestClient(app) as c:
        if not c.get("/health").json()["db"]:
            pytest.skip("db not running")
        if asyncio.run(_embedded()):
            pytest.skip("embeddings are backfilled; the empty-state 503 cannot fire")
        res = c.post("/ask", json={"question": "What is the 50/30/20 rule?",
                                   "approach": "rag"})
    assert res.status_code == 503
    assert "embed_chunks" in res.json()["detail"]


def test_ask_rag_end_to_end_records_run(monkeypatch):
    """Endpoint plumbing for approach='rag': routing, response shape, and the
    ask_runs row; baseline internals are covered in test_baseline.py."""
    from app.schemas import Citation, RunResult

    async def fake_run_rag(question, user_id):
        return RunResult(answer="From the retrieved context.", refused=False,
                         citations=[Citation(kind="txn_chunk", ref="transaction chunk 1")],
                         tool_calls=[], latency_ms=7)

    monkeypatch.setattr("app.main.run_rag", fake_run_rag)

    asyncio.run(db.close_pool())
    with TestClient(app) as c:
        if not c.get("/health").json()["db"]:
            pytest.skip("db not running")
        res = c.post("/ask", json={"question": "What is the 50/30/20 rule?",
                                   "approach": "rag"})
    assert res.status_code == 200
    body = res.json()
    assert body["approach"] == "rag"
    assert body["citations"][0]["kind"] == "txn_chunk"

    async def _check_and_cleanup():
        conn = await asyncpg.connect(settings.database_url)
        try:
            row = await conn.fetchrow("SELECT * FROM ask_runs ORDER BY id DESC LIMIT 1")
            assert row["approach"] == "rag" and row["tool_calls"] == "[]"
            await conn.execute("DELETE FROM ask_runs WHERE id = $1", row["id"])
        finally:
            await conn.close()

    asyncio.run(_check_and_cleanup())


def test_ask_rejects_bad_approach():
    res = client.post("/ask", json={"question": "hi", "approach": "graphrag"})
    assert res.status_code == 422


def test_ask_returns_503_when_key_missing(monkeypatch):
    """A missing key fails clean BEFORE any DB write (model resolved first),
    so this needs neither the key nor a reachable DB... except the users
    lookup; skip if the DB is down."""
    monkeypatch.setattr(settings, "openai_api_key", "")
    asyncio.run(db.close_pool())
    with TestClient(app) as c:
        if not c.get("/health").json()["db"]:
            pytest.skip("db not running")
        res = c.post("/ask", json={"question": "hello", "approach": "agent"})
    assert res.status_code == 503
    assert "OPENAI_API_KEY" in res.json()["detail"]


def test_ask_unknown_user_is_404():
    asyncio.run(db.close_pool())
    with TestClient(app) as c:
        if not c.get("/health").json()["db"]:
            pytest.skip("db not running")
        res = c.post("/ask", json={"question": "hi", "user_id": 99, "approach": "agent"})
    assert res.status_code == 404


def test_ask_agent_end_to_end_records_run(monkeypatch):
    """Full plumbing with the real agent loop and a scripted model: response
    contract, citations, and the ask_runs row. Cleans up its own rows."""

    def script(messages, info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart(
                tool_name="spending_by_category",
                args={"subcategory": "Groceries",
                      "start_date": "2026-06-01", "end_date": "2026-06-30"},
            )])
        return ModelResponse(parts=[TextPart("Your June 2026 grocery total, from SQL.")])

    monkeypatch.setattr("app.main.run_agent",
                        partial(run_agent, model=FunctionModel(script)))

    async def _watermarks():
        conn = await asyncpg.connect(settings.database_url)
        try:
            return (await conn.fetchval("SELECT coalesce(max(id),0) FROM ask_runs"),
                    await conn.fetchval("SELECT coalesce(max(id),0) FROM llm_payload_log"))
        finally:
            await conn.close()

    asyncio.run(db.close_pool())
    with TestClient(app) as c:
        if not c.get("/health").json()["db"]:
            pytest.skip("db not running")
        runs_before, log_before = asyncio.run(_watermarks())
        res = c.post("/ask", json={
            "question": "How much did I spend on groceries in June?",
            "user_id": 1, "approach": "agent"})

    assert res.status_code == 200
    body = res.json()
    assert body["approach"] == "agent" and body["refused"] is False
    assert body["answer"].startswith("Your June 2026 grocery total")
    assert body["citations"] and body["citations"][0]["kind"] == "sql_tool"

    async def _check_and_cleanup():
        conn = await asyncpg.connect(settings.database_url)
        try:
            row = await conn.fetchrow(
                "SELECT * FROM ask_runs WHERE id > $1 ORDER BY id DESC LIMIT 1",
                runs_before)
            assert row["approach"] == "agent" and row["refused"] is False
            assert "spending_by_category" in row["tool_calls"]
            assert row["latency_ms"] is not None and row["latency_ms"] >= 0
            await conn.execute("DELETE FROM ask_runs WHERE id > $1", runs_before)
            await conn.execute("DELETE FROM llm_payload_log WHERE id > $1", log_before)
        finally:
            await conn.close()

    asyncio.run(_check_and_cleanup())


def test_ui_served_at_root():
    res = client.get("/")
    assert res.status_code == 200
    assert "FinQuery" in res.text


def test_transactions_endpoint():
    # drop any pool bound to a previous test's event loop, then keep every
    # request of this test on one loop via the context-managed client
    asyncio.run(db.close_pool())
    with TestClient(app) as c:
        if not c.get("/health").json()["db"]:
            pytest.skip("db not running")
        res = c.get("/transactions", params={"user_id": 1})
    assert res.status_code == 200
    body = res.json()
    assert len(body) > 0
    row = body[0]
    assert set(row) >= {"id", "txn_date", "bank_description", "amount", "txn_type", "category"}
    assert row["txn_type"] in ("credit", "debit")
