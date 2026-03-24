"""Public holidays for Victoria, Australia via Nager.Date API."""

import requests
from datetime import date


NAGER_URL = "https://date.nager.at/api/v3/publicholidays"


def get_vic_holidays(year: int = None) -> list[dict]:
    """Fetch public holidays for Victoria, Australia for the given year.

    Returns list of {"date": "YYYY-MM-DD", "name": "Holiday Name"}
    """
    if year is None:
        year = date.today().year

    resp = requests.get(f"{NAGER_URL}/{year}/AU", timeout=10)
    resp.raise_for_status()
    holidays = resp.json()

    vic_holidays = []
    for h in holidays:
        # Include if global (nationwide) or if VIC is in the counties list
        counties = h.get("counties")
        if counties is None or "AU-VIC" in counties:
            vic_holidays.append({
                "date": h["date"],
                "name": h["localName"],
            })

    return vic_holidays


def get_vic_holidays_for_range(start_date: date, end_date: date) -> list[dict]:
    """Get VIC holidays that fall within a date range. Handles year boundaries."""
    years = set()
    years.add(start_date.year)
    years.add(end_date.year)

    all_holidays = []
    for year in years:
        all_holidays.extend(get_vic_holidays(year))

    return [
        h for h in all_holidays
        if start_date.isoformat() <= h["date"] <= end_date.isoformat()
    ]
