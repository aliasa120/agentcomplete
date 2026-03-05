"""Parallel image analyzer using google/gemini-3-flash via LiteLLM.

Flow:
1. Receives up to 5 image URLs (already on disk from view_candidate_images)
2. Fires 5 PARALLEL requests to google/gemini-3-flash (vision)
3. Each request returns structured JSON specs:
   - quality_score (1-10)
   - faces: count + positions
   - clear_areas: available text placement zones
   - dominant_colors: hex values
   - objects: main recognizable objects
   - recommendation: best layout suggestion for this image
4. Returns all specs so the agent can pick the best image AND
   craft precise editing prompts for create_post_image_gemini.
"""

import base64
import io
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from langchain_core.tools import tool
from PIL import Image

# ── Config ────────────────────────────────────────────────────────────────────
_MANIFEST_FILE = Path("output") / "candidate_images" / "manifest.json"
_MODEL         = "google/gemini-3-flash"   # vision model via Vercel AI Gateway

_ANALYSIS_PROMPT = """Analyze this news photo for social media post editing. Return ONLY valid JSON.

{
  "quality_score": <float 1.0-10.0, based on sharpness, lighting, composition, resolution>,
  "resolution_ok": <true if image is ≥ 800px wide, else false>,
  "faces": {
    "count": <int>,
    "positions": [<"top-left"|"top-center"|"top-right"|"center-left"|"center"|"center-right"|"bottom-left"|"bottom-center"|"bottom-right">],
    "size": <"dominant (>50%)" | "medium (20-50%)" | "small (<20%)" | "none">
  },
  "clear_areas": [
    {
      "zone": <"top-left"|"top-center"|"top-right"|"left-strip"|"right-strip"|"bottom-band"|"center-overlay">,
      "size_pct": <estimated % of frame this clear zone occupies>,
      "usable_for_text": <true|false>
    }
  ],
  "dominant_colors": [<"#rrggbb">, <"#rrggbb">, <"#rrggbb">],
  "background": <"plain"|"simple"|"moderate"|"busy"|"very_busy">,
  "objects": [<string: main recognizable objects, people, locations visible>],
  "has_foreign_branding": <true if visible logos, chyrons, or text from other news outlets>,
  "text_safe_zones": [<best zones for placing headline text, e.g., "top-left 35% sky area">],
  "editing_recommendation": "<1-2 sentence creative suggestion: which zone for headline, gradient style, color to use from the image palette>"
}

Be precise about clear areas — the social media editor NEEDS to know exactly where text can be placed without covering faces or busy backgrounds.
Return ONLY the JSON object, no markdown fences."""


def _load_image_b64(url: str, max_px: int = 800) -> str | None:
    """Load image from disk manifest (or download) and return base64 JPEG."""
    raw = None

    # Try manifest first
    if _MANIFEST_FILE.exists():
        try:
            manifest = json.loads(_MANIFEST_FILE.read_text(encoding="utf-8"))
            fpath = manifest.get(url)
            if fpath and Path(fpath).exists():
                raw = Path(fpath).read_bytes()
        except Exception:
            pass

    # Fallback: download
    if raw is None:
        try:
            r = requests.get(
                url,
                timeout=15,
                headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"},
            )
            r.raise_for_status()
            raw = r.content
        except Exception as e:
            print(f"[analyze_images] Download failed for {url[:60]}: {e}")
            return None

    # Resize to max_px for analysis (smaller = faster API call)
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = img.size
        if max(w, h) > max_px:
            scale = max_px / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"[analyze_images] Image encode failed: {e}")
        return None


def _analyze_single(index: int, url: str) -> dict:
    """Send one image to Gemini Flash for analysis. Called in parallel."""
    result = {
        "index": index,
        "url": url,
        "error": None,
        "specs": None,
    }

    # Load + encode image
    b64 = _load_image_b64(url)
    if not b64:
        result["error"] = "Could not load image"
        return result

    # Call Vercel AI Gateway
    api_key  = os.environ.get("AI_GATEWAY_API_KEY", "")
    base_url = "https://ai-gateway.vercel.sh/v1"

    payload = {
        "model": _MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                    {"type": "text", "text": _ANALYSIS_PROMPT},
                ],
            }
        ],
        "temperature": 0.0,
        "max_tokens": 2048,
    }

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()

        # ── Robust JSON extraction ───────────────────────────────────────────────────────────────────
        import re

        # 1. Strip ```json ... ``` or ``` ... ``` fences
        if "```" in text:
            fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
            if fence:
                text = fence.group(1)
            else:
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)

        # 2. Extract outermost { } block if still not clean
        if not text.startswith("{"):
            brace = re.search(r"\{.*\}", text, re.DOTALL)
            if brace:
                text = brace.group(0)

        specs = json.loads(text)
        result["specs"] = specs
    except json.JSONDecodeError as e:
        result["error"] = f"JSON parse error (response may be truncated): {e} | Raw: {text[:300]}"
        print(f"[analyze_images] Full raw for debug:\n{text[:800]}")
    except Exception as e:
        result["error"] = str(e)

    return result


# ── LangChain Tool ────────────────────────────────────────────────────────────
@tool(parse_docstring=True)
def analyze_images_gemini(image_urls: list[str]) -> str:
    """Analyze up to 5 candidate images in PARALLEL using Gemini Flash vision.

    Sends each image to google/gemini-3-flash simultaneously and returns
    detailed composition specs for each image:
    - Image quality score (1-10)
    - Face count and positions
    - Available clear areas for text placement
    - Dominant colors (hex)
    - Background complexity
    - Whether foreign branding/logos are present
    - Specific text-safe zones with size estimates
    - Creative editing recommendation

    Use this AFTER view_candidate_images to pick your top 3-5 images,
    then call this tool with those URLs to get specs for ALL of them
    in parallel. Then pick the BEST image (highest quality + most text area)
    and craft your editing_prompt using the exact specs returned.

    Args:
        image_urls: List of 2-5 image URLs to analyze in parallel.
                    These must be URLs previously returned by fetch_images_brave
                    and shown in view_candidate_images.

    Returns:
        Structured analysis of each image with quality scores, face positions,
        clear text areas, and editing recommendations. Pick the image with
        highest quality_score + has_foreign_branding=false + largest text_safe_zones.
    """
    urls = image_urls[:5]  # max 5
    if not urls:
        return "No image URLs provided."

    print(f"[analyze_images_gemini] Analyzing {len(urls)} images in parallel via {_MODEL}...")

    results = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_analyze_single, i + 1, url): url for i, url in enumerate(urls)}
        for future in as_completed(futures):
            results.append(future.result())

    # Sort by original index
    results.sort(key=lambda r: r["index"])

    # Format output
    lines = [f"📊 IMAGE ANALYSIS — {len(results)} images analyzed in parallel\n"]
    lines.append("=" * 60)

    for r in results:
        lines.append(f"\n🖼️  Image {r['index']}: {r['url'][:80]}")
        if r["error"]:
            lines.append(f"   ❌ Error: {r['error']}")
            continue

        specs = r["specs"]
        score = specs.get("quality_score", "?")
        branding = specs.get("has_foreign_branding", False)
        faces = specs.get("faces", {})
        clear = specs.get("clear_areas", [])
        colors = specs.get("dominant_colors", [])
        bg = specs.get("background", "?")
        recommendation = specs.get("editing_recommendation", "")
        text_zones = specs.get("text_safe_zones", [])

        brand_tag = "⚠️ HAS FOREIGN BRANDING — REJECT" if branding else "✅ Clean (no foreign branding)"
        lines.append(f"   Quality Score:    {score}/10")
        lines.append(f"   Branding:         {brand_tag}")
        lines.append(f"   Background:       {bg}")
        lines.append(f"   Faces:            {faces.get('count', 0)} face(s) — {faces.get('size', 'none')} — positions: {faces.get('positions', [])}")
        lines.append(f"   Dominant Colors:  {', '.join(colors)}")

        if clear:
            lines.append("   Clear Areas:")
            for zone in clear:
                usable = "✅" if zone.get("usable_for_text") else "❌"
                lines.append(f"     {usable} {zone.get('zone')} — ~{zone.get('size_pct', '?')}% of frame")

        if text_zones:
            lines.append(f"   Best Text Zones:  {' | '.join(text_zones)}")

        if recommendation:
            lines.append(f"   💡 Recommendation: {recommendation}")

    lines.append("\n" + "=" * 60)
    lines.append(
        "\n📌 SELECTION GUIDE:\n"
        "  1. REJECT any image with has_foreign_branding=true\n"
        "  2. Pick highest quality_score among clean images\n"
        "  3. Prefer images with large text_safe_zones\n"
        "  4. Use the 'editing_recommendation' to build your editing_prompt\n"
        "  5. Reference exact color hex codes and zone names in your prompt\n"
        "  6. Then call create_post_image_gemini with the chosen URL and your crafted prompt"
    )

    return "\n".join(lines)
