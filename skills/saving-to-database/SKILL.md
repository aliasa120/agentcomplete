---
name: saving-to-database
description: Use as the mandatory last step of every run after social_posts.md is written. Calls save_posts_to_supabase to save all three platform posts and the image to Supabase so the web UI displays them. Trigger keywords: save database, supabase, save posts, final step, database upload, web UI, persist data.
---

# Saving to Database Skill

## Critical Constraints (Read First)

- **This is the LAST action of every single run** — no exceptions
- **Never skip** — skipping means the web UI never updates
- **Run verification checklist before calling** — do not save broken posts

---

## Verification Checklist (Run Before Calling)

```
PRE-SAVE CHECKLIST
==================
[ ] /social_posts.md exists and is not empty
[ ] X post is complete and ≤ 280 characters
[ ] Instagram post has: first line hook, emojis, engagement question, hashtags
[ ] Facebook post is 100–250 words, balanced view, includes at least 1 quote
[ ] All [1] [2] [3] citations in Sources section correspond to real URLs
[ ] No hallucinated facts (if unsure, recheck /news_input.md against posts)
[ ] Tone is neutral and factual — no editorialising
[ ] output/social_post.jpg path listed under ## Images (if image pipeline ran)
```

Only proceed after all boxes are checked.

---

## How to Call

```python
save_posts_to_supabase()
```

No arguments needed. The tool automatically reads `/social_posts.md` and `output/social_post.jpg` from the filesystem.

---

## What the Tool Does

1. Parses `/social_posts.md` into X, Instagram, and Facebook fields
2. Uploads `output/social_post.jpg` to Supabase Storage (if the file exists)
3. Inserts a row into the `social_posts` table
4. Returns a confirmation with the database row ID

---

## After Calling

The tool returns a confirmation with a database row ID. This means:
- Post is saved ✅
- Image is uploaded ✅ (if applicable)
- Web UI at `/posts` will display the new entry

**The workflow is now complete.** Do not call any further tools.

---

## If the Call Fails

1. Check that `/social_posts.md` exists with `read_file("/social_posts.md")`
2. Check that the file format matches the required template (see prompts.py)
3. Retry `save_posts_to_supabase()` once
4. If it fails again — report the error and stop; do not retry infinitely
