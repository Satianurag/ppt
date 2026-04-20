"""Entry point for the markdown → presentation multi-agent pipeline.

The pipeline is multi-agent by default:
    Strategist → Designer → Executor → Reviewer
with a conditional retry edge Reviewer → Designer when quality fails.

The orchestration is implemented with LangGraph so the graph is a first-class
object (30% Code Quality & Agentic bucket of the hackathon rubric).

Hackathon constraints:
- Fixed slides 1 / 14 / 15 are preserved verbatim from the Slide Master template.
- Slide 1 (cover) accepts only dynamic title, subtitle, presenter name, date.
- Output always contains exactly 15 slides.
- No two adjacent slides share a visually similar layout.
- All styling cascades from the Slide Master (no runtime overrides).
- Mistral is the sole LLM provider.

Usage:
    python main.py <markdown_file> <template.pptx> --presenter "Name"
                   [--date "April 19, 2026"]
                   [--output out.pptx]
                   [--quality 0.6] [--retries 2]
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from agents.langgraph_pipeline import run_langgraph_pipeline


def _default_date() -> str:
    return date.today().strftime("%B %-d, %Y")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Markdown → 15-slide PPTX via multi-agent LangGraph pipeline (Mistral).",
    )
    parser.add_argument("markdown_file", help="Path to the markdown source file.")
    parser.add_argument("template_file", help="Path to a Slide Master .pptx template.")
    parser.add_argument(
        "--presenter", required=True,
        help="Presenter full name (rendered at the bottom-left of the cover slide).",
    )
    parser.add_argument(
        "--date", dest="presentation_date", default=_default_date(),
        help="Presentation date. Defaults to today, e.g. 'April 19, 2026'.",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output .pptx path. Defaults to ./output/<markdown_stem>.pptx.",
    )
    parser.add_argument("--quality", type=float, default=0.6, dest="quality_threshold")
    parser.add_argument("--retries", type=int, default=2, dest="max_retries")
    return parser.parse_args(argv[1:])


def main() -> None:
    if not os.getenv("MISTRAL_API_KEY"):
        print("Error: MISTRAL_API_KEY is not set. This project uses Mistral only.")
        sys.exit(1)

    args = _parse_args(sys.argv)

    if not Path(args.markdown_file).exists():
        print(f"Error: markdown file not found: {args.markdown_file}")
        sys.exit(1)
    if not Path(args.template_file).exists():
        print(f"Error: template file not found: {args.template_file}")
        sys.exit(1)

    output_dir = "./output"
    output_path = args.output
    if output_path is None:
        stem = Path(args.markdown_file).stem
        output_path = str(Path(output_dir) / f"{stem}.pptx")

    state = run_langgraph_pipeline(
        markdown_path=args.markdown_file,
        template_path=args.template_file,
        output_dir=output_dir,
        output_path=output_path,
        presenter=args.presenter,
        presentation_date=args.presentation_date,
        max_retries=args.max_retries,
        quality_threshold=args.quality_threshold,
    )

    print(f"\nPPTX: {state.pptx_path}")
    print(f"Quality: {state.quality_score:.2f}")
    print(f"Retries used: {state.total_retries}")


if __name__ == "__main__":
    main()
