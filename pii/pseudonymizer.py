"""Forward pseudonymization: real PII -> consistent fake values.

Applied at every LLM boundary in BOTH approaches:
  - tool outputs before they enter agent context (approach B)
  - serialized transactions before embedding (approach A)
  - user questions before they reach the LLM

Detection = regex for UPI VPAs, phone numbers, masked card numbers, and masked
account fragments, plus a known-values list (the per-user pii_mappings table).
Free-text name NER is documented out of scope; counterparty names are handled
only when they appear in the known-values list. Reverse mapping is an optional
extension. Prior art acknowledged: Microsoft Presidio (not imported).
"""

import re

# Order matters: earlier patterns claim their span first (a VPA contains a
# phone-shaped prefix; a masked card contains an account-shaped tail).
PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    # note: '-' excluded from the local part; bank narrations are dash-delimited
    ("vpa", re.compile(r"\b[A-Za-z0-9][\w.]*@[a-z][a-z0-9]{1,15}\b")),
    ("card", re.compile(r"\b\d{4,6}X{4,8}\d{4}\b")),
    ("account", re.compile(r"\bX{2,}\d{4}\b")),
    ("loan_ref", re.compile(r"\bL[A-Z0-9]{1,6}\d{6,}\b")),
    ("policy", re.compile(r"(?<=POL )[A-Z]{0,5}\d{6,}\b")),
    ("phone", re.compile(r"\b[6-9]\d{9}\b")),
]
# Scope boundary: one-off transaction references (NEFT/UPI/ACH ids, tax CINs)
# are not masked; they identify a single transaction, not a person or account.
# Loan references and insurance policy numbers are masked because they are
# persistent account identifiers.


def detect_pii(text: str) -> list[tuple[str, str]]:
    """Return non-overlapping (pii_type, value) hits, left to right."""
    claimed: list[tuple[int, int]] = []
    hits: list[tuple[int, str, str]] = []
    for pii_type, pattern in PII_PATTERNS:
        for m in pattern.finditer(text):
            span = (m.start(), m.end())
            if any(s < span[1] and span[0] < e for s, e in claimed):
                continue
            claimed.append(span)
            hits.append((m.start(), pii_type, m.group()))
    hits.sort()
    return [(t, v) for _, t, v in hits]


class Pseudonymizer:
    """Per-user forward mapper. Fake values are stable for the lifetime of the
    mapping (persisted in pii_mappings), so the LLM sees consistent identities
    across calls without ever seeing a real value."""

    def __init__(self, user_id: int, known: dict[str, tuple[str, str]] | None = None):
        # known: real_value -> (pii_type, fake_value), preloaded from the DB
        self.user_id = user_id
        self.mapping: dict[str, tuple[str, str]] = dict(known or {})
        self._counters: dict[str, int] = {}
        for pii_type, _fake in self.mapping.values():
            self._counters[pii_type] = self._counters.get(pii_type, 0) + 1

    def _make_fake(self, pii_type: str) -> str:
        n = self._counters.get(pii_type, 0) + 1
        self._counters[pii_type] = n
        u = self.user_id
        if pii_type == "vpa":
            return f"person{u}.contact{n:03d}@fakeupi"
        if pii_type == "phone":
            return f"9{u % 10}00{n:07d}"
        if pii_type == "card":
            return f"4999{u % 100:02d}XXXXXX{n:04d}"
        if pii_type == "account":
            return f"XX{9000 + n}"
        if pii_type == "loan_ref":
            return f"LN{u % 10}00{n:08d}"
        if pii_type == "policy":
            return f"FP{u % 10}00{n:06d}"
        return f"FAKE_{pii_type.upper()}_{n:03d}"

    def register(self, text: str) -> list[tuple[str, str, str]]:
        """Detect PII in text, extend the mapping, return newly added
        (pii_type, real_value, fake_value) triples."""
        added = []
        for pii_type, real in detect_pii(text):
            if real not in self.mapping:
                fake = self._make_fake(pii_type)
                self.mapping[real] = (pii_type, fake)
                added.append((pii_type, real, fake))
        return added

    def pseudonymize(self, text: str) -> str:
        """Replace every known real value with its fake value. Call register()
        first (or rely on a fully built mapping) so nothing is missed."""
        return self.pseudonymize_with_report(text)[0]

    def pseudonymize_with_report(self, text: str) -> tuple[str, list[tuple[str, str]]]:
        """pseudonymize(), plus the (pii_type, fake_value) pairs actually
        substituted in this text. The report is the evidence the PII log page
        shows per payload: it covers values already in the mapping, not just
        newly registered ones, so a repeated VPA still counts as masked.

        Real values are deliberately absent; they stay in pii_mappings."""
        self.register(text)
        applied: list[tuple[str, str]] = []
        # longest first so a substring never clobbers a longer value
        for real in sorted(self.mapping, key=len, reverse=True):
            pii_type, fake = self.mapping[real]
            if real in text:
                applied.append((pii_type, fake))
                text = text.replace(real, fake)
        return text, applied
