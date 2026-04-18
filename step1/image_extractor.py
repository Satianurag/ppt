"""Base64 image extraction from markdown."""

import base64
import hashlib
import re
from pathlib import Path
from typing import Tuple, List
from .models import ImageInfo


# Regex for base64 embedded images
BASE64_IMAGE_RE = re.compile(
    r'!\[([^\]]*)\]\(data:image/(\w+);base64,([A-Za-z0-9+/=\n]+)\)',
    re.IGNORECASE
)

# Regex for URL-based images
URL_IMAGE_RE = re.compile(
    r'!\[([^\]]*)\]\((https?://[^)]+)\)',
    re.IGNORECASE
)

# Regex for local images
LOCAL_IMAGE_RE = re.compile(
    r'!\[([^\]]*)\]\((?!data:|https?://)([^)]+)\)',
    re.IGNORECASE
)


def extract_base64_images(markdown: str, output_dir: Path) -> Tuple[str, List[ImageInfo]]:
    """Extract base64 images from markdown and save to files.
    
    Args:
        markdown: Raw markdown text
        output_dir: Directory to save extracted images
        
    Returns:
        Tuple of (modified markdown with file paths, list of ImageInfo)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    images = []
    image_index = 0
    
    def replacer(match) -> str:
        nonlocal image_index
        
        alt_text = match.group(1)
        img_format = match.group(2).lower()
        base64_data = match.group(3).replace('\n', '')  # Remove newlines
        
        try:
            # Decode base64
            img_bytes = base64.b64decode(base64_data)
            
            # Generate filename from content hash
            content_hash = hashlib.md5(img_bytes).hexdigest()[:8]
            filename = f"img_{content_hash}.{img_format}"
            filepath = output_dir / filename
            
            # Save image (only if not exists)
            if not filepath.exists():
                filepath.write_bytes(img_bytes)
            
            # Record image info
            images.append(ImageInfo(
                index=image_index,
                image_type="base64",
                format=img_format,
                source=match.group(0)[:100] + "...",  # Truncated for storage
                extracted_path=str(filepath),
                alt_text=alt_text if alt_text else None
            ))
            image_index += 1
            
            # Return markdown with file path
            return f"![{alt_text}]({filepath})"
            
        except Exception:
            # If extraction fails, keep original
            return match.group(0)
    
    # Replace all base64 images
    modified_markdown = BASE64_IMAGE_RE.sub(replacer, markdown)
    
    return modified_markdown, images


def extract_url_images(markdown: str) -> List[ImageInfo]:
    """Detect URL-based images in markdown.
    
    Args:
        markdown: Raw markdown text
        
    Returns:
        List of ImageInfo for URL images (not downloaded, just cataloged)
    """
    images = []
    
    for i, match in enumerate(URL_IMAGE_RE.finditer(markdown)):
        alt_text = match.group(1)
        url = match.group(2)
        
        # Detect format from URL
        fmt = "png"  # default
        if ".jpg" in url.lower() or ".jpeg" in url.lower():
            fmt = "jpg"
        elif ".svg" in url.lower():
            fmt = "svg"
        elif ".gif" in url.lower():
            fmt = "gif"
        
        images.append(ImageInfo(
            index=i,
            image_type="url",
            format=fmt,
            source=url,
            alt_text=alt_text if alt_text else None
        ))
    
    return images


def extract_local_images(markdown: str) -> List[ImageInfo]:
    """Detect local image references in markdown.
    
    Args:
        markdown: Raw markdown text
        
    Returns:
        List of ImageInfo for local images
    """
    images = []
    
    for i, match in enumerate(LOCAL_IMAGE_RE.finditer(markdown)):
        alt_text = match.group(1)
        path = match.group(2)
        
        # Detect format from extension
        fmt = "png"  # default
        if ".jpg" in path.lower() or ".jpeg" in path.lower():
            fmt = "jpg"
        elif ".svg" in path.lower():
            fmt = "svg"
        elif ".gif" in path.lower():
            fmt = "gif"
        
        images.append(ImageInfo(
            index=i,
            image_type="local",
            format=fmt,
            source=path,
            alt_text=alt_text if alt_text else None
        ))
    
    return images


def extract_all_images(markdown: str, output_dir: Path) -> Tuple[str, List[ImageInfo]]:
    """Extract all types of images from markdown.
    
    Args:
        markdown: Raw markdown text
        output_dir: Directory to save extracted images
        
    Returns:
        Tuple of (modified markdown, list of all ImageInfo)
    """
    # First extract base64 images (modifies markdown)
    modified_md, base64_images = extract_base64_images(markdown, output_dir)
    
    # Then detect URL and local images
    url_images = extract_url_images(modified_md)
    local_images = extract_local_images(modified_md)
    
    # Combine all images with updated indices
    all_images = base64_images + url_images + local_images
    
    # Re-index all images
    for i, img in enumerate(all_images):
        img.index = i
    
    return modified_md, all_images
