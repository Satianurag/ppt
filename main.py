"""Main entry point for the markdown-to-presentation pipeline.

Steps 1-4: Parse → Triage → Extract → Render PPTX.
All LLM calls use retry-with-feedback (PPTAgent pattern).
No image handling. No fallback code.
"""

import os
import sys
from pathlib import Path

from step1 import MarkdownParser
from step2 import ContentTriageAgent
from step3 import ContentExtractor
from step3.content_models import PresentationContent
from step4 import build_presentation
from llm import get_llm_client


def process_markdown_to_presentation(
    markdown_path: str,
    template_path: str | None = None,
    output_dir: str = "./output",
) -> tuple[PresentationContent, str | None]:
    """Process a markdown file through all 4 steps to create a PPTX.

    Args:
        markdown_path: Path to input markdown file.
        template_path: Path to Slide Master PPTX template. If None, skips Step 4.
        output_dir: Directory for output files.

    Returns:
        Tuple of (PresentationContent, pptx_path or None).
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    client = get_llm_client()

    # Step 1: Parse markdown into content inventory
    print("\n[Step 1] Parsing markdown...")
    parser = MarkdownParser()
    inventory = parser.parse_file(Path(markdown_path))
    print(f"  Title: {inventory.title}")
    print(f"  Sections: {inventory.total_sections}")
    print(f"  Tables: {inventory.total_tables}")

    # Step 2: Create slide plan using LLM (with retry-with-feedback)
    print("\n[Step 2] Creating slide plan with LLM...")
    agent = ContentTriageAgent(client=client)
    plan = agent.triage(inventory)
    print(f"  Slides planned: {plan.total_slides}")
    print(f"  Charts: {plan.charts_planned}")
    print(f"  Sections used: {plan.sections_used}/{inventory.total_sections}")

    # Step 3: Extract slide-ready content (with LLM bullet rewriting)
    print("\n[Step 3] Extracting slide content...")
    extractor = ContentExtractor(client=client)
    markdown_text = Path(markdown_path).read_text(encoding='utf-8')
    presentation = extractor.extract(plan, markdown_text, inventory)
    print(f"  Slides: {len(presentation.slides)}")
    if presentation.stats:
        print(f"  Total words: {presentation.stats.total_word_count}")
        print(f"  LLM calls: {presentation.stats.llm_api_calls}")

    # Generate extraction report
    report = extractor.generate_report(presentation)
    report_path = output_path / "extraction_report.txt"
    report_path.write_text(report, encoding='utf-8')
    print(f"\n  Report saved to: {report_path}")

    # Step 4: Render PPTX (pure code, no LLM calls)
    pptx_path = None
    if template_path is not None:
        print("\n[Step 4] Rendering PPTX...")
        md_stem = Path(markdown_path).stem
        pptx_file = str(output_path / f"{md_stem}.pptx")
        pptx_path, issues = build_presentation(presentation, template_path, pptx_file)
    else:
        print("\n[Step 4] Skipped — no template provided.")

    return presentation, pptx_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <markdown_file> [template.pptx]")
        print("\nExample:")
        print("  python main.py research/example.md template.pptx")
        sys.exit(1)

    api_key = os.getenv("LLM_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("\nWarning: No API key found. Set LLM_API_KEY or GOOGLE_API_KEY")
        sys.exit(1)

    markdown_file = sys.argv[1]
    template_file = sys.argv[2] if len(sys.argv) > 2 else None
    result, pptx_path = process_markdown_to_presentation(markdown_file, template_file)

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"Presentation: {result.title}")
    print(f"Slides: {len(result.slides)}")
    if pptx_path:
        print(f"PPTX: {pptx_path}")

    issues = result.validate_completeness()
    if issues:
        print("\nIssues found:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\nNo issues found.")
