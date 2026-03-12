"""
app/agents/scrapers/internshala.py
────────────────────────────────────
Re-exports IntershalaScraper from indeed.py for clean imports.
"""
from app.agents.scrapers.indeed import IntershalaScraper  # noqa

__all__ = ["IntershalaScraper"]
