---
name: todo-list
description: Use throughout the research loop to track status of each research target after every search and extract step. Maintain a running checklist: Complete, Partially Complete, or Not Found. Trigger keywords: target status, checklist, tracking, complete, partial, not found.
---

# Todo List Skill

## Critical Constraints (Read First)

- **Update after EVERY tool call** — never skip an update
- **Copy target descriptions exactly** — never paraphrase
- **Trigger early exit immediately** when all targets are Complete
- **Be honest** — Partially Complete ≠ Complete; do not round up

---

## Status Definitions

| Status | Criteria |
|---|---|
| ✅ **Complete** | Specific fact or direct quote + at least 1 credible source URL |
| ⚠️ **Partially Complete** | Some info found but key detail missing, or only a weak/uncredible source |
| ❌ **Not Found** | No relevant information after all searches attempted |

**Credible sources:** Dawn, Geo TV, Al Jazeera, Reuters, BBC, ARY News, The News, Tribune, Express Tribune

---

## Checklist Format

Use this exactly inside every `think_tool` reflection:

```
TARGET STATUS UPDATE
====================
Target 1: [copy exact description from /news_input.md]
  Status: ✅ Complete / ⚠️ Partially Complete / ❌ Not Found
  Found:  [specific facts, quotes, dates found]
  Source: [URL or outlet name]
  Missing: [what is still needed, if any]

Target 2: [copy exact description]
  Status: ...
  Found:  ...
  Source: ...
  Missing: ...

[repeat for all targets]

OVERALL: [X] of [Y] targets Complete
DECISION: Continue searching / Extract URLs / Early exit
```

---

## Completion Criteria — Examples

**Complete ✅:**
> "Found Naqvi's exact quote 'the exam was conducted by an independent team' from Dawn News press conference report dated March 5"

**Partially Complete ⚠️:**
> "Found mention TTAP rejected Naqvi's account, but no direct quote from TTAP spokesperson. Geo TV snippet hints at full statement — worth extracting"

**Not Found ❌:**
> "No mention of Aleema Khan's specific statement in any result after 2 searches targeting it"

---

## Early Exit Trigger

When all targets are ✅ Complete:
- Stop immediately — do not run remaining search rounds
- Do not run `tavily_extract` if not already needed
- Proceed directly to the synthesizing skill
