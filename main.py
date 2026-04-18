"""Main entry point for the markdown-to-presentation pipeline."""

import os
from pathlib import Path
from step1 import MarkdownParser
from step2 import ContentTriageAgent
from step3 import ContentExtractor


def process_markdown_to_presentation(markdown_path: str, output_dir: str = "./output"):
    """
    Process a markdown file through all 3 steps to create slide-ready content.
    
    Args:
        markdown_path: Path to the markdown file
        output_dir: Directory for output files
        
    Returns:
        PresentationContent object with all slide content
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Parse markdown into content inventory
    print("\n[Step 1] Parsing markdown...")
    parser = MarkdownParser(image_output_dir=output_path / "images")
    inventory = parser.parse_file(Path(markdown_path))
    print(f"  ✓ Title: {inventory.title}")
    print(f"  ✓ Sections: {inventory.total_sections}")
    print(f"  ✓ Tables: {inventory.total_tables}")
    print(f"  ✓ Images: {inventory.total_images}")
    
    # Step 2: Create slide plan using LLM
    print("\n[Step 2] Creating slide plan with LLM...")
    agent = ContentTriageAgent()
    plan = agent.triage(inventory)
    print(f"  ✓ Slides planned: {plan.total_slides}")
    print(f"  ✓ Charts: {plan.charts_planned}")
    print(f"  ✓ Sections used: {plan.sections_used}/{inventory.total_sections}")
    
    # Step 3: Extract slide-ready content
    print("\n[Step 3] Extracting slide content...")
    extractor = ContentExtractor()
    markdown_text = Path(markdown_path).read_text(encoding='utf-8')
    presentation = extractor.extract(plan, markdown_text, inventory)
    print(f"  ✓ Slides: {len(presentation.slides)}")
    print(f"  ✓ Total words: {presentation.stats.total_word_count}")
    print(f"  ✓ LLM calls: {presentation.stats.llm_api_calls}")
    
    return presentation


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python main.py <markdown_file>")
        print("\nExample:")
        print("  python main.py research/example.md")
        sys.exit(1)
    
    # Check for API key
    api_key = os.getenv("LLM_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("\n⚠ Warning: No API key found. Set LLM_API_KEY or GOOGLE_API_KEY")
        print("   The pipeline requires an API key for Step 2 (triage) and Step 3 (content extraction)")
    
    markdown_file = sys.argv[1]
    result = process_markdown_to_presentation(markdown_file)
    
    print("\n" + "="*60)
    print("PIPELINE COMPLETE")
    print("="*60)
    print(f"Presentation: {result.title}")
    print(f"Slides: {len(result.slides)}")
    print(f"Output: ./output/")
