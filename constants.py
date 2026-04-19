"""Single source of truth for pipeline-wide constants."""

# Slide budget — configurable per hackathon brief (10-15 range)
SLIDE_BUDGET: int = 15

# Mandatory slide slots (title, agenda, executive summary, thank you)
MANDATORY_SLIDES: int = 4

# Maximum chart slides recommended
MAX_CHART_SLIDES: int = 5

# Bullet constraints
MAX_BULLETS_PER_SLIDE: int = 6
MAX_WORDS_PER_BULLET: int = 8

# Word budget per slide
TARGET_WORDS_PER_SLIDE: int = 50
MAX_WORDS_PER_SLIDE: int = 60

# Character limits (reused from PPTAgent editor.yaml pattern)
MAX_TITLE_CHARS: int = 100
MAX_SUBTITLE_CHARS: int = 150
MAX_KEY_MESSAGE_CHARS: int = 200
MAX_BULLET_CHARS: int = 120

# Rate limiting
MAX_RPM: int = 8

# Verbosity control — exact rules from SlidesAI build_slides.py:4184-4201
VERBOSITY_RULES: dict[str, str] = {
    "concise": (
        "ULTRA-CONCISE mode. Each slide gets AT MOST 2 bullets. "
        "Each bullet must be 6-10 words max — a punchy phrase, not a sentence. "
        "Prefer a single impactful statement over a list whenever possible. "
        "Step cards in method_process: 1-sentence max per step, 8 words max."
    ),
    "normal": (
        "NORMAL mode. 2-4 bullets per slide, each a single compact sentence or key phrase. "
        "For hero_dark or no-image challenge_solution slides, prefer 3 bullets; never exceed 4."
    ),
    "detailed": (
        "DETAILED mode. 3-5 bullets per slide with sufficient explanation for a reader unfamiliar "
        "with the topic. Each bullet may be 1-2 sentences. Include supporting numbers, examples, "
        "or mechanisms where relevant."
    ),
}

DEFAULT_VERBOSITY: str = "normal"
