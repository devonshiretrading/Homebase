# Lifeblock

A weekly life planning tool built with Flask. Not a habit tracker — a contextual planner that helps schedule life around the immovable blocks.

## Philosophy

- **Weekly planning, not daily nagging** — life is planned in weekly rhythms
- **Speed bumps, not reminders** — you come to it, it doesn't come to you
- **Data first, rules second, insights third** — get the pipes flowing, then build intelligence
- **Low friction** — quick-entry blocks, weekly toggles, not dragging calendar items around
- **A newspaper, not an alarm clock** — something you want to open with coffee

## Architecture

```
Data Sources (APIs)          Rules Engine          Outputs
─────────────────           ────────────          ────────
Strava (exercise)    ──┐
Weather (Open-Meteo) ──┤                         Weekly calendar view
Office 365 calendar  ──┼──▶  Rule set  ──▶       Morning email briefing
Weekly toggles       ──┤     (JSON)              Evening check-in
Activity templates   ──┘                         AI weekly summary (later)
```

## Data Sources

| Source | Status | Auth | Notes |
|--------|--------|------|-------|
| Strava | Done | OAuth2 | Activities, distance, HR, training load |
| Open-Meteo | Done | None needed | 7-day forecast, run score algorithm |
| Office 365 | Done | MS Graph OAuth2 | Work calendar — the immovable blocks |
| Weekly toggles | Done | N/A | Your weekly decisions (office days, school walk, track club) |
| Activity templates | Done | N/A | Shorthand dictionary with default durations |
| Browser geolocation | Done | Browser API | One-time prompt, stored in DB |

## Key Concepts

### Weekly Toggles
A small set of decisions (~10) that reshape the entire week:
- Office days (Mon-Fri checkboxes)
- Walking to school AM
- Doing school pickup (or Lisa)
- Track club Tuesday
- Pilates this week

These aren't calendar events — they're planning inputs that cascade into everything.

### Activity Templates
Your personal shorthand with sensible defaults:
- "Shopping" → 90 min
- "School pickup" → 15:15-15:45
- "Run" → 45 min
- "Cook dinner" → 17:30, 60 min
- "Fishmonger" → 30 min

Quick entry: pick template + day + time → block appears on calendar.

### Speed Bumps (Gates)
Contextual interruptions you opted into by opening the app:
- App open → "Drink water" gate (every 90 min)
- Morning → skincare check before showing briefing (future)
- After 9pm → "screens off" acknowledgement (future)

### Run Score
Weather-based algorithm (0-100) for outdoor running suitability:
- Temperature sweet spot: 8-18°C
- Rain probability penalty
- Wind speed penalty
- Displayed on weekly weather strip to help plan run days

## Tech Stack

- **Backend**: Flask + SQLAlchemy + SQLite
- **Frontend**: Vanilla JS + FullCalendar.js
- **Weather**: Open-Meteo (free, no API key)
- **Exercise**: Strava API
- **Calendar**: Microsoft Graph API (Office 365)
- **AI** (future): Claude API for weekly summaries

## Running Locally

```bash
cd ~/Projects/lifeblock
source venv/bin/activate
python app.py
# Opens on http://localhost:5001
```

## Project Structure

```
lifeblock/
├── app.py              # Flask app, all routes & API endpoints
├── config.py           # Configuration from .env
├── models.py           # SQLAlchemy models (all data tables)
├── services/
│   ├── weather.py      # Open-Meteo integration + run score
│   └── strava.py       # (TODO) Strava OAuth + sync
├── templates/
│   ├── base.html       # Layout with nav + water gate
│   ├── week.html       # Weekly planner (sidebar + calendar)
│   ├── mobile.html     # Mobile day view with auto-refresh
│   └── checkin.html    # Evening check-in form
├── static/
│   ├── css/style.css   # Dark theme styles
│   └── js/app.js       # Frontend logic
├── .env                # Secrets (not committed)
├── .env.example        # Template for secrets
└── requirements.txt    # Python dependencies
```

## Data Model

```
UserSettings       – location, email prefs, screen-off target
ActivityTemplate   – shorthand dictionary (name, duration, default time, color)
WeeklyPlan         – one per week, owns toggles + blocks
WeeklyToggle       – boolean decisions for the week
PlannedBlock       – concrete time blocks (manual, synced, or AI-suggested)
CalendarEvent      – synced from Office 365 / Google
StravaActivity     – synced from Strava
WeatherForecast    – 7-day forecast with run score
DailyCheckIn       – evening quick check (outside, cooked, exercised, etc.)
OAuthToken         – stored tokens for external services
```

## Roadmap

### Phase 1 — Data pipes (current)
- [x] Project scaffold + data model
- [x] Activity templates with defaults
- [x] Weekly toggles system
- [x] Weekly calendar view (FullCalendar)
- [x] Weather integration + run score
- [x] Browser geolocation
- [x] Evening check-in page
- [x] Water gate (speed bump)
- [x] Strava OAuth + activity sync
- [x] Office 365 calendar sync

### Phase 2 — Planning intelligence
- [ ] Quick natural language entry ("run thursday 7am")
- [ ] Toggle-driven auto-suggestions (office day → commute block)
- [ ] Weather-aware run planning for the week
- [ ] Morning email briefing
- [ ] Calendar conflict detection

### Phase 3 — AI coaching
- [ ] Weekly AI summary (patterns, streaks, suggestions)
- [ ] Rule engine (JSON rule set: "if strava load > X, suggest rest")
- [ ] Strava training load integration
- [ ] "Least worst" schedule optimizer
- [ ] Context-aware suggestions based on toggles + weather + calendar

### Phase 4 — Polish
- [x] Mobile-optimized views
- [x] Deploy to EC2
- [ ] Progressive web app (offline support)
- [ ] Historical trends / weekly review page

## Design Principles

1. **Don't be another app to ignore** — no push notifications, no nagging
2. **Context over reminders** — "you have a gap + good weather" > "go run!"
3. **The week is the unit** — plan weekly, execute daily
4. **10 toggles, not 100 tasks** — small decisions with big cascading effects
5. **Record, don't nag** — the data speaks for itself over time
6. **Simple until proven otherwise** — SQLite, vanilla JS, no frameworks needed yet
