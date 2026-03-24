"""Smart time suggestion engine for activities.

Looks at calendar, weather, and preferences to find the best slot.
"""

from datetime import date, time, datetime, timedelta
from models import db, PlannedBlock, CalendarEvent, WeatherHourly, WeeklyPlan


def find_best_slot(
    target_date: date,
    duration_mins: int = 30,
    preferred_time: time = None,
    earliest: time = time(6, 0),
    latest: time = time(20, 0),
    avoid_rain: bool = True,
) -> dict:
    """Find the best available time slot on a given date.

    Returns {"start_time": "HH:MM", "end_time": "HH:MM", "reason": "..."}
    """
    # Get all existing blocks and calendar events for this date
    blocks = PlannedBlock.query.filter_by(date=target_date).all()
    cal_events = CalendarEvent.query.filter_by(date=target_date).all()

    # Build list of busy periods (ignore background blocks)
    BACKGROUND_CATEGORIES = {"work", "lisa", "hugo"}
    busy = []
    for b in blocks:
        if b.category in BACKGROUND_CATEGORIES:
            continue
        busy.append((b.start_time, b.end_time))
    for c in cal_events:
        if c.busy_status == "FREE":
            continue
        busy.append((c.start_time, c.end_time))

    # Sort by start time
    busy.sort(key=lambda x: x[0])

    # Get hourly weather for this date
    rain_hours = set()
    if avoid_rain:
        hourly = WeatherHourly.query.filter(
            WeatherHourly.datetime_local >= datetime.combine(target_date, time(0, 0)),
            WeatherHourly.datetime_local < datetime.combine(target_date + timedelta(days=1), time(0, 0)),
        ).all()
        for h in hourly:
            if h.precipitation_probability and h.precipitation_probability > 40:
                rain_hours.add(h.datetime_local.hour)

    # Generate candidate slots (every 15 mins)
    candidates = []
    current = datetime.combine(target_date, earliest)
    end_limit = datetime.combine(target_date, latest)

    while current + timedelta(minutes=duration_mins) <= end_limit:
        slot_start = current.time()
        slot_end = (current + timedelta(minutes=duration_mins)).time()

        # Check if slot overlaps any busy period
        is_free = True
        for busy_start, busy_end in busy:
            if slot_start < busy_end and slot_end > busy_start:
                is_free = False
                break

        if is_free:
            # Check rain
            slot_hours = set()
            for h in range(current.hour, (current + timedelta(minutes=duration_mins)).hour + 1):
                slot_hours.add(h)
            has_rain = bool(slot_hours & rain_hours)

            # Score this slot
            score = 100

            # Rain penalty
            if has_rain:
                score -= 40

            # Preference penalty (distance from preferred time)
            if preferred_time:
                pref_mins = preferred_time.hour * 60 + preferred_time.minute
                slot_mins = slot_start.hour * 60 + slot_start.minute
                diff = abs(pref_mins - slot_mins)
                score -= min(diff / 10, 30)  # Max 30 point penalty

            # Avoid very early or very late
            if slot_start.hour < 7:
                score -= 10
            if slot_start.hour >= 19:
                score -= 15

            # Avoid meal times
            if slot_start.hour == 12 and slot_start.minute >= 0 and slot_start.hour < 13:
                score -= 5  # Lunch is ok but not ideal
            if slot_start.hour >= 18 and slot_start.hour < 20:
                score -= 10  # Dinner time

            reason_parts = []
            if has_rain:
                reason_parts.append("rain likely")
            if not has_rain and avoid_rain:
                reason_parts.append("dry")

            candidates.append({
                "start_time": slot_start.strftime("%H:%M"),
                "end_time": slot_end.strftime("%H:%M"),
                "score": score,
                "has_rain": has_rain,
                "reason": ", ".join(reason_parts) if reason_parts else "clear slot",
            })

        current += timedelta(minutes=15)

    if not candidates:
        return None

    # Sort by score descending
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[0]


def suggest_run_time(
    target_date: date,
    run_type: str,
) -> dict:
    """Suggest a run time based on run type and context.

    run_type: "office", "sangsters", "long", "parkrun"
    """
    if run_type == "parkrun":
        # Fixed time
        return {
            "start_time": "07:30",
            "end_time": "09:00",
            "reason": "Parkrun",
        }

    if run_type == "office":
        # Prefer early afternoon, then morning, then lunch
        # Try 1pm first, fall back to 1:30 if blocked
        slot = find_best_slot(
            target_date,
            duration_mins=90,
            preferred_time=time(13, 0),
            earliest=time(7, 0),
            latest=time(17, 0),
        )
        if not slot:
            slot = find_best_slot(
                target_date,
                duration_mins=90,
                preferred_time=time(13, 30),
                earliest=time(7, 0),
                latest=time(17, 0),
            )
        return slot

    if run_type == "sangsters":
        # Default prefer 2pm, but flexible
        slot = find_best_slot(
            target_date,
            duration_mins=30,
            preferred_time=time(14, 0),
            earliest=time(7, 0),
            latest=time(18, 0),
        )
        return slot

    if run_type == "long":
        # Prefer morning for long runs
        slot = find_best_slot(
            target_date,
            duration_mins=90,
            preferred_time=time(8, 0),
            earliest=time(6, 30),
            latest=time(15, 0),
        )
        return slot

    # Generic
    return find_best_slot(
        target_date,
        duration_mins=30,
        preferred_time=time(14, 0),
    )
