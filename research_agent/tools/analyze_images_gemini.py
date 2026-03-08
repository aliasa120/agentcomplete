"""Single-call image analyzer + editing-prompt writer using google/gemini-3-flash.

SINGLE CALL FLOW (v3):
1. Receives up to 5 image URLs + social_posts.md content
2. Fires ONE single call to Gemini Flash with ALL images in the same message
3. Gemini sees all images side-by-side and:
   - Picks the BEST image directly (no scoring guesswork)
   - Writes ONE complete editing_prompt for the chosen image
   - Returns quality notes for all images so we know why it picked
"""

import base64
import io
import json
import os
import re
from pathlib import Path

import requests
from langchain_core.tools import tool
from PIL import Image

# ── Config ────────────────────────────────────────────────────────────────────
_MANIFEST_FILE    = Path("output") / "candidate_images" / "manifest.json"
_MODEL            = "google/gemini-3-flash"
_BRAND_STYLE_FILE = Path(__file__).parent.parent.parent / "brand_style.md"

# Load brand style once at module level — fallback if file missing
try:
    _BRAND_STYLE = _BRAND_STYLE_FILE.read_text(encoding="utf-8")
except FileNotFoundError:
    _BRAND_STYLE = (
        "THE ECHO brand: Primary #1A5C5A (teal), Highlight #C9A227 (mustard), "
        "Text #FFFFFF. Watermark: theecho.news.tv bottom-right. "
        "Brand mark: THE ECHO top-left teal badge."
    )
    print(f"[analyze_images] WARNING: brand_style.md not found at {_BRAND_STYLE_FILE}. Using fallback.")

# ── Single-call prompt (all images sent together) ─────────────────────────────
_SINGLE_CALL_PROMPT = """You are THE ECHO news brand image editor.
You are shown {n_images} news photos (labeled Image 1, Image 2, ... Image {n_images}).
Compare them all and pick the SINGLE BEST one for a social media post.

## THE ECHO Brand Style Guide
{brand_style}

## Social Post Content (use this to craft the text layers)
{post_content}

## Your Task
1. Compare all {n_images} images.
2. Reject any with visible logos/chyrons from other news outlets.
3. Pick the best remaining image (highest clarity, most text space, most visually impactful).
4. Write a complete THE ECHO editing prompt for that image.

Return ONLY valid JSON (no markdown fences, no extra text):
{{
  "chosen_image_index": <integer 1-{n_images}>,
  "chosen_image_url": "<the URL of the chosen image>",
  "selection_reason": "<1 sentence: why this image was chosen over the others>",
  "rejected_images": [<list of image index integers that were rejected and why, e.g. {{"index": 2, "reason": "foreign branding"}}]],
  "kicker": "<2-4 words SMALL CAPS — e.g. BREAKING NEWS, MARKET UPDATE, COURT RULING>",
  "headline": "<max 10 words — hook line from the X post above>",
  "spice_line": "<max 15 words — intriguing teaser NOT repeating the headline, from Instagram/Facebook post>",
  "text_safe_zones": ["<precise areas in the chosen image free for text overlay>"],
  "selected_style": "<Style 1|Style 2|Style 3|Style 4|Style 5|Style 6>",
  "editing_prompt": "<COMPLETE ready-to-paste editing prompt: references exact hex colors from brand style, uses the text_safe_zones identified in the chosen image, all 3 text layers (kicker+headline+spice_line) with real text from above, THE ECHO badge top-left, theecho.news.tv watermark bottom-right, ends with preservation sentence from brand style guide>"
}}

Rules:
- chosen_image_url must be the EXACT URL string shown in the image label below
- Use REAL kicker/headline/spice_line from post content — no placeholder text
- editing_prompt must be complete and ready to paste — agent will use it verbatim
"""


def _load_image_b64(url: str, max_px: int = 900) -> str | None:
    """Load image from disk manifest (or download) and return base64 JPEG."""
    raw = None

    if _MANIFEST_FILE.exists():
        try:
            manifest = json.loads(_MANIFEST_FILE.read_text(encoding="utf-8"))
            fpath = manifest.get(url)
            if fpath and Path(fpath).exists():
                raw = Path(fpath).read_bytes()
        except Exception:
            pass

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

    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = img.size
        if max(w, h) > max_px:
            scale = max_px / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"[analyze_images] Image encode failed: {e}")
        return None


# ── LangChain Tool ─────────────────────────────────────────────────────────────
@tool(parse_docstring=True)
def analyze_images_gemini(image_urls: list[str], post_content: str = "") -> str:
    """Send all candidate images in ONE call to Gemini Flash for comparison + editing prompt.

    SINGLE CALL: All images are sent together in one API request.
    Gemini sees all images simultaneously and:
    - Directly picks the BEST image (not just highest score — actual comparison)
    - Rejects any with foreign branding
    - Writes ONE complete, ready-to-paste editing_prompt for the chosen image
    - Extracts kicker, headline, spice_line from your actual post text

    You MUST pass post_content (read_file("/social_posts.md") output) so Gemini
    can derive real text layers from your actual posts.

    Args:
        image_urls: List of 2-5 image URLs to compare. Must be URLs returned by
                    fetch_images_brave and viewed in view_candidate_images.
        post_content: Full text of /social_posts.md. Gemini uses this to extract
                      kicker, headline, spice_line and pick the correct brand style.

    Returns:
        The chosen image URL, selection reason, and a complete editing_prompt
        ready to paste verbatim into create_post_image_gemini.
    """
    urls = image_urls[:5]
    if not urls:
        return "No image URLs provided."

    print(f"[analyze_images_gemini] Loading {len(urls)} images for single Gemini call...")

    # Load all images as base64
    loaded = []
    for i, url in enumerate(urls, start=1):
        b64 = _load_image_b64(url)
        if b64:
            loaded.append({"index": i, "url": url, "b64": b64})
        else:
            print(f"[analyze_images] Skipped Image {i} — could not load: {url[:60]}")

    if not loaded:
        return "Failed to load any images. Check URLs or network connection."

    print(f"[analyze_images_gemini] Sending {len(loaded)} images in ONE call to {_MODEL}...")

    # Build the content array: one image_url block per image, labelled, then text prompt
    content = []
    for item in loaded:
        # Label each image so Gemini can reference them by number and URL
        content.append({
            "type": "text",
            "text": f"Image {item['index']} (URL: {item['url']}):"
        })
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{item['b64']}"}
        })

    # Final instruction text with brand style + post content injected
    prompt_text = _SINGLE_CALL_PROMPT.format(
        n_images=len(loaded),
        brand_style=_BRAND_STYLE,
        post_content=post_content or "(not provided — use generic news kicker/headline/spice)",
    )
    content.append({"type": "text", "text": prompt_text})

    api_key  = os.environ.get("AI_GATEWAY_API_KEY", "")
    base_url = "https://ai-gateway.vercel.sh/v1"

    payload = {
        "model": _MODEL,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.1,
        "max_tokens": 3000,
    }

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()

        # Robust JSON extraction
        if "```" in text:
            fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
            if fence:
                text = fence.group(1)
            else:
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)

        if not text.startswith("{"):
            brace = re.search(r"\{.*\}", text, re.DOTALL)
            if brace:
                text = brace.group(0)

        result = json.loads(text)

    except json.JSONDecodeError as e:
        return f"❌ Gemini returned invalid JSON: {e}\nRaw response (first 500 chars): {text[:500]}"
    except Exception as e:
        return f"❌ API call failed: {e}"

    # Format readable output for the agent
    chosen_idx   = result.get("chosen_image_index", "?")
    chosen_url   = result.get("chosen_image_url", "?")
    reason       = result.get("selection_reason", "")
    rejected     = result.get("rejected_images", [])
    style        = result.get("selected_style", "?")
    kicker       = result.get("kicker", "?")
    headline     = result.get("headline", "?")
    spice        = result.get("spice_line", "?")
    text_zones   = result.get("text_safe_zones", [])
    editing_prompt = result.get("editing_prompt", "")

    lines = [
        f"📊 IMAGE ANALYSIS — {len(loaded)} images compared in ONE Gemini call",
        "=" * 70,
        f"\n✅ CHOSEN: Image {chosen_idx}",
        f"   URL: {chosen_url}",
        f"   Reason: {reason}",
    ]

    if rejected:
        lines.append("\n❌ Rejected images:")
        for r in rejected:
            lines.append(f"   Image {r.get('index', '?')}: {r.get('reason', '?')}")

    lines += [
        f"\n🎨 Style:      {style}",
        f"   Kicker:     {kicker}",
        f"   Headline:   {headline}",
        f"   Spice Line: {spice}",
        f"   Text Zones: {' | '.join(text_zones) if text_zones else 'not specified'}",
        f"\n📋 EDITING PROMPT (paste verbatim into create_post_image_gemini):",
        f"   {editing_prompt}",
        "\n" + "=" * 70,
        "\n📌 NEXT STEP:",
        f"   create_post_image_gemini(",
        f'       image_url="{chosen_url}",',
        f'       headline_text="{headline}",',
        f"       editing_prompt=<editing prompt shown above>",
        f"   )",
    ]

    return "\n".join(lines)
