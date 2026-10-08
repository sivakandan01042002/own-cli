import base64
import hashlib
import io
import mimetypes
from pathlib import Path
from typing import Optional
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from PIL import Image

from app.core.config import settings
from app.core.redis_client import get_cached_response, set_cached_response
from app.core.llm import get_cached_llm

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
MAX_DIMENSION = 1920  # Max dimension to optimize token payload


def _resolve_safe_image_path(target_path: str) -> Path:
    """
    Resolves image path relative to workspace root or current working directory.
    """
    path_obj = Path(target_path)
    if path_obj.is_absolute() and path_obj.exists():
        return path_obj

    root = settings.WORKSPACE_ROOT.resolve()
    resolved = (root / target_path).resolve()
    if resolved.exists():
        return resolved

    cwd_resolved = (Path.cwd() / target_path).resolve()
    if cwd_resolved.exists():
        return cwd_resolved

    return resolved


def _optimize_and_encode_image(image_path: Path) -> tuple[str, str, dict]:
    """
    Validates, optionally resizes large images, and returns (mime_type, base64_str, metadata).
    """
    mime_type, _ = mimetypes.guess_type(str(image_path))
    if not mime_type or not mime_type.startswith("image/"):
        ext = image_path.suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
        }
        mime_type = mime_map.get(ext, "image/png")

    with Image.open(image_path) as img:
        orig_width, orig_height = img.size
        orig_format = img.format or "PNG"
        
        # Downscale if image is larger than MAX_DIMENSION
        if max(orig_width, orig_height) > MAX_DIMENSION:
            scale = MAX_DIMENSION / max(orig_width, orig_height)
            new_size = (int(orig_width * scale), int(orig_height * scale))
            resized_img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            buf = io.BytesIO()
            save_format = "JPEG" if orig_format in ["JPEG", "JPG"] else "PNG"
            resized_img.save(buf, format=save_format, quality=85)
            img_bytes = buf.getvalue()
            current_size = new_size
        else:
            with open(image_path, "rb") as f:
                img_bytes = f.read()
            current_size = (orig_width, orig_height)

    b64_data = base64.b64encode(img_bytes).decode("utf-8")
    meta = {
        "original_dimensions": f"{orig_width}x{orig_height}",
        "processed_dimensions": f"{current_size[0]}x{current_size[1]}",
        "mime_type": mime_type,
        "format": orig_format,
    }
    return mime_type, b64_data, meta


@tool
def inspect_image(image_path: str, prompt: str = "Analyze this image in detail and extract all key visual and textual information.") -> str:
    """
    Inspects and analyzes a local image file (PNG, JPG, WebP, GIF) in the workspace using Multimodal Vision.
    Use this tool to inspect UI screenshots, wireframes, architecture diagrams, charts, or error screens.
    Results are cached in Redis to guarantee zero repeated costs.

    Args:
        image_path: Relative or absolute path to the image file.
        prompt: Specific inspection instructions (e.g., 'Extract the color palette and layout hierarchy' or 'Transcribe all text and error tracebacks in this screenshot').

    Returns:
        Structured visual breakdown including layout, UI components, text content, colors, and diagram relationships.
    """
    try:
        resolved_path = _resolve_safe_image_path(image_path)

        if not resolved_path.exists():
            return f"Error: Image file not found at '{image_path}'."

        if resolved_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return f"Error: Unsupported image format '{resolved_path.suffix}'. Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}"

        # Compute SHA-256 hash for zero-cost caching
        with open(resolved_path, "rb") as f:
            file_bytes = f.read()
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        cache_key = f"vision_cache:{file_hash}:{hashlib.md5(prompt.encode('utf-8')).hexdigest()}"

        # 1. Check Redis cache first (0ms, 0 API calls)
        cached_result = get_cached_response(cache_key)
        if cached_result:
            return f"[Cached Vision Analysis for {resolved_path.name}]\n{cached_result}"

        # 2. Encode and optimize image
        mime_type, b64_data, meta = _optimize_and_encode_image(resolved_path)

        # 3. Call Gemini Multimodal Vision
        vision_llm = get_cached_llm(provider="gemini", model_name=settings.GEMINI_MODEL, temperature=0.0)

        user_content = [
            {
                "type": "text",
                "text": (
                    f"Instruction: {prompt}\n\n"
                    f"Context: Image file '{resolved_path.name}' ({meta['original_dimensions']}, {meta['format']}).\n"
                    f"Please provide a structured, precise analysis focusing on visual layout, textual transcription, "
                    f"UI components, color styles, and actionable implementation insights."
                ),
            },
            {
                "type": "image_url",
                "image_url": f"data:{mime_type};base64,{b64_data}",
            },
        ]

        response = vision_llm.invoke([HumanMessage(content=user_content)])
        result_text = response.content if hasattr(response, "content") else str(response)

        # 4. Cache result in Redis (24 hours TTL)
        set_cached_response(cache_key, result_text, ttl=86400)

        return f"[Vision Analysis: {resolved_path.name} ({meta['original_dimensions']})]\n{result_text}"

    except Exception as e:
        return f"Error analyzing image '{image_path}': {str(e)}"


@tool
def generate_image(
    prompt: str,
    output_path: str = "",
    width: int = 1024,
    height: int = 1024,
) -> str:
    """
    Generates a high-resolution AI image from a text prompt and saves it to disk in the workspace.
    Supports creating logos, UI mockups, diagrams, illustrations, banners, and concept art.
    Uses high-speed Flux.1/SDXL zero-cost image synthesis by default.

    Args:
        prompt: Detailed descriptive prompt for the image (e.g. 'A sleek modern neon dashboard icon with blue accents, vector style').
        output_path: Optional relative file path to save the generated image (e.g. 'assets/logo.png'). If omitted, saved to 'assets/generated_<timestamp>.png'.
        width: Image width in pixels (default: 1024, range: 256-2048).
        height: Image height in pixels (default: 1024, range: 256-2048).

    Returns:
        Confirmation message with the resolved output file path and image dimensions.
    """
    import time
    import urllib.parse
    import urllib.request

    try:
        clean_prompt = prompt.strip()
        if not clean_prompt:
            return "Error: Prompt cannot be empty for image generation."

        # Determine target output path
        root = settings.WORKSPACE_ROOT.resolve()
        if not output_path or not output_path.strip():
            timestamp = int(time.time())
            target_rel = Path("assets") / f"generated_{timestamp}.png"
        else:
            target_rel = Path(output_path.strip().replace("\\", "/"))

        # Ensure safe workspace resolution
        target_file = (root / target_rel).resolve()
        if not str(target_file).startswith(str(root)):
            return f"Error: Target path '{output_path}' is outside the workspace."

        # Clamp width and height
        w = max(256, min(width, 2048))
        h = max(256, min(height, 2048))

        # Build Pollinations image URL
        encoded_prompt = urllib.parse.quote(clean_prompt)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={w}&height={h}&nologo=true"

        # Download image bytes with proper headers
        req = urllib.request.Request(
            image_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Referer": "https://pollinations.ai/",
                "Origin": "https://pollinations.ai",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=45) as response:
            if response.status != 200:
                return f"Error: Failed to download generated image (HTTP status {response.status})."
            img_data = response.read()

        if not img_data or len(img_data) < 500:
            return "Error: Received empty or invalid image response from generation engine."

        # Ensure parent directory exists and write image
        target_file.parent.mkdir(parents=True, exist_ok=True)
        with open(target_file, "wb") as f:
            f.write(img_data)

        rel_out = target_file.relative_to(root).as_posix()
        size_kb = len(img_data) / 1024

        return (
            f"Successfully generated image from prompt '{clean_prompt[:60]}...' "
            f"and saved to '{rel_out}' ({w}x{h} px, {size_kb:.1f} KB)."
        )

    except Exception as e:
        return f"Error generating image from prompt '{prompt[:60]}': {str(e)}"

