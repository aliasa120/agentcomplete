---
name: gemini-image-editing
description: Use when creating the social post image after writing posts. Covers fetch_images_brave, view_candidate_images, analyze_images_gemini (NEW — pass post_content), create_post_image_gemini. Gemini writes the complete editing prompt from seeing image + post text together. Trigger keywords: image, photo, visual, create image, brand image, THE ECHO image, news photo, editing prompt.
---

# Gemini Image Editing Skill

## Critical Constraints (Read First)

- **Run ONLY after `/social_posts.md` is written and verified**
- **Skip entire pipeline gracefully if `fetch_images_brave` returns no results**
- **Always pass `post_content`** to `analyze_images_gemini` — read `/social_posts.md` first with `read_file()`
- **Do NOT write the editing prompt yourself** — use the `editing_prompt` that Gemini returns
- **Use the recommended image** — pick the image with highest `quality_score` + `has_foreign_branding=false`

---

## THE ECHO Brand Identity (for reference only — Gemini handles the prompt)

| Element | Value |
|---|---|
| Brand name | **THE ECHO** |
| Watermark | `theecho.news.tv` |
| Primary | Deep Teal `#1A5C5A` |
| Highlight | Warm Mustard `#C9A227` |
| Text | White `#FFFFFF` |
| Dark card | `#0D1F1E` |
| Brand mark position | Top-left — `THE ECHO` wordmark on small teal badge |
| Watermark position | Bottom-right — `theecho.news.tv` in small mustard text |

---

## Pipeline: 5 Steps

### Step A — Read Post Content
```python
post_content = read_file("/social_posts.md")
```
You MUST do this before calling `analyze_images_gemini`. This is what gives Gemini the context to write accurate kicker/headline/spice_line text layers.

---

### Step B — Fetch Candidates
```python
fetch_images_brave(query="[same keyword query from research — be specific]")
```
Returns up to 10 image URLs. If empty → stop, skip entire pipeline gracefully.

---

### Step C — View Thumbnails
```python
view_candidate_images(image_urls=["url1", "url2", ...])
```
Pass ALL URLs. Shows 200px thumbnails. For each:
- ✅ Keep: clean photo, well-lit, no foreign news logos or chyrons
- ❌ Reject: another channel's watermark, text overlay from other brands, low resolution, blurry

Pick your **top 3–5** clean ones.

---

### Step D — Analyse with Gemini Vision (NEW — pass post_content)

```python
analyze_images_gemini(
    image_urls=["top-pick-1", "top-pick-2", "top-pick-3"],
    post_content=post_content   # ← pass the social_posts.md text here
)
```

**What Gemini returns per image:**
- `quality_score` (0–10), `has_foreign_branding` (true/false)
- `text_safe_zones` — exact areas free for text overlay
- `selected_style` — which of Style 1–6 fits this news type
- `kicker`, `headline`, `spice_line` — derived from your actual post text
- **`editing_prompt`** — complete, ready-to-paste editing prompt for `create_post_image_gemini`

**Selection rule:** Use the `editing_prompt` from the image with the **highest `quality_score`** and **`has_foreign_branding=false`**.

---

### Step E — Create Branded Image

```python
create_post_image_gemini(
    image_url="[best image URL from Step D]",
    headline_text="[headline from Step D analysis — max 10 words]",
    editing_prompt="[editing_prompt from Step D analysis — paste verbatim]"
)
```

Output: `output/social_post.jpg`

Then append to `/social_posts.md` under `## Images`:
```
## Images
- output/social_post.jpg
```

---

## Style Reference (Gemini selects automatically — no action needed from agent)

| News Type | Style | Visual Feel |
|---|---|---|
| Breaking / Hard News / Political | **Style 1 — Gritty Ground-Level** | Real photo + gradient bottom, white serif headline |
| Quote / Interview / Controversy | **Style 2 — Portrait Gradient** | Close-up face, dark gradient, bold sans, mustard highlights |
| Feature / Natural / Science | **Style 3 — Clean Container** | Wide cinematic, white/teal rounded text block at bottom |
| Tabloid / Geo-political Drama | **Style 4 — Composite Dramatic** | Bold all-caps, yellow/red highlights, distressed textures |
| Tech / Environment / Niche | **Style 5 — Cinematic Branded** | High-angle shot, black text block, single teal accent bar |
| Disaster / Grief / Humanitarian | **Style 6 — Immersive Dark Band** | Dark teal bands top+bottom, white serif centered, sombre |

---

## Text Layers Reference (Gemini writes these from your post — no action needed)

| Layer | Length | Purpose |
|---|---|---|
| **KICKER** | 2–4 words, small caps | Category label e.g. `BREAKING NEWS`, `COURT RULING` |
| **HEADLINE** | max 10 words, bold | Hook line from your X post |
| **SPICE LINE** | max 15 words, italic | Intriguing teaser — NOT a repeat of the headline |

---

## If Pipeline Fails

| Failure | Action |
|---|---|
| `fetch_images_brave` returns empty | Log "No images found", skip pipeline, proceed to Step 6 Verification |
| All images have `has_foreign_branding=true` | Log "All images branded", skip pipeline |
| `create_post_image_gemini` fails | Log the error, skip — do not retry more than once |
