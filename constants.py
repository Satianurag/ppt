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
MAX_TITLE_CHARS: int = 50
MAX_SUBTITLE_CHARS: int = 80
MAX_KEY_MESSAGE_CHARS: int = 100
MAX_BULLET_CHARS: int = 60

# Rate limiting
MAX_RPM: int = 8
