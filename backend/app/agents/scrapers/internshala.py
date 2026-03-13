"""
app/agents/scrapers/internshala.py
────────────────────────────────────
Internshala scraper — India's largest internship platform.
No authentication required for public listings.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from app.agents.scrapers.base import BaseScraper, ScrapedJob
from app.core.config import settings


class IntershalaScraper(BaseScraper):
    """
    Scrapes Internshala for internship listings.
    Uses their public search pages — no authentication required.
    """

    source = "internshala"
    BASE_URL = "https://internshala.com"

    ROLE_TO_CATEGORY: Dict[str, str] = {
        "computer vision": "computer-vision",
        "machine learning": "machine-learning",
        "deep learning": "deep-learning",
        "data science": "data-science",
        "artificial intelligence": "artificial-intelligence",
        "python": "python",
        "nlp": "natural-language-processing",
        "mlops": "machine-learning",
        "data analyst": "data-science",
    }

    async def _get_search_queries(self) -> List[Dict[str, Any]]:
        queries = []
        for role in settings.USER_DESIRED_ROLES:
            category = None
            for key, cat in self.ROLE_TO_CATEGORY.items():
                if key in role.lower():
                    category = cat
                    break
            if not category:
                category = role.lower().replace(" ", "-")
            queries.append({"category": category, "original_role": role})

        # Always include general ML search
        queries.append({"category": "machine-learning", "original_role": "ML"})
        return queries

    async def _scrape_query(self, query_params: Dict) -> List[ScrapedJob]:
        jobs = []
        category = query_params["category"]
        url = f"{self.BASE_URL}/internships/{category}-internship"

        import random
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            "Accept": "text/html",
        }

        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30) as client:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    jobs = self._parse_page(response.text, category)
                else:
                    self.log.warning(
                        f"Internshala returned {response.status_code}",
                        category=category,
                    )
            except Exception as e:
                self.log.error("Internshala scrape failed", error=str(e))

        return jobs

    def _parse_page(self, html: str, category: str) -> List[ScrapedJob]:
        soup = BeautifulSoup(html, "lxml")
        jobs = []

        cards = soup.find_all(
            "div",
            class_=re.compile(r"internship_meta|individual_internship"),
        )

        for card in cards:
            try:
                title_el = (
                    card.find("h3", class_=re.compile(r"profile|job-internship-name"))
                    or card.find("a", class_=re.compile(r"profile"))
                )
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)

                company_el = (
                    card.find("p", class_=re.compile(r"company_name"))
                    or card.find("a", class_=re.compile(r"company-name"))
                )
                company = company_el.get_text(strip=True) if company_el else "Unknown"

                loc_els = card.find_all(
                    "a", class_=re.compile(r"location_link")
                ) or card.find_all("span", class_=re.compile(r"location"))
                location = ", ".join(el.get_text(strip=True) for el in loc_els)

                stipend_el = card.find("span", class_=re.compile(r"stipend|salary"))
                stipend_text = stipend_el.get_text(strip=True) if stipend_el else ""
                sal_min, sal_max, currency = self._parse_salary(stipend_text)

                link_el = card.find(
                    "a", href=re.compile(r"/internships/detail|/internship/")
                )
                source_url = self.BASE_URL + link_el["href"] if link_el else ""
                job_id = source_url.split("/")[-1] if source_url else ""

                if not job_id:
                    job_id = (
                        card.get("internshipid")
                        or card.get("data-internship-id", "")
                    )

                if not job_id:
                    continue

                work_mode = (
                    "remote"
                    if "work from home" in location.lower() or "remote" in location.lower()
                    else "onsite"
                )

                jobs.append(
                    ScrapedJob(
                        source=self.source,
                        source_job_id=f"internshala_{job_id}",
                        source_url=source_url,
                        title=title,
                        company_name=company,
                        location=location,
                        work_mode=work_mode,
                        job_type="internship",
                        salary_min=sal_min,
                        salary_max=sal_max,
                        salary_currency=currency or "INR",
                        posted_at=datetime.now(timezone.utc),
                        easy_apply=True,
                    )
                )
            except Exception as e:
                self.log.warning("Failed to parse Internshala card", error=str(e))

        return jobs


__all__ = ["IntershalaScraper"]