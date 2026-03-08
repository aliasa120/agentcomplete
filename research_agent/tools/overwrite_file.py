"""Thread-isolated file overwrite tool.

Writes news_input.md and social_posts.md to a per-thread subdirectory so that
parallel LangGraph runs (e.g. 3 articles processed simultaneously) never
overwrite each other's files.

Path layout:
    <project_root>/threads/<thread_id>/news_input.md
    <project_root>/threads/<thread_id>/social_posts.md

The agent always references files as "/news_input.md" or "/social_posts.md"
(virtual paths) — this tool resolves them to the thread-scoped real path.
"""

import os
from pathlib import Path

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

# Allowed filenames — nothing else may be written via this tool.
_ALLOWED = {"news_input.md", "social_posts.md"}

# Project root is two levels up from this file:
#   research_agent/tools/overwrite_file.py  →  <project_root>
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@tool
def overwrite_file(file_path: str, content: str, config: RunnableConfig) -> str:
    """Write content to a file, completely overwriting it if it already exists.

    Use this to save /news_input.md (Step 1) and /social_posts.md (Step 4).
    Each parallel run writes to its own isolated directory so concurrent
    articles never collide.

    Args:
        file_path: Virtual path to write to — e.g. "/news_input.md" or "/social_posts.md".
        content: Full content to write (replaces any existing content).
    """
    filename = os.path.basename(file_path)

    if filename not in _ALLOWED:
        return (
            f"Error: overwrite_file only supports {sorted(_ALLOWED)}. "
            f"Cannot write to '{filename}'."
        )

    # Extract the LangGraph thread_id from the injected config.
    # Falls back to "default" so local / notebook runs still work.
    configurable = config.get("configurable", {}) if config else {}
    thread_id: str = configurable.get("thread_id", "default")

    # Build a thread-scoped directory: <project_root>/threads/<thread_id>/
    thread_dir = _PROJECT_ROOT / "threads" / thread_id
    thread_dir.mkdir(parents=True, exist_ok=True)

    abs_path = thread_dir / filename

    try:
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote {filename} → {abs_path}"
    except Exception as e:
        return f"Error writing file: {e}"
