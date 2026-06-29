"""Loads the domain-specific knowledge base slice.

KB files are pre-sliced per domain at the file level (spec section 9), so only
the relevant slice ever enters the prompt. Pure file I/O, no LLM.
"""

import os

from app.config import DOMAIN_TO_KB_FILE

# Project root = parent of the app/ package directory.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_kb_slice(domain: str) -> str:
    """Return the KB text for a domain.

    The per-domain files start with a `==domain==` header line, which is
    stripped since the format/grounding instructions live in the system prompt.
    """
    rel_path = DOMAIN_TO_KB_FILE.get(domain)
    if rel_path is None:
        raise ValueError(f"No knowledge base configured for domain: {domain!r}")

    abs_path = os.path.join(_PROJECT_ROOT, rel_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"Knowledge base file not found: {abs_path}")

    with open(abs_path, "r", encoding="utf-8") as f:
        text = f.read().strip()

    # Drop a leading `==domain==` marker line if present.
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("==") and lines[0].strip().endswith("=="):
        lines = lines[1:]

    return "\n".join(lines).strip()
