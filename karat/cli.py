"""Entrypoint: mock source -> metrics -> report -> narrate -> print markdown.

Offline by default (FakeNarrator). Nothing hits the network unless --live is
passed, which switches to AnthropicNarrator (Haiku 4.5, key from .env).

Run: python -m karat.cli [--live] [--seed N] [--days N]
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from karat.metrics import compute_campaign_stats
from karat.mock_source import MockDataSource
from karat.models import Window
from karat.narrate import AnthropicNarrator, FakeNarrator
from karat.reasons import compute_reason_mix
from karat.report import build_report, render_markdown


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="karat",
        description="Rank campaigns by real downstream profit and explain why leads fail to match.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="write the why-summary with the Anthropic API (default: offline FakeNarrator)",
    )
    parser.add_argument("--seed", type=int, default=42, help="mock data seed")
    parser.add_argument("--days", type=int, default=30, help="window length ending today")
    args = parser.parse_args(argv)

    window = Window(start=date.today() - timedelta(days=args.days), end=date.today())
    source = MockDataSource(seed=args.seed)
    leads = source.get_leads(window)
    costs = {m.campaign_id: m.cost for m in source.get_campaign_metrics(window)}

    stats = compute_campaign_stats(leads, costs, window)
    report = build_report(stats, compute_reason_mix(leads), window)

    narrator = AnthropicNarrator() if args.live else FakeNarrator()
    print(render_markdown(report, narrator.narrate(report)))


if __name__ == "__main__":
    main()
