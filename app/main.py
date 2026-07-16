from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

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
    # Stub until the agent (approach B) and vanilla RAG baseline (approach A)
    # are implemented; keeps the API contract and UI wired end to end.
    return AskResponse(
        answer=(
            "FinQuery is scaffolded but the answering pipeline is not implemented yet. "
            f"Received question for approach '{req.approach}' as user {req.user_id}."
        ),
        approach=req.approach,
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
