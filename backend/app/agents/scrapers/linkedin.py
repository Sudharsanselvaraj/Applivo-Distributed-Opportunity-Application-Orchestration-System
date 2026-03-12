"""
app/agents/scrapers/linkedin.py
app/agents/scrapers/wellfound.py
──────────────────────────────────
LinkedIn and Wellfound scrapers.
LinkedIn requires session cookies (login first, then copy cookies).
Wellfound uses their public search pages.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from app.agents.scrapers.base import BaseScraper, ScrapedJob
from app.core.config import settings


# ═══════════════════════════════════════════════════════════════════════════
#  LINKEDIN SCRAPER
# ═══════════════════════════════════════════════════════════════════════════

class LinkedInScraper(BaseScraper):
    """
    Scrapes LinkedIn job listings.
    Uses LinkedIn's public job search (no login required for basic listings).
    For full details, session cookies improve access.
    """

    source = "linkedin"
    BASE_URL = "https://www.linkedin.com"

    async def _get_search_queries(self) -> List[Dict[str, Any]]:
        queries = []
        for role in settings.USER_DESIRED_ROLES:
            for location in settings.USER_DESIRED_LOCATIONS[:3]:
                queries.append({
                    "keywords": role,
                    "location": location,
                    "f_WT": "2" if location.lower() == "remote" else "",  # Remote filter
                    "f_TPR": "r604800",  # Posted in last 7 days
                })
        return queries

    async def _scrape_query(self, query_params: Dict) -> List[ScrapedJob]:
        jobs = []
        start = 0
        pages = 3

        keywords = query_params["keywords"].replace(" ", "%20")
        location = query_params.get("location", "").replace(" ", "%20")

        import random
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }

        # Add session cookie if available
        cookies = {}
        if settings.LINKEDIN_EMAIL:
            cookies["li_at"] = getattr(settings, "LINKEDIN_SESSION_COOKIE", "")

        async with httpx.AsyncClient(headers=headers, cookies=cookies, follow_redirects=True, timeout=30) as client:
            for page in range(pages):
                url = (
                    f"{self.BASE_URL}/jobs/search?"
                    f"keywords={keywords}&location={location}"
                    f"&start={start}&f_TPR=r604800"
                )
                if query_params.get("f_WT"):
                    url += f"&f_WT={query_params['f_WT']}"

                try:
                    response = await client.get(url)
                    if response.status_code == 200:
                        page_jobs = self._parse_linkedin_page(response.text)
                        jobs.extend(page_jobs)
                        start += 25
                        if not page_jobs:
                            break
                        await self._sleep()
                    elif response.status_code == 429:
                        self.log.warning("LinkedIn rate limited, backing off")
                        await self._sleep(extra=30.0)
                        break
                    else:
                        break
                except Exception as e:
                    self.log.error("LinkedIn page failed", error=str(e))
                    break

        return jobs

    def _parse_linkedin_page(self, html: str) -> List[ScrapedJob]:
        """Parse LinkedIn search results HTML."""
        soup = BeautifulSoup(html, "lxml")
        jobs = []

        cards = soup.find_all("div", class_=re.compile(r"job-search-card|base-card"))

        for card in cards:
            try:
                # Title
                title_el = (
                    card.find("h3", class_=re.compile(r"job-search-card__title|base-search-card__title")) or
                    card.find("a", class_=re.compile(r"job-card-list__title"))
                )
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)

                # Company
                company_el = card.find("h4", class_=re.compile(r"base-search-card__subtitle"))
                company = company_el.get_text(strip=True) if company_el else "Unknown"

                # Location
                loc_el = card.find("span", class_=re.compile(r"job-search-card__location"))
                location = loc_el.get_text(strip=True) if loc_el else ""

                # Job ID from link
                link_el = card.find("a", href=re.compile(r"/jobs/view/"))
                if not link_el:
                    continue
                href = link_el.get("href", "")
                job_id_match = re.search(r"/jobs/view/(\d+)", href)
                if not job_id_match:
                    continue
                job_id = job_id_match.group(1)
                source_url = f"{self.BASE_URL}/jobs/view/{job_id}/"

                # Logo
                img_el = card.find("img", class_=re.compile(r"artdeco-entity-image"))
                logo_url = img_el.get("data-delayed-url") if img_el else None

                # Applicant count
                count_el = card.find("span", class_=re.compile(r"job-search-card__applicant-count"))
                applicant_count = None
                if count_el:
                    match = re.search(r"(\d+)", count_el.get_text())
                    if match:
                        applicant_count = int(match.group(1))

                # Posted date
                date_el = card.find("time")
                posted_at = None
                if date_el:
                    datetime_str = date_el.get("datetime")
                    if datetime_str:
                        try:
                            posted_at = datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
                        except ValueError:
                            pass

                work_mode = self._detect_work_mode(location + " " + title)
                job_type = self._detect_job_type(title)

                jobs.append(ScrapedJob(
                    source=self.source,
                    source_job_id=f"li_{job_id}",
                    source_url=source_url,
                    title=title,
                    company_name=company,
                    location=location,
                    work_mode=work_mode,
                    job_type=job_type,
                    posted_at=posted_at,
                    applicant_count=applicant_count,
                    company_logo_url=logo_url,
                    easy_apply=False,  # Check on detail page
                ))
            except Exception as e:
                self.log.warning("LinkedIn card parse failed", error=str(e))

        return jobs


# ═══════════════════════════════════════════════════════════════════════════
#  WELLFOUND SCRAPER
# ═══════════════════════════════════════════════════════════════════════════

class WellfoundScraper(BaseScraper):
    """
    Scrapes Wellfound (formerly AngelList Talent) for startup jobs.
    Great source for AI/ML roles at startups.
    """

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
                    jobs = self._parse_wellfound_page(response.text, role)
            except Exception as e:
                self.log.error("Wellfound scrape failed", error=str(e))

        return jobs

    def _parse_wellfound_page(self, html: str, role: str) -> List[ScrapedJob]:
        soup = BeautifulSoup(html, "lxml")
        jobs = []

        # Wellfound job cards
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

                jobs.append(ScrapedJob(
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
                ))
            except Exception as e:
                self.log.warning("Wellfound card parse failed", error=str(e))

        return jobs
