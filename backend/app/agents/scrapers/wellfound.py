"""
app/agents/scrapers/wellfound.py
──────────────────────────────────
Re-exports WellfoundScraper from linkedin.py for clean imports.
"""
from app.agents.scrapers.linkedin import WellfoundScraper  # noqa

__all__ = ["WellfoundScraper"]
