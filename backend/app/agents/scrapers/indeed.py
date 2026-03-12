"""
app/agents/scrapers/indeed.py
app/agents/scrapers/internshala.py
────────────────────────────────────
Concrete scraper implementations for Indeed and Internshala.
These are the two friendliest platforms to start with (less aggressive anti-bot).
LinkedIn scraper is in linkedin.py (needs cookies/session).
"""

# ═══════════════════════════════════════════════════════════════════════════
#  INDEED SCRAPER
# ═══════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from app.agents.scrapers.base import BaseScraper, ScrapedJob
from app.core.config import settings


class IndeedScraper(BaseScraper):
    """
    Scrapes Indeed job listings.
    Uses Indeed's HTML search pages (no API key needed).
    Rotates User-Agent to reduce detection risk.
    """

    source = "indeed"
    BASE_URL = "https://in.indeed.com"  # India edition; change for other regions

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
    ]

    async def _get_search_queries(self) -> List[Dict[str, Any]]:
        """Build search query combinations from user profile."""
        queries = []
        for role in settings.USER_DESIRED_ROLES:
            for location in settings.USER_DESIRED_LOCATIONS[:3]:  # Top 3 locations
                queries.append({
                    "query": role,
                    "location": location if location.lower() != "remote" else "",
                    "remote": location.lower() == "remote",
                })
        return queries

    async def _scrape_query(self, query_params: Dict) -> List[ScrapedJob]:
        """Scrape one search query across multiple pages."""
        jobs = []
        start = 0
        pages_per_query = 3  # Max pages per search

        import random
        headers = {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30) as client:
            for page in range(pages_per_query):
                url = self._build_url(query_params, start)
                try:
                    response = await client.get(url)
                    if response.status_code == 200:
                        page_jobs = self._parse_page(response.text, query_params)
                        jobs.extend(page_jobs)
                        start += 15  # Indeed shows 15 per page
                        if not page_jobs:
                            break  # No more results
                        await self._sleep()
                    else:
                        self.log.warning(f"Indeed returned {response.status_code}")
                        break
                except Exception as e:
                    self.log.error(f"Indeed page scrape failed", error=str(e))
                    break

        return jobs

    def _build_url(self, params: Dict, start: int) -> str:
        query = params["query"].replace(" ", "+")
        location = params.get("location", "").replace(" ", "+")
        remote_filter = "&remotejob=032b3046-06a3-4876-8dfd-474eb5e7ed11" if params.get("remote") else ""
        return f"{self.BASE_URL}/jobs?q={query}&l={location}&start={start}{remote_filter}&fromage=14"

    def _parse_page(self, html: str, params: Dict) -> List[ScrapedJob]:
        """Parse Indeed search results HTML."""
        soup = BeautifulSoup(html, "lxml")
        jobs = []

        job_cards = soup.find_all("div", class_=re.compile(r"job_seen_beacon|result"))

        for card in job_cards:
            try:
                # Title
                title_el = card.find("h2", class_=re.compile(r"jobTitle")) or \
                           card.find("a", {"data-jk": True})
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)

                # Company
                company_el = card.find("span", {"data-testid": "company-name"}) or \
                             card.find("span", class_="companyName")
                company = company_el.get_text(strip=True) if company_el else "Unknown"

                # Location
                loc_el = card.find("div", {"data-testid": "text-location"}) or \
                         card.find("div", class_=re.compile(r"companyLocation"))
                location = loc_el.get_text(strip=True) if loc_el else params.get("location", "")

                # Job ID and URL
                link = card.find("a", href=re.compile(r"/rc/clk"))
                if not link:
                    link = card.find("a", {"data-jk": True})
                job_id = link.get("data-jk", "") if link else ""
                source_url = f"{self.BASE_URL}/viewjob?jk={job_id}" if job_id else ""

                if not job_id or not source_url:
                    continue

                # Salary
                salary_el = card.find("div", class_=re.compile(r"salary"))
                salary_text = salary_el.get_text(strip=True) if salary_el else ""
                sal_min, sal_max, currency = self._parse_salary(salary_text)

                # Date posted
                date_el = card.find("span", class_=re.compile(r"date|Posted"))
                posted_at = self._parse_posted_date(date_el.get_text(strip=True) if date_el else "")

                work_mode = self._detect_work_mode(location + " " + title)
                job_type = self._detect_job_type(title)

                jobs.append(ScrapedJob(
                    source=self.source,
                    source_job_id=job_id,
                    source_url=source_url,
                    title=title,
                    company_name=company,
                    location=location,
                    work_mode=work_mode,
                    job_type=job_type,
                    salary_min=sal_min,
                    salary_max=sal_max,
                    salary_currency=currency or "INR",
                    posted_at=posted_at,
                ))
            except Exception as e:
                self.log.warning("Failed to parse job card", error=str(e))

        return jobs

    def _parse_posted_date(self, text: str) -> Optional[datetime]:
        """Convert 'Posted 3 days ago' → datetime."""
        now = datetime.now(timezone.utc)
        text = text.lower()
        if "today" in text or "just posted" in text:
            return now
        if "yesterday" in text:
            return now - timedelta(days=1)
        match = re.search(r"(\d+)\s*day", text)
        if match:
            return now - timedelta(days=int(match.group(1)))
        return None


# ═══════════════════════════════════════════════════════════════════════════
#  INTERNSHALA SCRAPER
# ═══════════════════════════════════════════════════════════════════════════

class IntershalaScraper(BaseScraper):
    """
    Scrapes Internshala for internship listings.
    Internshala is India's largest internship platform.
    Uses their search pages — no authentication required for listings.
    """

    source = "internshala"
    BASE_URL = "https://internshala.com"

    async def _get_search_queries(self) -> List[Dict[str, Any]]:
        queries = []
        # Generate search categories based on user's desired roles
        role_to_category = {
            "computer vision": "computer-vision",
            "machine learning": "machine-learning",
            "deep learning": "deep-learning",
            "data science": "data-science",
            "artificial intelligence": "artificial-intelligence",
            "python": "python",
            "nlp": "natural-language-processing",
            "mlops": "machine-learning",
        }
        for role in settings.USER_DESIRED_ROLES:
            category = None
            for key, cat in role_to_category.items():
                if key in role.lower():
                    category = cat
                    break
            if not category:
                category = role.lower().replace(" ", "-")
            queries.append({"category": category, "original_role": role})

        # Also add general AI/ML search
        queries.append({"category": "machine-learning", "original_role": "ML"})
        return queries

    async def _scrape_query(self, query_params: Dict) -> List[ScrapedJob]:
        """Scrape Internshala listings for a category."""
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
                    jobs = self._parse_internshala_page(response.text, category)
                else:
                    self.log.warning(f"Internshala returned {response.status_code} for {category}")
            except Exception as e:
                self.log.error(f"Internshala scrape failed", error=str(e))

        return jobs

    def _parse_internshala_page(self, html: str, category: str) -> List[ScrapedJob]:
        """Parse Internshala search results."""
        soup = BeautifulSoup(html, "lxml")
        jobs = []

        # Internshala uses data attributes on internship containers
        cards = soup.find_all("div", class_=re.compile(r"internship_meta|individual_internship"))

        for card in cards:
            try:
                # Title
                title_el = card.find("h3", class_=re.compile(r"profile|job-internship-name")) or \
                           card.find("a", class_=re.compile(r"profile"))
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)

                # Company
                company_el = card.find("p", class_=re.compile(r"company_name")) or \
                             card.find("a", class_=re.compile(r"company-name"))
                company = company_el.get_text(strip=True) if company_el else "Unknown"

                # Location
                loc_els = card.find_all("a", class_=re.compile(r"location_link")) or \
                          card.find_all("span", class_=re.compile(r"location"))
                location = ", ".join(el.get_text(strip=True) for el in loc_els)

                # Stipend
                stipend_el = card.find("span", class_=re.compile(r"stipend|salary"))
                stipend_text = stipend_el.get_text(strip=True) if stipend_el else ""
                sal_min, sal_max, currency = self._parse_salary(stipend_text)

                # Duration (internship-specific)
                duration_el = card.find("div", class_=re.compile(r"internship-other-details"))
                duration = duration_el.get_text(strip=True) if duration_el else ""

                # Job ID from link
                link_el = card.find("a", href=re.compile(r"/internships/detail"))
                if not link_el:
                    link_el = card.find("a", href=re.compile(r"/internship/"))
                source_url = self.BASE_URL + link_el["href"] if link_el else ""
                job_id = source_url.split("/")[-1] if source_url else ""

                if not job_id:
                    # Try data attribute
                    job_id = card.get("internshipid") or card.get("data-internship-id", "")

                if not job_id:
                    continue

                # Remote detection
                work_mode = "remote" if "work from home" in location.lower() or \
                            "remote" in location.lower() else "onsite"

                jobs.append(ScrapedJob(
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
                    easy_apply=True,  # Internshala has easy apply
                ))
            except Exception as e:
                self.log.warning("Failed to parse Internshala card", error=str(e))

        return jobs
