import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic_ai.exceptions import UsageLimitExceeded

from agent.agent import run_agent
from app import db
from app.schemas import AskRequest, AskResponse, TransactionOut

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
    if req.approach == "rag":
        raise HTTPException(
            status_code=501,
            detail="vanilla RAG baseline (approach A) is not implemented yet; "
                   "use approach='agent'",
        )

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        known_user = await conn.fetchval("SELECT 1 FROM users WHERE id = $1", req.user_id)
    if not known_user:
        raise HTTPException(status_code=404, detail=f"unknown user_id {req.user_id}")

    try:
        result = await run_agent(req.question, req.user_id)
    except ValueError as exc:      # whitespace-only question slips the schema min_length
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:    # OPENAI_API_KEY not configured
        raise HTTPException(status_code=503, detail=str(exc))
    except UsageLimitExceeded as exc:
        raise HTTPException(status_code=500, detail=f"agent stopped: {exc}")

    # ask_runs stores the raw question: app observability, not an LLM boundary
    # (the masked LLM-bound payloads live in llm_payload_log).
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO ask_runs (user_id, approach, question, answer, refused,
                                     tool_calls, citations, latency_ms)
               VALUES ($1, 'agent', $2, $3, $4, $5::jsonb, $6::jsonb, $7)""",
            req.user_id, req.question, result.answer, result.refused,
            json.dumps(result.tool_calls),
            json.dumps([c.model_dump() for c in result.citations]),
            result.latency_ms,
        )

    return AskResponse(
        answer=result.answer, approach="agent",
        refused=result.refused, citations=result.citations,
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


app.mount("/", StaticFiles(directory=UI_DIR, html=True), name="ui")
