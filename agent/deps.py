"""Per-run agent dependencies (Pydantic AI RunContext deps).

user_id is bound here server-side and injected into every tool by the
wrappers in agent/agent.py: the model never chooses whose data it queries.
The pseudonymizer is preloaded with the user's pii_mappings so fake values
stay consistent across tool calls within and across runs.
"""

from dataclasses import dataclass, field

from app.db import get_pool
from app.schemas import Citation
from pii.pseudonymizer import Pseudonymizer


@dataclass
class AgentDeps:
    user_id: int
    pseudonymizer: Pseudonymizer
    # filled by the tool wrappers as the ReAct loop runs
    tool_calls: list[dict] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)


async def build_deps(user_id: int) -> AgentDeps:
    pool = await get_pool()
    async with pool.acquire() as conn:
        known = {
            m["real_value"]: (m["pii_type"], m["fake_value"])
            for m in await conn.fetch(
                "SELECT pii_type, real_value, fake_value FROM pii_mappings "
                "WHERE user_id = $1",
                user_id,
            )
        }
    return AgentDeps(user_id=user_id, pseudonymizer=Pseudonymizer(user_id, known))
