import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic_ai.exceptions import UsageLimitExceeded

from agent.agent import run_agent
from app import db
from app.config import settings
from app.schemas import (
    AskRequest,
    AskResponse,
    FakeValue,
    PayloadEntry,
    PayloadsResponse,
    TransactionOut,
)
from baseline.plain_rag import run_rag

UI_DIR = Path(__file__).resolve().parent.parent / "ui"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await db.close_pool()


app = FastAPI(
    title="FinQuery",
    description="Grounded personal-finance Q&A agent (AIEngg.dev capstone, IP6)",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok", "db": await db.ping()}


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest) -> AskResponse:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        known_user = await conn.fetchval("SELECT 1 FROM users WHERE id = $1", req.user_id)
    if not known_user:
        raise HTTPException(status_code=404, detail=f"unknown user_id {req.user_id}")

    runner = run_rag if req.approach == "rag" else run_agent
    try:
        result = await runner(req.question, req.user_id)
    except ValueError as exc:      # whitespace-only question slips the schema min_length
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:    # key not configured / embeddings not backfilled
        raise HTTPException(status_code=503, detail=str(exc))
    except UsageLimitExceeded as exc:
        raise HTTPException(status_code=500, detail=f"agent stopped: {exc}")

    # ask_runs stores the raw question: app observability, not an LLM boundary
    # (the masked LLM-bound payloads live in llm_payload_log).
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO ask_runs (user_id, approach, question, answer, refused,
                                     tool_calls, citations, latency_ms)
               VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8)""",
            req.user_id, req.approach, req.question, result.answer, result.refused,
            json.dumps(result.tool_calls),
            json.dumps([c.model_dump() for c in result.citations]),
            result.latency_ms,
        )

    return AskResponse(
        answer=result.answer, approach=req.approach,
        refused=result.refused, citations=result.citations,
        tool_calls=result.tool_calls, latency_ms=result.latency_ms,
    )


@app.get("/transactions", response_model=list[TransactionOut])
async def transactions(user_id: int = 1) -> list[TransactionOut]:
    """Full ledger for one user; the UI filters client-side (~350 rows/user).

    Serves the verification page (raw synthetic data, pre-LLM-boundary, so no
    pseudonymization: the user is looking at their own transactions).
    """
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT t.id, t.txn_date, t.bank_description, t.amount, t.txn_type,
                   c.name AS category, s.name AS subcategory
            FROM transactions t
            LEFT JOIN categories c ON c.id = t.category_id
            LEFT JOIN subcategories s ON s.id = t.subcategory_id
            WHERE t.user_id = $1
            ORDER BY t.txn_date DESC, t.id DESC
            """,
            user_id,
        )
    return [TransactionOut(**dict(r)) for r in rows]


@app.get("/payloads", response_model=PayloadsResponse)
async def payloads(user_id: int = 1, limit: int = 50) -> PayloadsResponse:
    """Recent LLM-boundary payloads for the PII transparency page: exactly
    what left for (or came back from) the LLM, newest first.

    Each row carries the substitutions the PII gate applied to it, so the page
    can state per payload how many values were masked and of what type. Fake
    values (pseudonyms) are returned for highlighting; real values never leave
    the database through this endpoint.
    """
    limit = max(1, min(limit, 200))
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, created_at, approach, direction, kind, content, run_id,
                      replacements
               FROM llm_payload_log WHERE user_id = $1
               ORDER BY id DESC LIMIT $2""",
            user_id, limit,
        )
        fakes = await conn.fetch(
            "SELECT fake_value, pii_type FROM pii_mappings WHERE user_id = $1",
            user_id,
        )
    return PayloadsResponse(
        pii_masking=settings.pii_masking,
        payloads=[PayloadEntry(
            id=r["id"], created_at=r["created_at"].isoformat(),
            approach=r["approach"], direction=r["direction"],
            kind=r["kind"], content=r["content"], run_id=r["run_id"],
            replacements=json.loads(r["replacements"] or "[]"),
        ) for r in rows],
        fake_values=[FakeValue(**dict(f)) for f in fakes],
    )


class NoCacheStaticFiles(StaticFiles):
    """Static assets are actively edited during development; a browser that
    caches an old ui/*.html or *.css/js is a recurring source of "the nav
    looks wrong" confusion that has nothing to do with the served code."""

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response


app.mount("/", NoCacheStaticFiles(directory=UI_DIR, html=True), name="ui")
