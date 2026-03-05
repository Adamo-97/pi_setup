# -*- coding: utf-8 -*-
"""
PromptLoader — loads prompt skills from markdown files.

Each .md file in skills/ has two optional sections:
    <!-- SYSTEM -->   (persona / system instruction)
    <!-- USER -->     (the actual task prompt with {variables})

Usage:
    from config.prompts.loader import skill

    # Load full file (both sections joined)
    full = skill("planner")

    # Load just one section
    system = skill("planner", section="system")
    user   = skill("planner", section="user",
                   trending_games=..., remaining_budget=...)

    # Writer variants — one system prompt, separate user files
    system = skill("writer", section="system")
    user   = skill("writer_trending_news", news_data=..., ...)
"""

import re
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent / "skills"


def skill(name: str, section: str | None = None, **kwargs) -> str:
    """
    Load a prompt skill from skills/<name>.md.

    Args:
        name:     Filename without extension (e.g. "planner").
        section:  "system", "user", or None (return full file).
        **kwargs: Template variables — only matching {keys} are replaced.

    Returns:
        Prompt text with declared variables substituted.

    Raises:
        FileNotFoundError: If the skill file does not exist.
        ValueError:        If the requested section is not found.
    """
    path = _SKILLS_DIR / f"{name}.md"
    if not path.exists():
        available = [p.stem for p in _SKILLS_DIR.glob("*.md")]
        raise FileNotFoundError(
            f"Skill '{name}' not found. Available: {available}"
        )
    text = path.read_text(encoding="utf-8")

    if section:
        text = _extract_section(text, section, name)

    if kwargs:
        def _replace(m: re.Match) -> str:
            key = m.group(1)
            return str(kwargs[key]) if key in kwargs else m.group(0)
        text = re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", _replace, text)

    return text.strip()


def _extract_section(text: str, section: str, name: str) -> str:
    """Extract content between <!-- SECTION --> markers."""
    marker = f"<!-- {section.upper()} -->"
    parts = text.split(marker)
    if len(parts) < 2:
        raise ValueError(
            f"Section '{section}' not found in skill '{name}'. "
            f"Expected marker: {marker}"
        )
    content = parts[1]
    # Stop at next section marker if any
    next_marker = re.search(r"<!--\s+\w+\s+-->", content)
    if next_marker:
        content = content[:next_marker.start()]
    return content


def list_skills() -> list:
    """Return names of all available skill files."""
    return sorted(p.stem for p in _SKILLS_DIR.glob("*.md"))
