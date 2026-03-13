"""
app/agents/scrapers/wellfound.py
──────────────────────────────────
Wellfound (formerly AngelList Talent) scraper.
Great source for AI/ML roles at startups.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from app.agents.scrapers.base import BaseScraper, ScrapedJob


class WellfoundScraper(BaseScraper):

    source = "wellfound"
    BASE_URL = "https://wellfound.com"

    async def _get_search_queries(self) -> List[Dict[str, Any]]:
        return [
            {"role": "machine-learning-engineer", "remote": True},
            {"role": "artificial-intelligence-engineer", "remote": True},
            {"role": "computer-vision-engineer", "remote": False},
            {"role": "data-scientist", "remote": True},
        ]

    async def _scrape_query(self, query_params: Dict) -> List[ScrapedJob]:
        jobs = []
        role = query_params["role"]
        url = f"{self.BASE_URL}/role/{role}"
        if query_params.get("remote"):
            url += "?remote=true"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            "Accept": "text/html",
        }

        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30) as client:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    jobs = self._parse_page(response.text, role)
            except Exception as e:
                self.log.error("Wellfound scrape failed", error=str(e))

        return jobs

    def _parse_page(self, html: str, role: str) -> List[ScrapedJob]:
        soup = BeautifulSoup(html, "lxml")
        jobs = []

        cards = soup.find_all("div", class_=re.compile(r"styles_component|job-listing"))

        for card in cards:
            try:
                title_el = card.find("a", class_=re.compile(r"jobTitle|role-title"))
                if not title_el:
                    title_el = card.find("h2") or card.find("h3")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)

                company_el = card.find("a", class_=re.compile(r"startup-link|company"))
                company = company_el.get_text(strip=True) if company_el else "Startup"

                location_el = card.find("span", class_=re.compile(r"location|remote"))
                location = location_el.get_text(strip=True) if location_el else "Remote"

                link_el = card.find("a", href=re.compile(r"/jobs/"))
                if not link_el:
                    continue
                href = link_el.get("href", "")
                source_url = self.BASE_URL + href if href.startswith("/") else href
                job_id = href.split("/")[-1] or href.replace("/", "_")

                salary_el = card.find("span", class_=re.compile(r"salary|compensation"))
                sal_min, sal_max, currency = self._parse_salary(
                    salary_el.get_text(strip=True) if salary_el else ""
                )

                jobs.append(
                    ScrapedJob(
                        source=self.source,
                        source_job_id=f"wf_{job_id}",
                        source_url=source_url,
                        title=title,
                        company_name=company,
                        location=location,
                        work_mode=self._detect_work_mode(location),
                        job_type=self._detect_job_type(title),
                        salary_min=sal_min,
                        salary_max=sal_max,
                        salary_currency=currency or "USD",
                        posted_at=datetime.now(timezone.utc),
                    )
                )
            except Exception as e:
                self.log.warning("Wellfound card parse failed", error=str(e))

        return jobs


__all__ = ["WellfoundScraper"]