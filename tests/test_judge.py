"""Judge bookkeeping tests with a fake OpenAI client: verdict parsing,
in-place file update, summary recomputation, and idempotency. The judging
quality itself is an LLM property; what must never break is the accounting."""

import json

import pytest

from eval.judge import judge_file


class _FakeCompletions:
    def __init__(self, verdicts: dict[str, dict]):
        self.verdicts = verdicts  # keyed by question substring
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        user_msg = kwargs["messages"][1]["content"]
        verdict = next(v for k, v in self.verdicts.items() if k in user_msg)

        class _Msg:
            content = json.dumps(verdict)

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()


class _FakeClient:
    def __init__(self, verdicts):
        self.chat = type("chat", (), {})()
        self.chat.completions = _FakeCompletions(verdicts)


@pytest.fixture
def results_file(tmp_path, monkeypatch):
    monkeypatch.setattr("eval.judge.RESULTS_DIR", tmp_path)
    report = {
        "system": "rag",
        "pii_masking": True,
        "summary": {},
        "results": [
            {"id": "edu-01", "bucket": "education", "answer": "The 50/30/20 rule...",
             "refused": False, "passed": None, "pending_judge": True, "error": None},
            {"id": "comp-01", "bucket": "composite", "answer": "Your EMIs are 28,650...",
             "refused": False, "passed": None, "pending_judge": True,
             "component_recall": 1.0, "error": None},
            {"id": "agg-01", "bucket": "aggregation", "answer": "Rs 10,900",
             "refused": False, "passed": True, "pending_judge": False, "error": None},
        ],
    }
    path = tmp_path / "rag.json"
    path.write_text(json.dumps(report))
    return path


async def test_judge_fills_verdicts_and_recomputes_summary(results_file):
    client = _FakeClient({
        "50/30/20": {"pass": True, "missing": [], "reason": "covers all points"},
        "EMIs": {"pass": False, "missing": ["relates ratio to the comfort range"],
                 "reason": "no guideline comparison"},
    })
    outcome = await judge_file("rag", client)
    assert outcome["judged"] == 2

    report = json.loads(results_file.read_text())
    by_id = {r["id"]: r for r in report["results"]}
    assert by_id["edu-01"]["passed"] is True
    assert by_id["comp-01"]["passed"] is False
    assert by_id["comp-01"]["judge"]["missing"]
    assert by_id["comp-01"]["component_recall"] == 1.0  # evidence preserved
    assert by_id["agg-01"]["passed"] is True             # untouched

    assert report["summary"]["education"]["passed"] == 1
    assert report["summary"]["composite"]["failed"] == 1
    assert report["summary"]["education"]["pending_judge"] == 0


async def test_judge_is_idempotent_unless_rejudge(results_file):
    client = _FakeClient({
        "50/30/20": {"pass": True, "missing": [], "reason": "ok"},
        "EMIs": {"pass": True, "missing": [], "reason": "ok"},
    })
    first = await judge_file("rag", client)
    second = await judge_file("rag", client)
    assert first["judged"] == 2 and second["judged"] == 0
    assert client.chat.completions.calls == 2

    third = await judge_file("rag", client, rejudge=True)
    assert third["judged"] == 2
