from datetime import datetime, date, time
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# ---------------------------------------------------------------------------
# User settings & location
# ---------------------------------------------------------------------------
class UserSettings(db.Model):
    """Single-row table for app settings."""

    id = db.Column(db.Integer, primary_key=True, default=1)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    location_name = db.Column(db.String(120))
    # email for morning briefing
    morning_email = db.Column(db.String(200))
    morning_email_time = db.Column(db.Time, default=time(7, 0))
    screens_off_target = db.Column(db.Time, default=time(21, 0))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Activity templates - your shorthand dictionary
# ---------------------------------------------------------------------------
class ActivityTemplate(db.Model):
    """Known activity blocks with default durations.

    e.g. "shopping" = 90min, "school pickup" = 30min starting 15:15
    """

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)  # "shopping"
    default_duration_mins = db.Column(db.Integer, default=60)
    default_start_time = db.Column(db.Time, nullable=True)  # e.g. 15:15 for pickup
    category = db.Column(
        db.String(40), default="general"
    )  # exercise, errand, family, self-care
    color = db.Column(db.String(7), default="#4A90D9")  # hex for calendar display
    icon = db.Column(db.String(20), nullable=True)  # optional emoji/icon

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "default_duration_mins": self.default_duration_mins,
            "default_start_time": self.default_start_time.strftime("%H:%M")
            if self.default_start_time
            else None,
            "category": self.category,
            "color": self.color,
            "icon": self.icon,
        }


# ---------------------------------------------------------------------------
# Weekly toggles - the decisions that reshape the week
# ---------------------------------------------------------------------------
class WeeklyPlan(db.Model):
    """One row per week. The toggles + high-level decisions."""

    id = db.Column(db.Integer, primary_key=True)
    week_start = db.Column(db.Date, unique=True, nullable=False)  # Monday of the week
    notes = db.Column(db.Text, nullable=True)

    # Weekly toggles - stored as JSON-like flags
    toggles = db.relationship("WeeklyToggle", backref="week", lazy=True, cascade="all, delete-orphan")
    blocks = db.relationship("PlannedBlock", backref="week", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "week_start": self.week_start.isoformat(),
            "notes": self.notes,
            "toggles": {t.name: t.to_dict() for t in self.toggles},
            "blocks": [b.to_dict() for b in self.blocks],
        }


class WeeklyToggle(db.Model):
    """Individual toggle for a week.

    e.g. "office_monday": true, "track_club": true, "school_walk_tue": false
    """

    id = db.Column(db.Integer, primary_key=True)
    weekly_plan_id = db.Column(db.Integer, db.ForeignKey("weekly_plan.id"), nullable=False)
    name = db.Column(db.String(80), nullable=False)  # "office_monday"
    label = db.Column(db.String(120))  # "Going to office Monday"
    value = db.Column(db.Boolean, default=False)
    day_of_week = db.Column(db.Integer, nullable=True)  # 0=Mon, 6=Sun (optional)

    def to_dict(self):
        return {
            "name": self.name,
            "label": self.label,
            "value": self.value,
            "day_of_week": self.day_of_week,
        }


# ---------------------------------------------------------------------------
# Planned blocks - the actual scheduled items for the week
# ---------------------------------------------------------------------------
class PlannedBlock(db.Model):
    """A concrete time block in the week plan."""

    id = db.Column(db.Integer, primary_key=True)
    weekly_plan_id = db.Column(db.Integer, db.ForeignKey("weekly_plan.id"), nullable=False)
    activity_template_id = db.Column(
        db.Integer, db.ForeignKey("activity_template.id"), nullable=True
    )
    title = db.Column(db.String(120), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    category = db.Column(db.String(40), default="general")
    color = db.Column(db.String(7), default="#4A90D9")
    source = db.Column(
        db.String(20), default="manual"
    )  # manual, calendar_sync, strava, ai_suggested
    external_id = db.Column(db.String(200), nullable=True)  # for synced events
    completed = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text, nullable=True)

    template = db.relationship("ActivityTemplate", backref="blocks")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "date": self.date.isoformat(),
            "start_time": self.start_time.strftime("%H:%M"),
            "end_time": self.end_time.strftime("%H:%M"),
            "category": self.category,
            "color": self.color,
            "source": self.source,
            "completed": self.completed,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Calendar events - synced from Office 365 / Google
# ---------------------------------------------------------------------------
class CalendarEvent(db.Model):
    """Synced calendar events from external sources."""

    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(200), unique=True, nullable=False)
    source = db.Column(db.String(20), nullable=False)  # "office365", "google", "ics"
    title = db.Column(db.String(200), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    location = db.Column(db.String(200), nullable=True)
    is_all_day = db.Column(db.Boolean, default=False)
    attendees = db.Column(db.Text, nullable=True)  # JSON list
    busy_status = db.Column(db.String(20), nullable=True)  # "BUSY", "TENTATIVE", "FREE"
    raw_data = db.Column(db.Text, nullable=True)  # full JSON for reference
    synced_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "date": self.date.isoformat(),
            "start_time": self.start_time.strftime("%H:%M"),
            "end_time": self.end_time.strftime("%H:%M"),
            "location": self.location,
            "source": self.source,
            "is_all_day": self.is_all_day,
        }


# ---------------------------------------------------------------------------
# Strava activities
# ---------------------------------------------------------------------------
class StravaActivity(db.Model):
    """Synced from Strava API."""

    id = db.Column(db.Integer, primary_key=True)
    strava_id = db.Column(db.BigInteger, unique=True, nullable=False)
    activity_type = db.Column(db.String(40))  # Run, Ride, Walk, etc.
    name = db.Column(db.String(200))
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time)
    duration_seconds = db.Column(db.Integer)
    distance_meters = db.Column(db.Float)
    elevation_gain = db.Column(db.Float)
    average_heartrate = db.Column(db.Float)
    suffer_score = db.Column(db.Integer, nullable=True)  # Strava's relative effort
    raw_data = db.Column(db.Text, nullable=True)
    synced_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "strava_id": self.strava_id,
            "activity_type": self.activity_type,
            "name": self.name,
            "date": self.date.isoformat(),
            "start_time": self.start_time.strftime("%H:%M") if self.start_time else None,
            "duration_mins": round(self.duration_seconds / 60) if self.duration_seconds else None,
            "distance_km": round(self.distance_meters / 1000, 1)
            if self.distance_meters
            else None,
            "average_heartrate": self.average_heartrate,
            "suffer_score": self.suffer_score,
        }


# ---------------------------------------------------------------------------
# Weather forecasts
# ---------------------------------------------------------------------------
class WeatherForecast(db.Model):
    """Daily weather data from Open-Meteo."""

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    temp_max = db.Column(db.Float)
    temp_min = db.Column(db.Float)
    precipitation_probability = db.Column(db.Integer)  # percentage
    precipitation_mm = db.Column(db.Float)
    wind_speed_max = db.Column(db.Float)  # km/h
    weather_code = db.Column(db.Integer)  # WMO weather code
    sunrise = db.Column(db.Time)
    sunset = db.Column(db.Time)
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Running-friendliness score (calculated)
    run_score = db.Column(db.Integer, nullable=True)  # 0-100

    def to_dict(self):
        return {
            "date": self.date.isoformat(),
            "temp_max": self.temp_max,
            "temp_min": self.temp_min,
            "precipitation_probability": self.precipitation_probability,
            "precipitation_mm": self.precipitation_mm,
            "wind_speed_max": self.wind_speed_max,
            "weather_code": self.weather_code,
            "run_score": self.run_score,
            "sunrise": self.sunrise.strftime("%H:%M") if self.sunrise else None,
            "sunset": self.sunset.strftime("%H:%M") if self.sunset else None,
        }


class WeatherHourly(db.Model):
    """Hourly weather data for 48-hour window. More precise for planning."""

    id = db.Column(db.Integer, primary_key=True)
    datetime_utc = db.Column(db.DateTime, nullable=False, unique=True)
    datetime_local = db.Column(db.DateTime, nullable=False)
    temperature = db.Column(db.Float)
    precipitation_probability = db.Column(db.Integer)
    precipitation_mm = db.Column(db.Float)
    wind_speed = db.Column(db.Float)  # km/h
    weather_code = db.Column(db.Integer)
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "datetime": self.datetime_local.isoformat(),
            "hour": self.datetime_local.strftime("%H:%M"),
            "temperature": self.temperature,
            "precipitation_probability": self.precipitation_probability,
            "precipitation_mm": self.precipitation_mm,
            "wind_speed": self.wind_speed,
            "weather_code": self.weather_code,
        }


# ---------------------------------------------------------------------------
# Daily check-in - the evening speed bump
# ---------------------------------------------------------------------------
class DailyCheckIn(db.Model):
    """Evening quick check-in. Low friction, just radio buttons."""

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False)
    got_outside = db.Column(db.Boolean, nullable=True)
    cooked_dinner = db.Column(db.Boolean, nullable=True)
    exercised = db.Column(db.Boolean, nullable=True)
    stretched = db.Column(db.Boolean, nullable=True)
    skincare = db.Column(db.Boolean, nullable=True)
    screens_off_time = db.Column(db.Time, nullable=True)
    water_glasses = db.Column(db.Integer, nullable=True)
    mood = db.Column(db.Integer, nullable=True)  # 1-5 simple scale
    nytimes = db.Column(db.Boolean, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        mood_entries = MoodEntry.query.filter_by(date=self.date).order_by(MoodEntry.timestamp).all()
        latest_mood = mood_entries[-1].mood if mood_entries else None
        return {
            "date": self.date.isoformat(),
            "got_outside": self.got_outside,
            "cooked_dinner": self.cooked_dinner,
            "exercised": self.exercised,
            "stretched": self.stretched,
            "skincare": self.skincare,
            "screens_off_time": self.screens_off_time.strftime("%H:%M")
            if self.screens_off_time
            else None,
            "water_glasses": self.water_glasses,
            "mood": self.mood,
            "mood_name": latest_mood,
            "mood_log": [e.to_dict() for e in mood_entries],
            "nytimes": self.nytimes,
            "notes": self.notes,
        }


class MoodEntry(db.Model):
    """Track mood changes throughout the day."""

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    mood = db.Column(db.String(20), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "mood": self.mood,
            "time": self.timestamp.strftime("%H:%M") if self.timestamp else None,
        }


# ---------------------------------------------------------------------------
# OAuth tokens - for Strava, Microsoft, Google
# ---------------------------------------------------------------------------
class OAuthToken(db.Model):
    """Store OAuth tokens for external services."""

    id = db.Column(db.Integer, primary_key=True)
    service = db.Column(db.String(20), unique=True, nullable=False)  # strava, microsoft, google
    access_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.Text, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    scope = db.Column(db.String(500), nullable=True)
    raw_data = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
