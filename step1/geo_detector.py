"""Geographic content detection — identifies country/region mentions in text.

Addresses judge feedback from Common Mistakes PPTX:
  "Flag could be added for countries"

Maps detected countries to icon categories for use in infographic renderers.
"""

import re
from typing import List, Dict

# Major countries/regions with icon category mappings
# Covers all regions mentioned across the 24 test markdown files
COUNTRY_MAP: dict[str, str] = {
    # Asia
    "india": "globe", "china": "globe", "japan": "globe",
    "south korea": "globe", "korea": "globe", "singapore": "globe",
    "indonesia": "globe", "malaysia": "globe", "vietnam": "globe",
    "thailand": "globe", "philippines": "globe", "taiwan": "globe",
    "bangladesh": "globe", "pakistan": "globe", "sri lanka": "globe",
    "kazakhstan": "globe", "uzbekistan": "globe",
    # Middle East
    "uae": "globe", "united arab emirates": "globe",
    "saudi arabia": "globe", "qatar": "globe", "oman": "globe",
    "bahrain": "globe", "kuwait": "globe", "israel": "globe",
    # Africa
    "nigeria": "globe", "south africa": "globe", "kenya": "globe",
    "egypt": "globe", "morocco": "globe", "ghana": "globe",
    "ethiopia": "globe", "tanzania": "globe", "rwanda": "globe",
    # Europe
    "uk": "globe", "united kingdom": "globe", "germany": "globe",
    "france": "globe", "italy": "globe", "spain": "globe",
    "netherlands": "globe", "sweden": "globe", "norway": "globe",
    "denmark": "globe", "switzerland": "globe", "romania": "globe",
    "poland": "globe", "austria": "globe", "belgium": "globe",
    "finland": "globe", "ireland": "globe", "portugal": "globe",
    # Americas
    "usa": "globe", "united states": "globe", "canada": "globe",
    "brazil": "globe", "mexico": "globe", "argentina": "globe",
    "colombia": "globe", "chile": "globe", "peru": "globe",
    # Oceania
    "australia": "globe", "new zealand": "globe",
}

# Region groupings for broader detection
REGION_MAP: dict[str, str] = {
    "asia": "globe", "europe": "globe", "africa": "globe",
    "americas": "globe", "north america": "globe", "south america": "globe",
    "latin america": "globe", "middle east": "globe", "mena": "globe",
    "apac": "globe", "asia-pacific": "globe", "emea": "globe",
    "central asia": "globe", "east asia": "globe", "southeast asia": "globe",
    "sub-saharan africa": "globe", "eastern europe": "globe",
    "western europe": "globe", "nordic": "globe", "gcc": "globe",
}

# Compiled patterns for efficient matching
_COUNTRY_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(k) for k in sorted(COUNTRY_MAP.keys(), key=len, reverse=True)) + r')\b',
    re.IGNORECASE
)
_REGION_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(k) for k in sorted(REGION_MAP.keys(), key=len, reverse=True)) + r')\b',
    re.IGNORECASE
)


def detect_countries(text: str) -> List[str]:
    """Detect country names mentioned in text.

    Returns:
        List of unique country names (lowercase) found in text.
    """
    matches = _COUNTRY_PATTERN.findall(text)
    return list(dict.fromkeys(m.lower() for m in matches))


def detect_regions(text: str) -> List[str]:
    """Detect region names mentioned in text.

    Returns:
        List of unique region names (lowercase) found in text.
    """
    matches = _REGION_PATTERN.findall(text)
    return list(dict.fromkeys(m.lower() for m in matches))


def detect_geographic_content(text: str) -> Dict[str, List[str]]:
    """Detect all geographic references in text.

    Returns:
        Dict with 'countries' and 'regions' lists.
    """
    return {
        "countries": detect_countries(text),
        "regions": detect_regions(text),
    }


def has_geographic_content(text: str) -> bool:
    """Quick check whether text contains any geographic references."""
    return bool(_COUNTRY_PATTERN.search(text) or _REGION_PATTERN.search(text))


def get_geo_icon_category(text: str) -> str | None:
    """Return 'globe' icon category if text mentions countries/regions, else None."""
    if has_geographic_content(text):
        return "globe"
    return None
