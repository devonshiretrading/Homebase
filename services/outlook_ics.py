"""Outlook calendar sync via published ICS feed."""

import requests
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from icalendar import Calendar
from models import db, CalendarEvent

# IANA timezone for Melbourne
LOCAL_TZ = ZoneInfo("Australia/Melbourne")


def sync_ics_feed(ics_url: str, days_back: int = 7, days_forward: int = 30) -> dict:
    """Fetch ICS feed and sync events to DB.

    Only processes events within the date window to avoid churning
    through hundreds of old events.
    """
    resp = requests.get(ics_url, timeout=30)
    resp.raise_for_status()

    cal = Calendar.from_ical(resp.text)

    window_start = date.today() - timedelta(days=days_back)
    window_end = date.today() + timedelta(days=days_forward)

    created = 0
    updated = 0
    skipped = 0
    removed = 0
    seen_ids = set()

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        uid = str(component.get("UID", ""))
        if not uid:
            skipped += 1
            continue

        # Get busy status
        busy_status = str(component.get("X-MICROSOFT-CDO-BUSYSTATUS", "BUSY")).upper()

        # Skip "FREE" blocks — they're just empty time
        if busy_status == "FREE":
            skipped += 1
            continue

        # Parse start/end times
        dt_start = component.get("DTSTART")
        dt_end = component.get("DTEND")
        if not dt_start or not dt_end:
            skipped += 1
            continue

        dt_start = dt_start.dt
        dt_end = dt_end.dt

        # Handle all-day events (date objects, not datetime)
        is_all_day = not isinstance(dt_start, datetime)

        if is_all_day:
            event_date = dt_start
            start_time = time(0, 0)
            end_time = time(23, 59)
        else:
            # Convert to local timezone
            if dt_start.tzinfo is not None:
                dt_start = dt_start.astimezone(LOCAL_TZ)
                dt_end = dt_end.astimezone(LOCAL_TZ)
            event_date = dt_start.date()
            start_time = dt_start.time()
            end_time = dt_end.time()

        # Filter to our window
        if event_date < window_start or event_date > window_end:
            skipped += 1
            continue

        # Handle recurring events — icalendar expands RRULE into the UID,
        # but for published ICS feeds, Exchange usually expands them as
        # separate VEVENT entries. Use UID + date as unique key.
        external_id = f"{uid}_{event_date.isoformat()}"

        # Title from summary
        summary = str(component.get("SUMMARY", "Work meeting"))
        title = "Work meeting"  # Always show as "Work meeting" on calendar

        seen_ids.add(external_id)

        existing = CalendarEvent.query.filter_by(external_id=external_id).first()
        if existing:
            existing.date = event_date
            existing.start_time = start_time
            existing.end_time = end_time
            existing.busy_status = busy_status
            existing.is_all_day = is_all_day
            existing.raw_data = summary  # Store real title for click-to-view
            existing.synced_at = datetime.utcnow()
            updated += 1
        else:
            event = CalendarEvent(
                external_id=external_id,
                source="outlook_ics",
                title=title,
                date=event_date,
                start_time=start_time,
                end_time=end_time,
                is_all_day=is_all_day,
                busy_status=busy_status,
                raw_data=summary,  # Store real title for click-to-view
                synced_at=datetime.utcnow(),
            )
            db.session.add(event)
            created += 1

    # Remove events that are in our window but no longer in the feed
    stale = CalendarEvent.query.filter(
        CalendarEvent.source == "outlook_ics",
        CalendarEvent.date >= window_start,
        CalendarEvent.date <= window_end,
        ~CalendarEvent.external_id.in_(seen_ids) if seen_ids else True,
    ).all()
    for s in stale:
        db.session.delete(s)
        removed += 1

    # Clean up old events outside window
    CalendarEvent.query.filter(
        CalendarEvent.source == "outlook_ics",
        CalendarEvent.date < window_start,
    ).delete()

    db.session.commit()

    return {
        "created": created,
        "updated": updated,
        "removed": removed,
        "skipped": skipped,
    }
