"""The narration layer — the ONLY place the LLM appears (DECISIONS.md #3, #10).

A Narrator receives the computed Report (aggregates + reason mix), never raw
leads, and returns a short plain-English "why" string. AnthropicNarrator uses
Haiku 4.5; FakeNarrator is deterministic and offline for tests and the
default CLI path.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path

from karat.report import Report, ReportEntry, fmt_money, fmt_pct

_SYSTEM_PROMPT = (
    "You summarize paid-search campaign performance for a marketing team. "
    "Use ONLY the numbers provided in the JSON summary. Do not invent numbers, "
    "campaigns, or reasons. For each campaign listed, write one to two "
    "sentences stating the problem — money lost (tier1) or low match rate "
    "(tier2) — and the top reason its leads didn't match. "
    "Plain English, no preamble, no headers."
)


class Narrator(ABC):
    @abstractmethod
    def narrate(self, report: Report) -> str:
        """Return a short plain-English why-summary for the report."""


class FakeNarrator(Narrator):
    """Deterministic, offline. Same inputs as the real narrator."""

    def narrate(self, report: Report) -> str:
        lines = []
        for e in report.tier1:
            lines.append(
                f"{e.campaign_name} is losing money: profit {fmt_money(e.profit)} "
                f"on {e.mature_leads} mature leads at a {fmt_pct(e.match_rate)} "
                f"match rate. Top reason leads didn't match: {e.top_reason() or 'n/a'}."
            )
        for e in report.tier2:
            lines.append(
                f"{e.campaign_name} is profitable ({fmt_money(e.profit)}) but its "
                f"{fmt_pct(e.match_rate)} match rate is bottom-quartile. "
                f"Top reason leads didn't match: {e.top_reason() or 'n/a'}."
            )
        if not lines:
            return "No campaigns are losing money or underperforming this window."
        return "\n".join(lines)


class AnthropicNarrator(Narrator):
    """Real narrator on Haiku 4.5. Reads ANTHROPIC_API_KEY from .env or the
    environment. Sends only the computed tier summaries — cents per run."""

    MODEL = "claude-haiku-4-5"

    def __init__(self, api_key: str | None = None, model: str = MODEL):
        _load_dotenv()
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Put it in .env (gitignored) or the environment."
            )
        self.model = model

    def narrate(self, report: Report) -> str:
        import anthropic  # lazy: the offline path must not require the SDK

        client = anthropic.Anthropic(api_key=self._api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=500,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _summary_json(report)}],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()


def _summary_json(report: Report) -> str:
    """The computed summary table the LLM reads — aggregates only, no leads."""

    def slim(e: ReportEntry) -> dict:
        return {
            "campaign": e.campaign_name,
            "mature_leads": e.mature_leads,
            "pending_leads": e.pending_leads,
            "match_rate": None if e.match_rate is None else round(e.match_rate, 3),
            "cpl": None if e.cpl is None else round(e.cpl, 2),
            "rpr": None if e.rpr is None else round(e.rpr, 2),
            "profit": round(e.profit, 2),
            "reason_mix": {k: round(v, 2) for k, v in sorted(e.reason_mix.items())},
        }

    return json.dumps(
        {
            "window": f"{report.window_start} to {report.window_end}",
            "tier1_losing_money": [slim(e) for e in report.tier1],
            "tier2_underperforming_but_profitable": [slim(e) for e in report.tier2],
        },
        sort_keys=True,
    )


def _load_dotenv(path: str | Path = ".env") -> None:
    """Minimal .env loader (KEY=VALUE lines); never overrides real env vars."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))
