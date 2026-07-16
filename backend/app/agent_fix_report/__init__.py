"""Agent fix report package — build advanced Markdown briefs for coding agents."""

from .build import build_agent_fix_markdown
from .playbooks import PLAYBOOKS

__all__ = ["PLAYBOOKS", "build_agent_fix_markdown"]
