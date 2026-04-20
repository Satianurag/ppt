"""LLM-powered bullet point generation and content transformation.

Reuses patterns from:
- PPTAgent content_organizer.yaml: dual-format output (paragraph + bullet)
- PPTAgent presentation/layout.py LENGTHY_REWRITE_PROMPT: LLM compression
  instead of truncation when content exceeds character limits
- PPTAgent editor.yaml: suggested_characters enforcement
"""

import re
from typing import List, Optional
from pydantic import BaseModel, Field

from .content_models import ExtractedBullet
from .markdown_reparser import SectionContent
from llm import LLMClient, StructuredLLMClient
from constants import MAX_BULLETS_PER_SLIDE, MAX_WORDS_PER_BULLET, MAX_BULLET_CHARS, VERBOSITY_RULES, DEFAULT_VERBOSITY


class BulletRewriteOutput(BaseModel):
    """Structured output for bullet rewriting."""
    bullets: List[str] = Field(
        max_length=MAX_BULLETS_PER_SLIDE,
        description="Bullet points"
    )
    priorities: List[int] = Field(
        description="Importance score 1-10 for each bullet"
    )
    rationales: List[str] = Field(
        description="Why each bullet supports the key message"
    )


class MergedSectionOutput(BaseModel):
    """Structured output for merged section synthesis."""
    bullets: List[str] = Field(
        max_length=MAX_BULLETS_PER_SLIDE,
        description="Synthesized bullets from multiple sections"
    )
    priorities: List[int] = Field(
        description="Importance scores"
    )
    merge_strategy: str = Field(
        description="How sections were combined"
    )


class BulletRewriter:
    """LLM-powered bullet point generation with quality optimization."""

    def __init__(self, client: LLMClient) -> None:
        """Initialize the bullet rewriter with LLM client.

        Args:
            client: LLMClient instance (required, no fallback).
        """
        self.client = client
        self.bullet_client: StructuredLLMClient = client.with_structured_output(BulletRewriteOutput)
        self.merge_client: StructuredLLMClient = client.with_structured_output(MergedSectionOutput)

    def rewrite_bullets(
        self,
        source_text: str,
        key_message: str,
        section_id: str,
        max_bullets: int = MAX_BULLETS_PER_SLIDE,
        max_words_per_bullet: int = MAX_WORDS_PER_BULLET,
        target_audience: str = "executive",
        feedback_context: str = "",
        verbosity: str = DEFAULT_VERBOSITY,
    ) -> List[ExtractedBullet]:
        """Transform source text into optimized bullets using LLM.

        Args:
            feedback_context: Reviewer feedback from a previous attempt.
                Injected into the prompt so the LLM can correct prior issues
                (PPTAgent retry-with-feedback pattern).
            verbosity: One of 'concise', 'normal', 'detailed'. Controls
                bullet count and length per SlidesAI rules.
        """
        feedback_block = ""
        if feedback_context:
            feedback_block = (
                f"\nPREVIOUS ATTEMPT FEEDBACK (fix these issues):\n"
                f"{feedback_context}\n"
            )

        verbosity_instruction = VERBOSITY_RULES.get(verbosity, VERBOSITY_RULES[DEFAULT_VERBOSITY])

        prompt = f"""Transform the following content into high-impact presentation bullets.

SOURCE CONTENT:
{source_text[:4000]}

KEY MESSAGE (what this slide must convey):
{key_message}
{feedback_block}
VERBOSITY MODE: {verbosity_instruction}

REQUIREMENTS:
- Generate {max_bullets} bullets maximum
- Each bullet: {max_words_per_bullet} words maximum, {MAX_BULLET_CHARS} characters maximum
- Use powerful action verbs (Drive, Accelerate, Reduce, Increase, etc.)
- Parallel structure (all start with verb or all noun phrases)
- Quantify where possible (%, $, numbers)
- One idea per bullet
- Order by importance (most important first)

TARGET AUDIENCE: {target_audience}

OUTPUT FORMAT:
Return JSON with:
- bullets: array of strings (the bullet text)
- priorities: array of integers 1-10 (importance)
- rationales: array of strings (why this bullet matters)

Make every word count. Be concise and impactful."""

        result = self.bullet_client.invoke_with_retry(prompt, max_retries=3)

        extracted = []
        for i, (text, priority, rationale) in enumerate(
            zip(result.bullets, result.priorities, result.rationales)
        ):
            # LLM compression instead of truncation (PPTAgent length_rewrite pattern)
            text = self._compress_if_overlong(text, MAX_BULLET_CHARS)

            extracted.append(ExtractedBullet(
                text=text,
                priority=priority,
                source_section=section_id,
                rationale=rationale,
            ))

        return extracted[:max_bullets]

    def rewrite_merged_sections(
        self,
        sections: List[SectionContent],
        key_message: str,
        merge_reasoning: str,
        max_bullets: int = MAX_BULLETS_PER_SLIDE,
        max_words_per_bullet: int = MAX_WORDS_PER_BULLET,
        feedback_context: str = "",
    ) -> List[ExtractedBullet]:
        """Synthesize multiple sections into coherent bullets.

        Args:
            feedback_context: Reviewer feedback from a previous attempt.
        """
        sections_context = []
        source_section_ids = []

        for i, section in enumerate(sections):
            sections_context.append(
                f"SECTION {i+1}: {section.heading}\n"
                f"Content: {section.get_all_text()[:800]}\n"
            )
            source_section_ids.append(section.section_id)

        combined_context = "\n---\n".join(sections_context)

        feedback_block = ""
        if feedback_context:
            feedback_block = (
                f"\nPREVIOUS ATTEMPT FEEDBACK (fix these issues):\n"
                f"{feedback_context}\n"
            )

        prompt = f"""Synthesize multiple content sections into a coherent slide.

SECTIONS TO MERGE:
{combined_context}

MERGE REASONING:
{merge_reasoning}

KEY MESSAGE (unified takeaway):
{key_message}
{feedback_block}

REQUIREMENTS:
- Create {max_bullets} unified bullets
- Each bullet: {max_words_per_bullet} words max, {MAX_BULLET_CHARS} characters max
- Synthesize across sections (don't just list section summaries)
- Find common themes and connections
- Tell a cohesive story
- Use consistent voice and structure
- Prioritize cross-cutting insights

OUTPUT FORMAT:
Return JSON with:
- bullets: array of synthesized bullets
- priorities: importance scores
- merge_strategy: brief description of synthesis approach

Create a unified narrative, not a list of section summaries."""

        result = self.merge_client.invoke_with_retry(prompt, max_retries=3)

        extracted = []
        section_source = "_".join(source_section_ids[:3])

        for text, priority in zip(result.bullets, result.priorities):
            text = self._compress_if_overlong(text, MAX_BULLET_CHARS)

            extracted.append(ExtractedBullet(
                text=text,
                priority=priority,
                source_section=section_source,
                rationale=result.merge_strategy,
            ))

        return extracted[:max_bullets]

    def polish_bullets(
        self,
        bullets: List[str],
        key_message: str,
    ) -> List[str]:
        """Final polish pass for consistency and impact."""
        if len(bullets) <= 1:
            return bullets

        bullets_text = "\n".join([f"{i+1}. {b}" for i, b in enumerate(bullets)])

        prompt = f"""Polish these bullets for maximum impact and consistency.

CURRENT BULLETS:
{bullets_text}

KEY MESSAGE:
{key_message}

POLISH REQUIREMENTS:
1. Ensure parallel structure (all start similarly)
2. Use active voice throughout
3. Remove redundant words
4. Standardize terminology
5. Maintain {MAX_WORDS_PER_BULLET} words maximum per bullet
6. Each bullet must not exceed {MAX_BULLET_CHARS} characters
7. Keep the meaning identical, just improve wording

OUTPUT:
Return only the polished bullets, one per line, numbered."""

        response_text = self.client.invoke_with_retry(prompt, max_retries=2)

        polished = []
        for line in response_text.strip().split('\n'):
            line = re.sub(r'^\d+\.\s*', '', line.strip())
            if line:
                polished.append(line)

        return polished if polished else bullets

    def _compress_if_overlong(self, text: str, max_chars: int) -> str:
        """LLM compression instead of truncation (PPTAgent length_rewrite pattern).

        Reused from PPTAgent presentation/layout.py LENGTHY_REWRITE_PROMPT:
        when content exceeds suggested_characters, use LLM to compress
        rather than blindly truncating.
        """
        if len(text) <= max_chars:
            return text

        prompt = (
            f"Rewrite the following text to be concise and suitable for a "
            f"presentation slide. It must not exceed {max_chars} characters. "
            f"Preserve the original meaning. Do not invent new abbreviations.\n\n"
            f"Text: {text}\n\n"
            f"Rewritten (max {max_chars} characters):"
        )

        compressed = self.client.invoke(prompt)
        compressed = compressed.strip().strip('"').strip("'")

        if len(compressed) <= max_chars and compressed:
            return compressed

        return text[:max_chars]
