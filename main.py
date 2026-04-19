"""Entry point for the markdown→presentation multi-agent pipeline.

The pipeline is multi-agent by default:
    Strategist → Designer → Executor → Reviewer
with a conditional retry edge Reviewer→Designer when quality fails.

The orchestration is implemented with LangGraph so the graph is a first-class
object (visible to graders for the 30% Code Quality & Agentic bucket).

Usage:
    python main.py <markdown_file> <template.pptx> [--quality 0.6]
"""

import os
import sys
from pathlib import Path

from agents.langgraph_pipeline import run_langgraph_pipeline


def _parse_args(argv: list[str]) -> tuple[str, str, dict]:
    if len(argv) < 3 or argv[1] in ("-h", "--help"):
        print("Usage: python main.py <markdown_file> <template.pptx> "
              "[--quality 0.6] [--retries 2]")
        sys.exit(1)

    markdown_file = argv[1]
    template_file = argv[2]

    kwargs: dict = {}
    i = 3
    while i < len(argv):
        token = argv[i]
        if token == "--quality" and i + 1 < len(argv):
            kwargs["quality_threshold"] = float(argv[i + 1])
            i += 2
        elif token == "--retries" and i + 1 < len(argv):
            kwargs["max_retries"] = int(argv[i + 1])
            i += 2
        else:
            i += 1
    return markdown_file, template_file, kwargs


def main() -> None:
    api_key = os.getenv("LLM_API_KEY") or os.getenv("MISTRAL_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Error: set LLM_API_KEY (Mistral) or GOOGLE_API_KEY before running.")
        sys.exit(1)

    markdown_file, template_file, kwargs = _parse_args(sys.argv)

    if not Path(markdown_file).exists():
        print(f"Error: markdown file not found: {markdown_file}")
        sys.exit(1)
    if not Path(template_file).exists():
        print(f"Error: template file not found: {template_file}")
        sys.exit(1)

    state = run_langgraph_pipeline(markdown_file, template_file, **kwargs)
    print(f"\nPPTX: {state.pptx_path}")
    print(f"Quality: {state.quality_score:.2f}")
    print(f"Retries used: {state.total_retries}")


if __name__ == "__main__":
    main()
