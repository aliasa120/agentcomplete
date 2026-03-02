"""Visual image inspection tool.

Flow (like a friend giving you a pendrive with downloaded photos):
1. Download ALL images from provided URLs at FULL RESOLUTION → save to output/candidate_images/
2. Show small 400px thumbnails as base64 so the agent can SEE each image visually
3. Agent selects the best one
4. create_post_image_gemini loads the full-res file from disk and sends it to Gemini

Keeps a URL→filepath manifest so create_post_image_gemini knows which file to load.
"""

import base64
import io
import json
from pathlib import Path
from typing import Any

import requests
from langchain_core.tools import tool
from PIL import Image

_CANDIDATE_DIR = Path("output") / "candidate_images"
_MANIFEST_FILE = _CANDIDATE_DIR / "manifest.json"

# Small thumbnail for vision preview — must stay tiny to fit 10 images in one tool result
_THUMB_PX = 200   # 200px wide keeps each thumb ~15KB

# Show ALL images (we keep thumbnails tiny enough that 10 fit without overflow)
_MAX_SHOW = 10


def _download(url: str) -> bytes | None:
    try:
        r = requests.get(
            url,
            timeout=12,
            headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"},
        )
        r.raise_for_status()
        return r.content
    except Exception as e:
        print(f"[view_candidate_images] Download failed {url[:60]}: {e}")
        return None


def _save_full_res(raw: bytes, path: Path) -> bool:
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        img.save(str(path), "JPEG", quality=95)
        return True
    except Exception as e:
        print(f"[view_candidate_images] Save failed: {e}")
        return False


def _thumb_b64(raw: bytes) -> str | None:
    """Make a small 200px JPEG thumbnail and return as base64 data URI."""
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = img.size
        scale = _THUMB_PX / max(w, h)
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=45)  # low quality = tiny base64
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        print(f"[view_candidate_images] Thumbnail failed: {e}")
        return None


@tool(parse_docstring=True)
def view_candidate_images(image_urls: list[str]) -> list[dict[str, Any]]:
    """Download ALL candidate images and display them visually for selection.

    Downloads every image at FULL RESOLUTION to disk (for Gemini later),
    then shows small 400px thumbnails so you can SEE each image with your vision.

    Evaluate each image you see:
    - **Cleanliness** (MOST IMPORTANT) — must be FREE of other outlet logos,
      chyrons, banners, or text overlays. REJECT any image with foreign branding.
    - **Relevance** — directly depicts the news story.
    - **Visual quality** — sharp, well-lit, professionally composed.
    - **Impact** — eye-catching on social media.

    After viewing all images, use think_tool to record:
    1. A 1-line assessment of each image (clean? relevant? quality?)
    2. Which image you chose and WHY
    3. The exact URL of your chosen image
    4. Which layout from the 20-layout table you will use

    Then call create_post_image_gemini with the chosen URL.

    Args:
        image_urls: All image URLs returned by fetch_images_brave (pass all of them).

    Returns:
        Multimodal content with visual thumbnails of all downloaded images.
    """
    _CANDIDATE_DIR.mkdir(parents=True, exist_ok=True)

    # Skip obviously bad URLs (animated GIFs etc)
    urls = [u for u in image_urls[:10] if u and not u.lower().endswith(".gif")]

    manifest: dict[str, str] = {}          # url → local filepath
    downloaded: list[tuple[int, str, bytes]] = []   # (index, url, raw_bytes)

    # Step 1 — Download everything at full res to disk
    for i, url in enumerate(urls, 1):
        raw = _download(url)
        if not raw:
            continue
        save_path = _CANDIDATE_DIR / f"image_{i}.jpg"
        if _save_full_res(raw, save_path):
            manifest[url] = str(save_path)
            downloaded.append((i, url, raw))
            print(f"[view_candidate_images] ✅ image_{i}.jpg ({len(raw)//1024}KB)")

    # Persist manifest for create_post_image_gemini
    _MANIFEST_FILE.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[view_candidate_images] Manifest: {len(manifest)} images saved")

    if not downloaded:
        return [{"type": "text", "text": (
            "All image downloads failed. Call create_post_image_gemini "
            "directly with the best URL from fetch_images_exa."
        )}]

    total = len(downloaded)

    # Step 2 — Build vision response with thumbnails
    content: list[dict[str, Any]] = [{
        "type": "text",
        "text": (
            f"✅ Downloaded {total} image(s) to output/candidate_images/ (full resolution).\n"
            f"Here are the thumbnails — inspect each one carefully:\n\n"
            "Pick the BEST image:\n"
            "  ❌ REJECT if it has another outlet's logo, chyron, or burnt-in text\n"
            "  ✅ PREFER clean, relevant, sharp, impactful photos\n"
        ),
    }]

    shown = 0
    not_shown: list[tuple[int, str]] = []

    for idx, url, raw in downloaded:
        if shown < _MAX_SHOW:
            data_uri = _thumb_b64(raw)
            content.append({"type": "text", "text": f"\n--- Image {idx}: {url}"})
            if data_uri:
                content.append({"type": "image_url", "image_url": {"url": data_uri}})
            else:
                content.append({"type": "text", "text": "  (thumbnail failed — judge by title)"})
            shown += 1
        else:
            not_shown.append((idx, url))

    if not_shown:
        lines = [f"\nImages downloaded but not shown (judge by title/relevance):"]
        for idx, url in not_shown:
            lines.append(f"  Image {idx}: {url}")
        content.append({"type": "text", "text": "\n".join(lines)})

    content.append({"type": "text", "text": (
        f"\n---\nAll {total} images saved to disk at FULL RESOLUTION for Gemini editing.\n"
        "Now use think_tool to make your selection, then call create_post_image_gemini."
    )})

    return content
