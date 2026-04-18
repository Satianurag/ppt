"""LLM-powered bullet point generation and content transformation."""

from typing import List, Optional
from pydantic import BaseModel, Field

from .content_models import ExtractedBullet
from .markdown_reparser import SectionContent
from llm import get_llm_client, LLMClient, StructuredLLMClient


class BulletRewriteOutput(BaseModel):
    """Structured output for bullet rewriting."""
    bullets: List[str] = Field(
        max_length=6,
        description="Bullet points (max 6, max 8 words each)"
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
        max_length=6,
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
    
    def __init__(self, client: Optional[LLMClient] = None):
        """Initialize the bullet rewriter with LLM client."""
        self.client = client
        
        # Create structured clients if LLM available
        if self.client:
            self.bullet_client = self.client.with_structured_output(BulletRewriteOutput)
            self.merge_client = self.client.with_structured_output(MergedSectionOutput)
        else:
            self.bullet_client = None
            self.merge_client = None
    
    def rewrite_bullets(
        self,
        source_text: str,
        key_message: str,
        section_id: str,
        max_bullets: int = 6,
        max_words_per_bullet: int = 8,
        target_audience: str = "executive"
    ) -> List[ExtractedBullet]:
        """
        Transform source text into optimized bullets using LLM.
        Falls back to rule-based if no LLM client.
        """
        # Fallback to rule-based if no client
        if not self.client or not self.bullet_client:
            return self._fallback_rewrite(
                source_text, key_message, section_id, max_bullets, max_words_per_bullet
            )
        
        prompt = f"""Transform the following content into high-impact presentation bullets.

SOURCE CONTENT:
{source_text[:4000]}  # Truncate if too long

KEY MESSAGE (what this slide must convey):
{key_message}

REQUIREMENTS:
- Generate {max_bullets} bullets maximum
- Each bullet: {max_words_per_bullet} words maximum
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
        
        try:
            result = self.bullet_client.invoke(prompt)
            
            # Convert to ExtractedBullet objects
            extracted = []
            for i, (text, priority, rationale) in enumerate(
                zip(result.bullets, result.priorities, result.rationales)
            ):
                # Truncate if too long
                words = text.split()
                if len(words) > max_words_per_bullet:
                    text = ' '.join(words[:max_words_per_bullet])
                
                extracted.append(ExtractedBullet(
                    text=text,
                    priority=priority,
                    source_section=section_id,
                    rationale=rationale
                ))
            
            return extracted[:max_bullets]
            
        except Exception:
            # Fallback to rule-based extraction
            return self._fallback_rewrite(
                source_text, key_message, section_id, max_bullets, max_words_per_bullet
            )
    
    def rewrite_merged_sections(
        self,
        sections: List[SectionContent],
        key_message: str,
        merge_reasoning: str,
        max_bullets: int = 6,
        max_words_per_bullet: int = 8
    ) -> List[ExtractedBullet]:
        """
        Synthesize multiple sections into coherent bullets.
        Falls back to rule-based if no LLM client.
        """
        # Fallback to rule-based if no client
        if not self.client or not self.merge_client:
            return self._fallback_merge(
                sections, key_message, max_bullets, max_words_per_bullet
            )
        
        # Build combined context
        sections_context = []
        source_section_ids = []
        
        for i, section in enumerate(sections):
            sections_context.append(
                f"SECTION {i+1}: {section.heading}\n"
                f"Content: {section.get_all_text()[:800]}\n"
            )
            source_section_ids.append(section.section_id)
        
        combined_context = "\n---\n".join(sections_context)
        
        prompt = f"""Synthesize multiple content sections into a coherent slide.

SECTIONS TO MERGE:
{combined_context}

MERGE REASONING:
{merge_reasoning}

KEY MESSAGE (unified takeaway):
{key_message}

REQUIREMENTS:
- Create {max_bullets} unified bullets
- Each bullet: {max_words_per_bullet} words max
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
        
        try:
            result = self.merge_client.invoke(prompt)
            
            # Convert to ExtractedBullet
            extracted = []
            section_source = "_".join(source_section_ids[:3])  # Truncated combined ID
            
            for text, priority in zip(result.bullets, result.priorities):
                words = text.split()
                if len(words) > max_words_per_bullet:
                    text = ' '.join(words[:max_words_per_bullet])
                
                extracted.append(ExtractedBullet(
                    text=text,
                    priority=priority,
                    source_section=section_source,
                    rationale=result.merge_strategy
                ))
            
            return extracted[:max_bullets]
            
        except Exception:
            # Fallback: concatenate best bullets from each section
            return self._fallback_merge(
                sections, key_message, max_bullets, max_words_per_bullet
            )
    
    def polish_bullets(
        self,
        bullets: List[str],
        key_message: str
    ) -> List[str]:
        """
        Final polish pass for consistency and impact.
        
        Ensures:
        - Parallel structure
        - Active voice
        - Consistent terminology
        """
        if len(bullets) <= 1 or not self.client:
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
5. Maintain 8 words maximum per bullet
6. Keep the meaning identical, just improve wording

OUTPUT:
Return only the polished bullets, one per line, numbered."""
        
        try:
            response_text = self.client.invoke(prompt)
            
            # Parse response
            polished = []
            for line in response_text.strip().split('\n'):
                # Remove numbering if present
                line = re.sub(r'^\d+\.\s*', '', line.strip())
                if line:
                    polished.append(line)
            
            return polished if polished else bullets
            
        except Exception:
            return bullets
    
    def _fallback_rewrite(
        self,
        source_text: str,
        key_message: str,
        section_id: str,
        max_bullets: int,
        max_words: int
    ) -> List[ExtractedBullet]:
        """Fallback rule-based bullet extraction."""
        import re
        
        # Extract sentences
        sentences = re.split(r'[.!?]+', source_text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
        
        bullets = []
        for i, sentence in enumerate(sentences[:max_bullets]):
            words = sentence.split()
            if len(words) > max_words:
                text = ' '.join(words[:max_words])
            else:
                text = sentence
            
            bullets.append(ExtractedBullet(
                text=text,
                priority=10 - i,  # Descending priority
                source_section=section_id,
                rationale="Fallback extraction"
            ))
        
        return bullets
    
    def _fallback_merge(
        self,
        sections: List[SectionContent],
        key_message: str,
        max_bullets: int,
        max_words: int
    ) -> List[ExtractedBullet]:
        """Fallback for merged sections: pick best from each."""
        all_bullets = []
        
        for section in sections:
            # Get first sentence of each paragraph
            for para in section.paragraphs[:2]:
                import re
                sentences = re.split(r'[.!?]+', para)
                for sent in sentences[:1]:
                    sent = sent.strip()
                    if len(sent) > 20:
                        words = sent.split()
                        if len(words) > max_words:
                            sent = ' '.join(words[:max_words])
                        all_bullets.append((sent, section.section_id))
        
        # Take top bullets by source diversity
        selected = []
        seen_sources = set()
        
        for text, source in all_bullets:
            if len(selected) >= max_bullets:
                break
            if source not in seen_sources or len(seen_sources) >= len(sections):
                selected.append(ExtractedBullet(
                    text=text,
                    priority=10 - len(selected),
                    source_section=source,
                    rationale="Fallback merged extraction"
                ))
                seen_sources.add(source)
        
        return selected
