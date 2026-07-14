from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import db
from app.schemas import AskRequest, AskResponse

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


app.mount("/", StaticFiles(directory=UI_DIR, html=True), name="ui")
