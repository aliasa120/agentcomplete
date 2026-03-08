"""Research Agent - Standalone script for LangGraph deployment.

This module creates a single self-searching research agent that performs both
orchestration (gap analysis, file I/O, synthesis, post writing) and web research
(linkup_search, think_tool) without delegating to any sub-agent.
"""

import os
from datetime import datetime
from pathlib import Path

from langchain_openai import ChatOpenAI
from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend

from research_agent.prompts import MAIN_AGENT_INSTRUCTIONS
from research_agent.tools import (
    create_post_image_gemini,
    fetch_images_brave,
    linkup_search,
    overwrite_file,
    tavily_extract,
    think_tool,
    view_candidate_images,
    analyze_images_gemini,
)
from research_agent.tools.save_to_supabase import save_posts_to_supabase

# Inject today's date into the unified prompt
INSTRUCTIONS = MAIN_AGENT_INSTRUCTIONS.format(date=datetime.now().strftime("%Y-%m-%d"))

# Model: configured via environment variables
model = ChatOpenAI(
    model="minimax/minimax-m2.5",
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url=os.environ.get("OPENAI_BASE_URL", "http://47.82.173.134:4000"),
    temperature=0.45,
)

# Use FilesystemBackend so the agent's read_file tool and SkillsMiddleware can
# resolve virtual paths to real files on disk:
#   /skills/planning/SKILL.md  →  <project_root>/skills/planning/SKILL.md
#
# NOTE: news_input.md and social_posts.md are written via the custom overwrite_file
# tool (research_agent/tools/overwrite_file.py), which uses the LangGraph thread_id
# from RunnableConfig to write each run's files to an isolated subdirectory:
#   /news_input.md   →  <project_root>/threads/<thread_id>/news_input.md
#   /social_posts.md →  <project_root>/threads/<thread_id>/social_posts.md
# This prevents parallel runs from overwriting each other's files.
_PROJECT_ROOT = Path(__file__).parent
backend = FilesystemBackend(root_dir=_PROJECT_ROOT, virtual_mode=True)

# Create the single agent — skills loaded from ./skills/
agent = create_deep_agent(
    model=model,
    backend=backend,
    skills=["/skills/"],
    tools=[
        linkup_search,
        think_tool,
        tavily_extract,
        fetch_images_brave,
        view_candidate_images,
        analyze_images_gemini,
        create_post_image_gemini,
        overwrite_file,
        save_posts_to_supabase,
    ],
    system_prompt=INSTRUCTIONS,
)
