"""Deep Research Agent Example.

This module demonstrates building a research agent using the deepagents package
with custom tools for web search and strategic thinking.
"""

from research_agent.prompts import (
    RESEARCHER_INSTRUCTIONS,
    NEWS_TO_SOCIAL_WORKFLOW_INSTRUCTIONS,
    SUBAGENT_DELEGATION_INSTRUCTIONS,
)

__all__ = [
    "RESEARCHER_INSTRUCTIONS",
    "NEWS_TO_SOCIAL_WORKFLOW_INSTRUCTIONS",
    "SUBAGENT_DELEGATION_INSTRUCTIONS",
]
