from pathlib import Path

from step2.slide_plan_models import ChartType, LayoutType, SlideType
from step3.content_models import ChartData, ExtractedBullet, PresentationContent, SlideContent
from step4.assertions import run_all
from step4.deck_builder import build_deck


def _bullet(text: str) -> ExtractedBullet:
    return ExtractedBullet(text=text, priority=8, source_section="test")


def test_generated_deck_is_16x9_and_picture_free(tmp_path: Path) -> None:
    slides = []
    for i in range(1, 16):
        slides.append(
            SlideContent(
                slide_number=i,
                slide_type=SlideType.CONTENT,
                layout=LayoutType.BULLET,
                title=f"Slide {i}",
                subtitle="Subtitle",
                key_message=f"Key message {i}",
                bullets=[_bullet(f"{i * 10}% metric uplift"), _bullet("Improved execution")],
                word_count=20,
            )
        )
    slides[3].slide_type = SlideType.CHART
    slides[3].layout = LayoutType.CHART_WITH_TEXT
    slides[3].chart_data = ChartData(
        chart_type=ChartType.BAR,
        title="Revenue",
        source_table_index=0,
        categories=["Q1", "Q2", "Q3"],
        series=[{"name": "Revenue", "values": [10, 14, 18]}],
        number_format="$#,##0M",
    )

    content = PresentationContent(title="Editable test", total_slides=15, slides=slides)
    from pptx import Presentation

    template = tmp_path / "minimal_template.pptx"
    prs = Presentation()
    prs.save(template)

    out = tmp_path / "out.pptx"
    build_deck(content, str(template), str(out), "Tester", "April 26, 2026")

    results = run_all(str(out))
    assert all(result.passed for result in results.values()), {
        key: result.issues for key, result in results.items()
    }
