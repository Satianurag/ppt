"""Single source of truth for pipeline-wide constants."""

# Maximum markdown input size (hackathon brief: "Maximum markdown input size is 5 MB")
MAX_INPUT_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 MB

# Slide budget — configurable per hackathon brief (10-15 range)
SLIDE_BUDGET: int = 15

# Mandatory slide slots (title, agenda, executive summary, thank you)
MANDATORY_SLIDES: int = 4

# Chart slide cap — used as LLM guidance, not a hard truncator.
# We no longer drop tables past this index; the planner is allowed to
# promote as many chart slides as the deck budget holds.
MAX_CHART_SLIDES: int = 8

# Bullet capacity per slide — deliberately loose so the planner can render
# dense slides when the content demands it. Hard word caps were the root cause
# of the 4-10% coverage failure on long decks (UAE Solar = 12k words → 500).
MAX_BULLETS_PER_SLIDE: int = 10

# Per-bullet word ceiling (soft guidance, enforced as a warning only)
MAX_WORDS_PER_BULLET: int = 22

# Word budget per slide (soft guidance for the LLM, not a hard cap)
TARGET_WORDS_PER_SLIDE: int = 80
MAX_WORDS_PER_SLIDE: int = 180

# Character limits (reused from PPTAgent editor.yaml pattern)
MAX_TITLE_CHARS: int = 100
MAX_SUBTITLE_CHARS: int = 200
MAX_KEY_MESSAGE_CHARS: int = 240
MAX_BULLET_CHARS: int = 220

# Rate limiting (conservative for Mistral service tier limits)
MAX_RPM: int = 4

# Verbosity control — exact rules from SlidesAI build_slides.py:4184-4201
VERBOSITY_RULES: dict[str, str] = {
    "concise": (
        "ULTRA-CONCISE mode. Each slide gets AT MOST 3 bullets. "
        "Each bullet must be 6-10 words max — a punchy phrase, not a sentence. "
        "Prefer a single impactful statement over a list whenever possible."
    ),
    "normal": (
        "NORMAL mode. 3-5 bullets per slide, each a single compact sentence or key phrase. "
        "Keep titles short and specific; put numbers in bullets, not titles."
    ),
    "detailed": (
        "DETAILED mode. 4-7 bullets per slide with sufficient explanation for a reader unfamiliar "
        "with the topic. Each bullet may be 1-2 sentences. Include supporting numbers, examples, "
        "or mechanisms where relevant."
    ),
}

DEFAULT_VERBOSITY: str = "detailed"
