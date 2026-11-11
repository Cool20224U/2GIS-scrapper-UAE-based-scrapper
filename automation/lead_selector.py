"""Automation helpers for generating unique Abu Dhabi business leads.

This module fetches business listings from the 2GIS catalog API, filters
and deduplicates them, and emits a list of email-ready lead records.
It is designed to be executed from an n8n "Execute Command" node.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import json
import os
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set

import requests

DGIS_ITEMS_URL = "https://catalog.api.2gis.com/3.0/items"
DEFAULT_REGION_ID = "70000001017325107"  # Abu Dhabi region identifier in 2GIS
DEFAULT_LIMIT = 49
DEFAULT_PAGE_SIZE = 50

# Keywords that indicate an IT systems integrator or closely related company.
EXCLUDED_KEYWORDS = {
    "system integrator",
    "systems integrator",
    "information technology",
    "it solution",
    "it solutions",
    "it services",
    "technology services",
    "managed services",
    "network solution",
    "cyber security",
    "software house",
    "digital transformation",
    "cloud solution",
    "systems solution",
}

# Preferred business categories for Abu Dhabi business establishments.
DEFAULT_CATEGORIES: Sequence[str] = (
    "office",
    "factory",
    "warehouse",
    "government office",
    "hospital",
    "clinic",
    "school",
    "university",
    "restaurant",
    "hotel",
    "oil and gas",
    "marine",
    "shop",
    "logistics",
    "manufacturing",
    "facility management",
    "construction",
    "maintenance",
    "real estate",
    "consultancy",
)


@dataclasses.dataclass
class Lead:
    """Container for an individual lead record."""

    name: str
    email: str
    phone: Optional[str]
    address: Optional[str]
    category: Optional[str]
    website: Optional[str]
    source_link: Optional[str]

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class LeadHistory:
    """Handle persistence of previously contacted lead emails."""

    def __init__(self, path: Path, max_entries: int = 10000) -> None:
        self.path = path
        self.max_entries = max_entries
        self.emails: List[str] = []
        self.load()

    def load(self) -> None:
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
            self.emails = payload.get("emails", [])[-self.max_entries :]
        else:
            self.emails = []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": dt.datetime.utcnow().isoformat(),
            "emails": self.emails[-self.max_entries :],
        }
        with self.path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)

    def has(self, email: str) -> bool:
        email_lower = email.lower()
        return any(existing.lower() == email_lower for existing in self.emails)

    def add(self, email: str) -> None:
        if not self.has(email):
            self.emails.append(email)


class LeadFetcher:
    """Collect leads from the 2GIS API."""

    def __init__(
        self,
        api_key: str,
        region_id: str,
        categories: Sequence[str],
        history: LeadHistory,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> None:
        self.api_key = api_key
        self.region_id = region_id
        self.categories = categories
        self.history = history
        self.page_size = page_size

    def fetch(self, limit: int = DEFAULT_LIMIT) -> List[Lead]:
        session = requests.Session()
        leads: List[Lead] = []
        seen: Set[str] = set()
        for category in self.categories:
            if len(leads) >= limit:
                break
            for page in range(1, 21):  # fetch up to 20 pages per category
                if len(leads) >= limit:
                    break
                try:
                    page_items = list(self._fetch_page(session, category, page))
                except requests.RequestException:
                    continue
                for item in page_items:
                    lead = self._extract_lead(item)
                    if lead is None:
                        continue
                    email_lower = lead.email.lower()
                    if email_lower in seen:
                        continue
                    if self.history.has(lead.email):
                        continue
                    leads.append(lead)
                    seen.add(email_lower)
                    self.history.add(lead.email)
                    if len(leads) >= limit:
                        break
        return leads

    def _fetch_page(self, session: requests.Session, category: str, page: int) -> Iterable[dict]:
        params = {
            "q": category,
            "page": page,
            "page_size": self.page_size,
            "region_id": self.region_id,
            "fields": "items.contact_groups,items.rubrics,items.name_ex,items.address,items.link,items.ads_options",
            "key": self.api_key,
        }
        response = session.get(DGIS_ITEMS_URL, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        items = payload.get("result", {}).get("items", [])
        return items

    def _extract_lead(self, item: dict) -> Optional[Lead]:
        name = item.get("name") or item.get("full_name")
        if not name:
            return None
        if _is_excluded(name) or _is_excluded(" ".join(_collect_rubrics(item))):
            return None

        email = _extract_email(item)
        if not email:
            return None

        category = _pick_primary_rubric(item)
        address = item.get("address_name") or item.get("address")
        phone = _extract_phone(item)
        website = _extract_website(item)
        source_link = _build_public_link(item)

        return Lead(
            name=name,
            email=email,
            phone=phone,
            address=address,
            category=category,
            website=website,
            source_link=source_link,
        )


def _is_excluded(text: Optional[str]) -> bool:
    if not text:
        return False
    lower = text.lower()
    return any(keyword in lower for keyword in EXCLUDED_KEYWORDS)


def _collect_rubrics(item: dict) -> List[str]:
    rubrics = []
    for rubric in item.get("rubrics", []) or []:
        name = rubric.get("name")
        if name:
            rubrics.append(name)
    return rubrics


def _pick_primary_rubric(item: dict) -> Optional[str]:
    rubrics = _collect_rubrics(item)
    if rubrics:
        return rubrics[0]
    name_ex = item.get("name_ex") or {}
    categories = name_ex.get("primary") or []
    if categories:
        return categories[0]
    return None


def _extract_email(item: dict) -> Optional[str]:
    for group in item.get("contact_groups", []) or []:
        for contact in group.get("contacts", []) or []:
            if contact.get("type") == "email":
                value = contact.get("value")
                if value:
                    return value.strip()
    return None


def _extract_phone(item: dict) -> Optional[str]:
    for group in item.get("contact_groups", []) or []:
        for contact in group.get("contacts", []) or []:
            if contact.get("type") in {"phone", "phone_service"}:
                value = contact.get("value")
                if value:
                    return value
    return None


def _extract_website(item: dict) -> Optional[str]:
    ads_options = item.get("ads_options") or {}
    link = ads_options.get("site_url")
    if link:
        return link
    for group in item.get("contact_groups", []) or []:
        for contact in group.get("contacts", []) or []:
            if contact.get("type") == "website":
                value = contact.get("value")
                if value:
                    return value
    return None


def _build_public_link(item: dict) -> Optional[str]:
    link = item.get("link")
    if link:
        return link
    item_id = item.get("id")
    if item_id:
        return f"https://2gis.ae/abu_dhabi/firm/{item_id}"
    return None


def write_outputs(leads: Sequence[Lead], json_path: Path, csv_path: Optional[Path]) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump({"generated_at": dt.datetime.utcnow().isoformat(), "leads": [lead.to_dict() for lead in leads]}, fh, indent=2)

    if csv_path:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", encoding="utf-8", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=list(Lead.__annotations__.keys()))
            writer.writeheader()
            for lead in leads:
                writer.writerow(lead.to_dict())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Abu Dhabi business leads from 2GIS")
    parser.add_argument("--history", type=Path, default=Path("data/contact_history.json"), help="Path to the JSON file that stores contacted emails")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Number of leads to return")
    parser.add_argument("--region-id", default=DEFAULT_REGION_ID, help="2GIS region identifier for Abu Dhabi")
    parser.add_argument("--categories", type=Path, help="Optional path to a newline separated category list")
    parser.add_argument("--json-output", type=Path, default=Path("output/daily_leads.json"), help="Where to write the JSON output")
    parser.add_argument("--csv-output", type=Path, help="Optional CSV output path")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="Page size for API requests")
    return parser.parse_args()


def read_categories(args: argparse.Namespace) -> Sequence[str]:
    if args.categories:
        with args.categories.open("r", encoding="utf-8") as fh:
            categories = [line.strip() for line in fh if line.strip()]
        if categories:
            return categories
    return DEFAULT_CATEGORIES


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("DGIS_API_KEY")
    if not api_key:
        raise RuntimeError("The DGIS_API_KEY environment variable must be set with a valid 2GIS API key.")

    categories = read_categories(args)
    history = LeadHistory(args.history)
    fetcher = LeadFetcher(
        api_key=api_key,
        region_id=args.region_id,
        categories=categories,
        history=history,
        page_size=args.page_size,
    )

    leads = fetcher.fetch(limit=args.limit)
    history.save()
    write_outputs(leads, json_path=args.json_output, csv_path=args.csv_output)
    print(json.dumps({"lead_count": len(leads), "json_output": str(args.json_output), "csv_output": str(args.csv_output) if args.csv_output else None}))


if __name__ == "__main__":
    main()
