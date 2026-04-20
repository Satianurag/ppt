"""Extract chart/table data from base64 images embedded in markdown.

Uses Mistral vision models to analyze chart images and convert them
into structured data (markdown tables) that the existing pipeline
can process as native editable charts.
"""

import base64
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import requests


VISION_MODEL = os.getenv("VISION_MODEL", "mistral-small-2603")
VISION_PROMPT = """Analyze this chart/visualization image carefully. Extract ALL data shown.

Return ONLY valid JSON with these keys:
{
  "chart_type": "bar|line|pie|table|scatter|heatmap|other",
  "title": "chart title if visible",
  "description": "one-line description of what the chart shows",
  "categories": ["category1", "category2", ...],
  "series": [
    {"name": "series name", "values": [1.0, 2.0, ...]},
  ],
  "x_label": "x-axis label",
  "y_label": "y-axis label",
  "unit": "USD|%|MW|count|etc"
}

Rules:
- Extract ALL categories and values visible in the chart
- Use actual numbers (not rounded), include decimals if shown
- For pie charts, categories are slice labels and values are percentages
- For tables, treat each column as a series
- If you cannot extract data, return {"chart_type": "other", "description": "..."}"""


@dataclass
class ExtractedImage:
    """Data extracted from a single image via vision model."""
    index: int
    alt_text: str
    chart_type: str = "other"
    title: str = ""
    description: str = ""
    categories: List[str] = field(default_factory=list)
    series: List[dict] = field(default_factory=list)
    x_label: str = ""
    y_label: str = ""
    unit: str = ""
    raw_json: dict = field(default_factory=dict)
    error: str = ""


def extract_images_from_markdown(markdown_text: str) -> List[Tuple[int, str, str]]:
    """Find all base64 images in markdown text.

    Returns list of (position, alt_text, base64_data).
    """
    pattern = r'!\[([^\]]*)\]\(data:image/(?:png|jpeg|jpg);base64,([A-Za-z0-9+/=]+)\)'
    matches = []
    for match in re.finditer(pattern, markdown_text):
        matches.append((match.start(), match.group(1), match.group(2)))
    return matches


def _call_vision_api(api_key: str, base64_data: str, model: str = VISION_MODEL) -> dict:
    """Send image to Mistral vision API and get structured data back."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": VISION_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{base64_data}"},
                },
            ],
        }],
        "max_tokens": 1500,
        "temperature": 0.1,
    }

    for attempt in range(3):
        resp = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        if resp.status_code == 429:
            wait = 2 ** (attempt + 1)
            print(f"    [Vision] Rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        result = resp.json()
        content = result["choices"][0]["message"]["content"]
        # Extract JSON from response (may be wrapped in ```json ... ```)
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        # Try parsing the whole response as JSON
        return json.loads(content)

    return {"chart_type": "other", "error": "Rate limited after 3 retries"}


def analyze_images(
    markdown_text: str,
    api_key: Optional[str] = None,
    max_images: int = 50,
) -> List[ExtractedImage]:
    """Extract and analyze all images in a markdown document.

    Args:
        markdown_text: Raw markdown content with base64 images.
        api_key: Mistral API key (reads MISTRAL_API_KEY env if not provided).
        max_images: Maximum images to process (for cost control).

    Returns:
        List of ExtractedImage with structured data from each image.
    """
    api_key = api_key or os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("MISTRAL_API_KEY required for image extraction")

    raw_images = extract_images_from_markdown(markdown_text)
    if not raw_images:
        return []

    print(f"  [Vision] Found {len(raw_images)} images in markdown")
    results = []

    for i, (pos, alt_text, b64_data) in enumerate(raw_images[:max_images]):
        print(f"  [Vision] Processing image {i+1}/{min(len(raw_images), max_images)}: "
              f"\"{alt_text[:40]}\" ({len(b64_data) * 3 // 4 // 1024} KB)")

        extracted = ExtractedImage(index=i, alt_text=alt_text)

        try:
            data = _call_vision_api(api_key, b64_data)
            extracted.chart_type = data.get("chart_type", "other")
            extracted.title = data.get("title", "")
            extracted.description = data.get("description", "")
            extracted.categories = data.get("categories", [])
            extracted.series = data.get("series", [])
            extracted.x_label = data.get("x_label", "")
            extracted.y_label = data.get("y_label", "")
            extracted.unit = data.get("unit", "")
            extracted.raw_json = data
            extracted.error = data.get("error", "")
        except Exception as e:
            extracted.error = str(e)
            print(f"    [Vision] Error: {e}")

        results.append(extracted)
        # Small delay between calls to avoid rate limits
        if i < len(raw_images) - 1:
            time.sleep(0.5)

    convertible = sum(1 for r in results if r.chart_type != "other" and r.categories)
    print(f"  [Vision] Extracted data from {convertible}/{len(results)} images")

    return results


def image_to_markdown_table(img: ExtractedImage) -> str:
    """Convert extracted image data to a markdown table.

    This allows the existing pipeline to process image-derived data
    as regular tables, which then get converted to editable charts.
    """
    if not img.categories or not img.series:
        return ""

    title = img.title or img.description or f"Image {img.index + 1}"
    lines = [f"\n#### {title}\n"]

    # Build header
    header_parts = [img.x_label or "Category"]
    for s in img.series:
        name = s.get("name", "Value")
        if img.unit and img.unit not in name:
            name = f"{name} ({img.unit})"
        header_parts.append(name)
    lines.append("| " + " | ".join(header_parts) + " |")
    lines.append("| " + " | ".join(["---"] * len(header_parts)) + " |")

    # Build rows
    for j, cat in enumerate(img.categories):
        row_parts = [str(cat)]
        for s in img.series:
            vals = s.get("values", [])
            val = vals[j] if j < len(vals) else ""
            row_parts.append(str(val))
        lines.append("| " + " | ".join(row_parts) + " |")

    lines.append("")
    return "\n".join(lines)


def enrich_markdown_with_image_data(
    markdown_text: str,
    api_key: Optional[str] = None,
    max_images: int = 50,
) -> str:
    """Pre-process markdown: extract images via vision and inject as tables.

    The original image references are kept (for context) and the extracted
    data is appended as markdown tables right after each image.
    This enriched markdown is then fed to the standard pipeline.

    Args:
        markdown_text: Raw markdown with base64 images.
        api_key: Mistral API key.
        max_images: Max images to process.

    Returns:
        Enriched markdown with image data converted to tables.
    """
    extracted = analyze_images(markdown_text, api_key, max_images)
    if not extracted:
        return markdown_text

    # Find image positions and insert tables after them
    pattern = r'!\[[^\]]*\]\(data:image/(?:png|jpeg|jpg);base64,[A-Za-z0-9+/=]+\)'
    image_matches = list(re.finditer(pattern, markdown_text))

    # Build enriched markdown by inserting tables after images
    parts = []
    last_end = 0
    tables_added = 0

    for i, match in enumerate(image_matches):
        if i >= len(extracted):
            break

        img = extracted[i]
        table_md = image_to_markdown_table(img)

        # Keep everything up to and including the image reference
        parts.append(markdown_text[last_end:match.end()])

        # Insert the extracted table data after the image
        if table_md:
            parts.append(f"\n\n<!-- Extracted from image above by vision model -->\n{table_md}")
            tables_added += 1

        last_end = match.end()

    # Append remaining text
    parts.append(markdown_text[last_end:])

    print(f"  [Vision] Injected {tables_added} tables from images into markdown")
    return "".join(parts)
