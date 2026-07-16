"""Agent-loop tests with a scripted FunctionModel: the REAL ReAct machinery
(tool schemas, ModelRetry feedback, usage limits, the PII gate, payload
logging) runs against the live seeded DB; only the LLM is fake. Key-free.

Requires the dockerized Postgres; skips cleanly if it is not reachable.
Payload-log rows written by these tests are deleted on teardown so the
eval leakage scan never trips over deliberate flag-off test rows.
"""

import pytest
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import (
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.config import settings
from app.db import close_pool, get_pool, ping
from agent.agent import REQUEST_LIMIT, run_agent
from agent.tools import search_finance_kb
from guardrails.refusal import REFUSAL_MARKER


@pytest.fixture(autouse=True)
async def log_baseline():
    """DB guard + llm_payload_log high-water mark; test rows removed after."""
    await close_pool()
    if not await ping():
        await close_pool()
        pytest.skip("seeded DB not reachable on DATABASE_URL")
    pool = await get_pool()
    before = await pool.fetchval("SELECT coalesce(max(id), 0) FROM llm_payload_log")
    yield before
    pool = await get_pool()
    await pool.execute("DELETE FROM llm_payload_log WHERE id > $1", before)
    await close_pool()


def _parts(rounds, part_type):
    """Parts of the given type from the FINAL round's message history.
    Each round receives the full history so far; earlier rounds are prefixes
    of the last one, and iterating all rounds would double-count."""
    return [p for m in rounds[-1] for p in m.parts if isinstance(p, part_type)]


def _dmart_search_script(rounds):
    """Round 1: search DMART transactions (narrations carry a masked-card
    number that is in pii_mappings). Round 2: final text answer."""
    def script(messages, info: AgentInfo) -> ModelResponse:
        rounds.append(messages)
        if len(rounds) == 1:
            return ModelResponse(parts=[ToolCallPart(
                tool_name="search_transactions",
                args={"text": "DMART", "start_date": "2026-06-01",
                      "end_date": "2026-06-30"},
            )])
        return ModelResponse(parts=[TextPart(
            "Here are your DMART purchases for June 2026.")])
    return script


async def _real_values(user_id: int) -> list[str]:
    pool = await get_pool()
    return [r["real_value"] for r in await pool.fetch(
        "SELECT real_value FROM pii_mappings WHERE user_id = $1", user_id)]


# ------------------------------------------------------------- happy path

async def test_tool_output_is_masked_and_payloads_logged(log_baseline):
    rounds: list = []
    answer = await run_agent("Show my DMART purchases in June", 1,
                             model=FunctionModel(_dmart_search_script(rounds)))

    assert answer.answer.startswith("Here are your DMART purchases")
    assert answer.refused is False
    assert answer.tool_calls == [{"tool": "search_transactions", "args": {
        "text": "DMART", "start_date": "2026-06-01", "end_date": "2026-06-30",
        "order_by": "date", "limit": 20}}]
    assert [c.kind for c in answer.citations] == ["sql_tool"]

    # what actually entered LLM context contains no real mapped PII value
    returns = _parts(rounds, ToolReturnPart)
    assert len(returns) == 1 and "DMART" in returns[0].content
    reals = await _real_values(1)
    assert reals and not any(real in returns[0].content for real in reals)

    # every LLM-bound payload was logged, and the log matches the mask
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT kind, direction, content FROM llm_payload_log WHERE id > $1 ORDER BY id",
        log_baseline)
    assert [(r["kind"], r["direction"]) for r in rows] == [
        ("system", "to_llm"), ("user", "to_llm"),
        ("tool_result", "to_llm"), ("answer", "from_llm")]
    for r in rows:
        assert not any(real in r["content"] for real in reals)


async def test_pii_flag_off_sends_raw_narrations(monkeypatch, log_baseline):
    """Ablation mode: the gate is skipped, so the DMART card number reaches
    the model raw. Proves the flag toggles the boundary, and gives the
    leakage scan a known expected-positive shape."""
    monkeypatch.setattr(settings, "pii_masking", False)
    rounds: list = []
    await run_agent("Show my DMART purchases in June", 1,
                    model=FunctionModel(_dmart_search_script(rounds)))
    returns = _parts(rounds, ToolReturnPart)
    reals = await _real_values(1)
    assert any(real in returns[0].content for real in reals)


async def test_question_pii_is_masked_before_the_model_sees_it(log_baseline):
    pool = await get_pool()
    vpa = await pool.fetchrow(
        "SELECT real_value, fake_value FROM pii_mappings "
        "WHERE user_id = 1 AND pii_type = 'vpa' LIMIT 1")
    rounds: list = []

    def script(messages, info: AgentInfo) -> ModelResponse:
        rounds.append(messages)
        return ModelResponse(parts=[TextPart("Answered.")])

    await run_agent(f"Did I pay {vpa['real_value']} last month?", 1,
                    model=FunctionModel(script))
    prompts = _parts(rounds, UserPromptPart)
    assert len(prompts) == 1
    assert vpa["real_value"] not in prompts[0].content
    assert vpa["fake_value"] in prompts[0].content


# ------------------------------------------------------------- loop control

async def test_model_retry_feeds_valid_names_back_and_self_corrects(log_baseline):
    rounds: list = []

    def script(messages, info: AgentInfo) -> ModelResponse:
        rounds.append(messages)
        if len(rounds) == 1:  # invalid subcategory -> ModelRetry
            return ModelResponse(parts=[ToolCallPart(
                tool_name="spending_by_category", args={"subcategory": "Grocery"})])
        if len(rounds) == 2:  # corrected call
            return ModelResponse(parts=[ToolCallPart(
                tool_name="spending_by_category", args={"subcategory": "Groceries"})])
        return ModelResponse(parts=[TextPart("Grocery total reported.")])

    answer = await run_agent("Grocery spend?", 1, model=FunctionModel(script))

    retries = _parts(rounds, RetryPromptPart)
    assert len(retries) == 1
    assert "Groceries" in retries[0].model_response()  # lists valid options
    assert answer.answer == "Grocery total reported."
    # only the successful call is recorded
    assert answer.tool_calls == [
        {"tool": "spending_by_category", "args": {"subcategory": "Groceries"}}]


async def test_runaway_tool_loop_stops_at_request_limit(log_baseline):
    calls = 0

    def script(messages, info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        return ModelResponse(parts=[ToolCallPart(
            tool_name="search_finance_kb", args={"query": "emergency fund"})])

    with pytest.raises(UsageLimitExceeded):
        await run_agent("loop forever", 1, model=FunctionModel(script))
    assert calls == REQUEST_LIMIT


# ------------------------------------------------------------- guardrails

async def test_refusal_marker_sets_refused_flag(log_baseline):
    def script(messages, info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(
            f"{REFUSAL_MARKER}. Picking funds requires a SEBI-registered "
            "adviser. I can explain what a small-cap fund is instead.")])

    answer = await run_agent("Should I buy SBI Small Cap Fund?", 1,
                             model=FunctionModel(script))
    assert answer.refused is True
    assert answer.tool_calls == []


async def test_question_length_cap(log_baseline):
    with pytest.raises(ValueError, match="exceeds"):
        await run_agent("x" * 1001, 1, model=None)


# ------------------------------------------------------------- KB tool

async def test_search_finance_kb_sparse_retrieves_relevant_chunk(log_baseline):
    result = await search_finance_kb("how many months of expenses in an emergency fund")
    assert result.retrieval_mode == "sparse"
    assert result.hits
    assert any("emergency" in h.content.lower() for h in result.hits)
    assert all(h.document_title for h in result.hits)
