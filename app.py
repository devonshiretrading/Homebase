from datetime import datetime, date, timedelta, time
import json

from flask import Flask, render_template, request, jsonify, redirect, url_for
from config import Config
from models import (
    db,
    UserSettings,
    ActivityTemplate,
    WeeklyPlan,
    WeeklyToggle,
    PlannedBlock,
    CalendarEvent,
    StravaActivity,
    WeatherForecast,
    DailyCheckIn,
    MoodEntry,
    OAuthToken,
)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    with app.app_context():
        db.create_all()
        _seed_defaults()

    # Make timedelta available in Jinja templates
    app.jinja_env.globals["timedelta"] = timedelta

    # ----- Pages -----

    @app.route("/")
    def index():
        """Redirect to current week view."""
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        return redirect(url_for("week_view", week_start=monday.isoformat()))

    @app.route("/week/<week_start>")
    def week_view(week_start):
        """Main weekly planner view."""
        ws = date.fromisoformat(week_start)
        we = ws + timedelta(days=6)
        plan = WeeklyPlan.query.filter_by(week_start=ws).first()
        templates = ActivityTemplate.query.order_by(ActivityTemplate.name).all()
        return render_template(
            "week.html",
            week_start=ws,
            week_end=we,
            plan=plan,
            templates=templates,
        )

    @app.route("/m/")
    @app.route("/m")
    def mobile_view():
        """Mobile day view."""
        return render_template("mobile.html")

    @app.route("/checkin")
    def checkin_view():
        """Daily check-in page."""
        today = date.today()
        existing = DailyCheckIn.query.filter_by(date=today).first()
        return render_template("checkin.html", date=today, checkin=existing)

    # ----- API: Weekly Plan -----

    @app.route("/api/week/<week_start>", methods=["GET"])
    def api_get_week(week_start):
        ws = date.fromisoformat(week_start)
        plan = WeeklyPlan.query.filter_by(week_start=ws).first()
        if not plan:
            return jsonify({"week_start": ws.isoformat(), "toggles": {}, "blocks": []})
        return jsonify(plan.to_dict())

    @app.route("/api/week/<week_start>", methods=["POST"])
    def api_create_or_update_week(week_start):
        ws = date.fromisoformat(week_start)
        plan = WeeklyPlan.query.filter_by(week_start=ws).first()
        if not plan:
            plan = WeeklyPlan(week_start=ws)
            db.session.add(plan)
            db.session.flush()
        data = request.get_json()
        if "notes" in data:
            plan.notes = data["notes"]
        db.session.commit()
        return jsonify(plan.to_dict())

    # ----- API: Toggles -----

    @app.route("/api/week/<week_start>/toggles", methods=["POST"])
    def api_set_toggles(week_start):
        ws = date.fromisoformat(week_start)
        plan = WeeklyPlan.query.filter_by(week_start=ws).first()
        if not plan:
            plan = WeeklyPlan(week_start=ws)
            db.session.add(plan)
            db.session.flush()

        data = request.get_json()  # {"toggles": {"office_mon": true, ...}}

        # Map toggles to auto-block creation
        TOGGLE_TEMPLATES = {
            "track_club": "Tuesday Track Club",
        }

        # Office days: create a draggable/resizable block
        OFFICE_TOGGLES = {
            "office_mon": 0,
            "office_tue": 1,
            "office_wed": 2,
            "office_thu": 3,
            "office_fri": 4,
        }

        # School walk: different times for Mon/Wed vs Tue/Thu/Fri
        SCHOOL_WALK_TIMES = {
            "school_walk_mon": (time(8, 0), time(9, 0)),
            "school_walk_tue": (time(8, 30), time(9, 30)),
            "school_walk_wed": (time(8, 0), time(9, 0)),
            "school_walk_thu": (time(8, 30), time(9, 30)),
            "school_walk_fri": (time(8, 30), time(9, 30)),
        }

        # Dinner: 5:30-6:30
        DINNER_TOGGLES = {
            "dinner_mon": 0, "dinner_tue": 1, "dinner_wed": 2,
            "dinner_thu": 3, "dinner_fri": 4, "dinner_sat": 5, "dinner_sun": 6,
        }

        # Pick-up: 3:15-3:45 every day
        PICKUP_TOGGLES = {
            "pickup_mon": 0,
            "pickup_tue": 1,
            "pickup_wed": 2,
            "pickup_thu": 3,
            "pickup_fri": 4,
        }

        for toggle_name, toggle_data in data.get("toggles", {}).items():
            existing = WeeklyToggle.query.filter_by(
                weekly_plan_id=plan.id, name=toggle_name
            ).first()
            if existing:
                existing.value = toggle_data.get("value", False)
            else:
                t = WeeklyToggle(
                    weekly_plan_id=plan.id,
                    name=toggle_name,
                    label=toggle_data.get("label", toggle_name),
                    value=toggle_data.get("value", False),
                    day_of_week=toggle_data.get("day_of_week"),
                )
                db.session.add(t)

            # Auto-create/remove block if toggle has an associated template
            is_on = toggle_data.get("value", False)
            template_name = TOGGLE_TEMPLATES.get(toggle_name)
            if template_name:
                template = ActivityTemplate.query.filter_by(name=template_name).first()
                if template:
                    day_of_week = toggle_data.get("day_of_week")
                    if day_of_week is not None:
                        block_date = ws + timedelta(days=day_of_week)
                    else:
                        block_date = ws  # fallback

                    # Find existing auto-created block
                    existing_block = PlannedBlock.query.filter_by(
                        weekly_plan_id=plan.id,
                        activity_template_id=template.id,
                        source="toggle",
                    ).first()

                    if is_on and not existing_block:
                        start = template.default_start_time or time(9, 0)
                        end_dt = datetime.combine(block_date, start) + timedelta(
                            minutes=template.default_duration_mins
                        )
                        block = PlannedBlock(
                            weekly_plan_id=plan.id,
                            activity_template_id=template.id,
                            title=template.name,
                            date=block_date,
                            start_time=start,
                            end_time=end_dt.time(),
                            category=template.category,
                            color=template.color,
                            source="toggle",
                        )
                        db.session.add(block)
                    elif not is_on and existing_block:
                        db.session.delete(existing_block)

            # School walk blocks with day-specific times
            if toggle_name in SCHOOL_WALK_TIMES:
                sw_start, sw_end = SCHOOL_WALK_TIMES[toggle_name]
                day_of_week = toggle_data.get("day_of_week")
                if day_of_week is not None:
                    block_date = ws + timedelta(days=day_of_week)
                    existing_block = PlannedBlock.query.filter_by(
                        weekly_plan_id=plan.id,
                        title="School walk",
                        date=block_date,
                        source="toggle",
                    ).first()

                    if is_on and not existing_block:
                        block = PlannedBlock(
                            weekly_plan_id=plan.id,
                            title="School walk",
                            date=block_date,
                            start_time=sw_start,
                            end_time=sw_end,
                            category="family",
                            color="#F5A623",
                            source="toggle",
                        )
                        db.session.add(block)
                    elif not is_on and existing_block:
                        db.session.delete(existing_block)

            # Dinner blocks
            if toggle_name in DINNER_TOGGLES:
                day_of_week = DINNER_TOGGLES[toggle_name]
                block_date = ws + timedelta(days=day_of_week)
                existing_block = PlannedBlock.query.filter_by(
                    weekly_plan_id=plan.id,
                    title="Cook dinner",
                    date=block_date,
                    source="toggle",
                ).first()

                # Tuesday dinner is 7-8 (after track club)
                if day_of_week == 1:
                    dinner_start, dinner_end = time(19, 0), time(20, 0)
                else:
                    dinner_start, dinner_end = time(18, 30), time(19, 30)

                if is_on and not existing_block:
                    block = PlannedBlock(
                        weekly_plan_id=plan.id,
                        title="Cook dinner",
                        date=block_date,
                        start_time=dinner_start,
                        end_time=dinner_end,
                        category="dinner",
                        color="#BD10E0",
                        source="toggle",
                    )
                    db.session.add(block)
                elif not is_on and existing_block:
                    db.session.delete(existing_block)

            # Pick-up blocks
            if toggle_name in PICKUP_TOGGLES:
                day_of_week = PICKUP_TOGGLES[toggle_name]
                block_date = ws + timedelta(days=day_of_week)
                existing_block = PlannedBlock.query.filter_by(
                    weekly_plan_id=plan.id,
                    title="Pick-up",
                    date=block_date,
                    source="toggle",
                ).first()

                if is_on and not existing_block:
                    block = PlannedBlock(
                        weekly_plan_id=plan.id,
                        title="Pick-up",
                        date=block_date,
                        start_time=time(15, 15),
                        end_time=time(15, 45),
                        category="family",
                        color="#F5A623",
                        source="toggle",
                    )
                    db.session.add(block)
                elif not is_on and existing_block:
                    db.session.delete(existing_block)

            # Office day blocks
            if toggle_name in OFFICE_TOGGLES:
                day_of_week = OFFICE_TOGGLES[toggle_name]
                block_date = ws + timedelta(days=day_of_week)
                existing_block = PlannedBlock.query.filter_by(
                    weekly_plan_id=plan.id,
                    title="Office",
                    date=block_date,
                    source="toggle",
                ).first()

                if is_on and not existing_block:
                    block = PlannedBlock(
                        weekly_plan_id=plan.id,
                        title="Office",
                        date=block_date,
                        start_time=time(8, 0),
                        end_time=time(17, 0),
                        category="work",
                        color="#2a2e3d",
                        source="toggle",
                    )
                    db.session.add(block)
                elif not is_on and existing_block:
                    db.session.delete(existing_block)

        db.session.commit()
        return jsonify(plan.to_dict())

    # ----- API: Planned Blocks -----

    @app.route("/api/blocks", methods=["POST"])
    def api_add_block():
        data = request.get_json()
        block_date = date.fromisoformat(data["date"])
        monday = block_date - timedelta(days=block_date.weekday())

        plan = WeeklyPlan.query.filter_by(week_start=monday).first()
        if not plan:
            plan = WeeklyPlan(week_start=monday)
            db.session.add(plan)
            db.session.flush()

        # If a template name is given, look it up for defaults
        template = None
        if data.get("template_id"):
            template = ActivityTemplate.query.get(data["template_id"])
        elif data.get("title"):
            template = ActivityTemplate.query.filter(
                ActivityTemplate.name.ilike(data["title"])
            ).first()

        title = data.get("title", template.name if template else "Block")
        start_time = time.fromisoformat(data["start_time"])

        if data.get("end_time"):
            end_time = time.fromisoformat(data["end_time"])
        elif template:
            end_dt = datetime.combine(block_date, start_time) + timedelta(
                minutes=template.default_duration_mins
            )
            end_time = end_dt.time()
        else:
            end_dt = datetime.combine(block_date, start_time) + timedelta(minutes=60)
            end_time = end_dt.time()

        block = PlannedBlock(
            weekly_plan_id=plan.id,
            activity_template_id=template.id if template else None,
            title=title,
            date=block_date,
            start_time=start_time,
            end_time=end_time,
            category=template.category if template else data.get("category", "general"),
            color=template.color if template else data.get("color", "#4A90D9"),
            source=data.get("source", "manual"),
            notes=data.get("notes"),
        )
        db.session.add(block)
        db.session.commit()
        return jsonify(block.to_dict()), 201

    @app.route("/api/blocks/<int:block_id>", methods=["PUT"])
    def api_update_block(block_id):
        block = PlannedBlock.query.get_or_404(block_id)
        data = request.get_json()
        if "date" in data:
            block.date = date.fromisoformat(data["date"])
        if "start_time" in data:
            block.start_time = time.fromisoformat(data["start_time"])
        if "end_time" in data:
            block.end_time = time.fromisoformat(data["end_time"])
        if "title" in data:
            block.title = data["title"]
        if "completed" in data:
            block.completed = data["completed"]
        if "notes" in data:
            block.notes = data["notes"]
        db.session.commit()
        return jsonify(block.to_dict())

    @app.route("/api/blocks/<int:block_id>", methods=["DELETE"])
    def api_delete_block(block_id):
        block = PlannedBlock.query.get_or_404(block_id)
        db.session.delete(block)
        db.session.commit()
        return jsonify({"deleted": block_id})

    # ----- API: Activity Templates -----

    @app.route("/api/templates", methods=["GET"])
    def api_get_templates():
        templates = ActivityTemplate.query.order_by(ActivityTemplate.name).all()
        return jsonify([t.to_dict() for t in templates])

    @app.route("/api/templates", methods=["POST"])
    def api_add_template():
        data = request.get_json()
        t = ActivityTemplate(
            name=data["name"],
            default_duration_mins=data.get("default_duration_mins", 60),
            default_start_time=time.fromisoformat(data["default_start_time"])
            if data.get("default_start_time")
            else None,
            category=data.get("category", "general"),
            color=data.get("color", "#4A90D9"),
            icon=data.get("icon"),
        )
        db.session.add(t)
        db.session.commit()
        return jsonify(t.to_dict()), 201

    # ----- API: Daily Check-in -----

    @app.route("/api/checkin", methods=["GET"])
    def api_checkin_get():
        check_date = date.fromisoformat(
            request.args.get("date", date.today().isoformat())
        )
        checkin = DailyCheckIn.query.filter_by(date=check_date).first()
        if checkin:
            return jsonify(checkin.to_dict())
        return jsonify({
            "date": check_date.isoformat(),
            "water_glasses": 0,
            "skincare": False,
            "exercised": False,
            "got_outside": False,
            "stretched": False,
            "mood": None,
        })

    @app.route("/api/checkin", methods=["POST"])
    def api_checkin():
        data = request.get_json()
        check_date = date.fromisoformat(data.get("date", date.today().isoformat()))
        checkin = DailyCheckIn.query.filter_by(date=check_date).first()
        if not checkin:
            checkin = DailyCheckIn(date=check_date)
            db.session.add(checkin)

        for field in [
            "got_outside", "cooked_dinner", "exercised", "stretched",
            "skincare", "water_glasses", "mood", "nytimes", "notes",
        ]:
            if field in data:
                setattr(checkin, field, data[field])
        if "screens_off_time" in data and data["screens_off_time"]:
            checkin.screens_off_time = time.fromisoformat(data["screens_off_time"])

        db.session.commit()
        return jsonify(checkin.to_dict())

    @app.route("/api/checkin/mood", methods=["POST"])
    def api_checkin_mood():
        data = request.get_json()
        check_date = date.fromisoformat(data.get("date", date.today().isoformat()))
        mood_name = data["mood"]

        entry = MoodEntry(
            date=check_date,
            mood=mood_name,
            timestamp=datetime.now(),
        )
        db.session.add(entry)
        db.session.commit()
        return jsonify(entry.to_dict()), 201

    # ----- API: Food shopping -----

    @app.route("/api/food-shopping", methods=["GET"])
    def api_food_shopping_get():
        ws = date.fromisoformat(request.args.get("week_start", ""))
        # Find all food shopping blocks for this week
        end_date = ws + timedelta(days=6)
        blocks = PlannedBlock.query.filter(
            PlannedBlock.date >= ws,
            PlannedBlock.date <= end_date,
            PlannedBlock.category == "food_shopping",
        ).all()

        plans = {}
        for b in blocks:
            day_idx = (b.date - ws).days
            shops = [s.strip() for s in b.notes.split(",")] if b.notes else []
            plans[str(day_idx)] = shops

        return jsonify({"plans": plans})

    @app.route("/api/food-shopping", methods=["POST"])
    def api_food_shopping_post():
        data = request.get_json()
        ws = date.fromisoformat(data["week_start"])
        day_idx = data["day_index"]
        shop = data["shop"]
        checked = data["checked"]

        block_date = ws + timedelta(days=day_idx)

        plan = WeeklyPlan.query.filter_by(week_start=ws).first()
        if not plan:
            plan = WeeklyPlan(week_start=ws)
            db.session.add(plan)
            db.session.flush()

        # Find existing food block for this day
        block = PlannedBlock.query.filter_by(
            weekly_plan_id=plan.id,
            date=block_date,
            category="food_shopping",
        ).first()

        if block:
            current_shops = [s.strip() for s in block.notes.split(",")] if block.notes else []
        else:
            current_shops = []

        if checked and shop not in current_shops:
            current_shops.append(shop)
        elif not checked and shop in current_shops:
            current_shops.remove(shop)

        if current_shops:
            shop_label = ", ".join(current_shops)
            if block:
                block.notes = shop_label
                block.title = "Shopping"
            else:
                # Find best slot, prefer 10:30
                from services.scheduler import find_best_slot
                slot = find_best_slot(
                    block_date,
                    duration_mins=60,
                    preferred_time=time(10, 30),
                    earliest=time(8, 0),
                    latest=time(16, 0),
                    avoid_rain=False,
                )
                start = time.fromisoformat(slot["start_time"]) if slot else time(10, 30)
                end_dt = datetime.combine(block_date, start) + timedelta(minutes=60)
                end = end_dt.time()

                block = PlannedBlock(
                    weekly_plan_id=plan.id,
                    title="Shopping",
                    date=block_date,
                    start_time=start,
                    end_time=end,
                    category="food_shopping",
                    color="#50E3C2",
                    source="food_panel",
                    notes=shop_label,
                )
                db.session.add(block)
        elif block:
            db.session.delete(block)

        db.session.commit()
        return jsonify({"ok": True})

    # ----- API: Calendar events (for FullCalendar feed) -----

    @app.route("/api/events", methods=["GET"])
    def api_events():
        """Combined feed for FullCalendar - blocks + calendar events."""
        start = request.args.get("start", "")
        end = request.args.get("end", "")
        if not start or not end:
            return jsonify([])

        start_date = date.fromisoformat(start[:10])
        end_date = date.fromisoformat(end[:10])

        events = []

        # Planned blocks
        blocks = PlannedBlock.query.filter(
            PlannedBlock.date >= start_date, PlannedBlock.date < end_date
        ).all()
        for b in blocks:
            event = {
                "id": f"block_{b.id}",
                "title": b.title,
                "start": f"{b.date.isoformat()}T{b.start_time.strftime('%H:%M')}",
                "end": f"{b.date.isoformat()}T{b.end_time.strftime('%H:%M')}",
                "color": b.color,
                "extendedProps": {
                    "type": "block",
                    "block_id": b.id,
                    "category": b.category,
                    "source": b.source,
                    "completed": b.completed,
                    "notes": b.notes or "",
                },
            }
            # Office blocks: subtle style, but still draggable/resizable
            if b.category == "work":
                event["color"] = "rgba(74, 144, 217, 0.15)"
                event["borderColor"] = "rgba(74, 144, 217, 0.3)"
                event["textColor"] = "rgba(255, 255, 255, 0.4)"
            # Family blocks (school walk, pick-up): black text on orange
            if b.category == "family":
                event["textColor"] = "#000000"
            # Lisa blocks: subtle pink background
            if b.category == "lisa":
                event["color"] = "rgba(233, 30, 140, 0.15)"
                event["borderColor"] = "rgba(233, 30, 140, 0.3)"
                event["textColor"] = "rgba(233, 30, 140, 0.7)"
            # Hugo blocks: subtle yellow background
            if b.category == "hugo":
                event["color"] = "rgba(245, 166, 35, 0.15)"
                event["borderColor"] = "rgba(245, 166, 35, 0.3)"
                event["textColor"] = "rgba(245, 166, 35, 0.7)"
            events.append(event)

        # Synced calendar events
        cal_events = CalendarEvent.query.filter(
            CalendarEvent.date >= start_date, CalendarEvent.date < end_date
        ).all()
        for c in cal_events:
            is_tentative = c.busy_status == "TENTATIVE"
            event = {
                "id": f"cal_{c.id}",
                "title": c.title,
                "start": f"{c.date.isoformat()}T{c.start_time.strftime('%H:%M')}",
                "end": f"{c.date.isoformat()}T{c.end_time.strftime('%H:%M')}",
                "color": "#888888" if not is_tentative else "transparent",
                "borderColor": "#888888",
                "extendedProps": {
                    "type": "calendar",
                    "source": c.source,
                    "busy_status": c.busy_status,
                    "detail": c.raw_data,
                    "is_tentative": is_tentative,
                },
            }
            events.append(event)

        # Public holidays
        from services.holidays import get_vic_holidays_for_range
        try:
            holidays = get_vic_holidays_for_range(start_date, end_date)
            for h in holidays:
                events.append({
                    "id": f"holiday_{h['date']}",
                    "title": f"🎉 {h['name']}",
                    "start": h["date"],
                    "allDay": True,
                    "color": "#F5A623",
                    "textColor": "#000000",
                    "editable": False,
                    "extendedProps": {
                        "type": "holiday",
                    },
                })
        except Exception:
            pass  # Don't break the calendar if the API is down

        return jsonify(events)

    # ----- API: Location -----

    @app.route("/api/location", methods=["POST"])
    def api_set_location():
        data = request.get_json()
        settings = UserSettings.query.first()
        if not settings:
            settings = UserSettings(id=1)
            db.session.add(settings)
        settings.latitude = data["lat"]
        settings.longitude = data["lon"]
        settings.location_name = data.get("name", "")
        db.session.commit()
        return jsonify({"lat": settings.latitude, "lon": settings.longitude, "name": settings.location_name})

    @app.route("/api/location", methods=["GET"])
    def api_get_location():
        settings = UserSettings.query.first()
        if not settings or not settings.latitude:
            return jsonify({"lat": None, "lon": None})
        return jsonify({"lat": settings.latitude, "lon": settings.longitude, "name": settings.location_name})

    # ----- Strava OAuth + API -----

    @app.route("/auth/strava")
    def strava_connect():
        """Redirect to Strava OAuth."""
        from services.strava import get_auth_url
        return redirect(get_auth_url())

    @app.route("/auth/strava/callback")
    def strava_callback():
        """Handle Strava OAuth callback."""
        code = request.args.get("code")
        error = request.args.get("error")
        if error:
            return f"Strava authorization denied: {error}", 400
        if not code:
            return "No authorization code received", 400

        from services.strava import exchange_code
        exchange_code(code)
        # Sync activities immediately after connecting
        from services.strava import sync_activities
        result = sync_activities(days_back=90)
        return redirect(url_for("index"))

    @app.route("/api/strava/status")
    def api_strava_status():
        from services.strava import get_connection_status
        return jsonify(get_connection_status())

    @app.route("/api/strava/sync", methods=["POST"])
    def api_strava_sync():
        from services.strava import sync_activities
        data = request.get_json() or {}
        days_back = data.get("days_back", 30)
        result = sync_activities(days_back=days_back)
        return jsonify(result)

    @app.route("/api/strava/activities")
    def api_strava_activities():
        """Get stored Strava activities."""
        days = request.args.get("days", 30, type=int)
        since = date.today() - timedelta(days=days)
        activities = StravaActivity.query.filter(
            StravaActivity.date >= since
        ).order_by(StravaActivity.date.desc()).all()
        return jsonify([a.to_dict() for a in activities])

    # ----- API: Outlook ICS Sync -----

    @app.route("/api/outlook/sync", methods=["POST"])
    def api_outlook_sync():
        ics_url = app.config.get("OUTLOOK_ICS_URL")
        if not ics_url:
            return jsonify({"error": "No ICS URL configured"}), 400
        from services.outlook_ics import sync_ics_feed
        result = sync_ics_feed(ics_url)
        return jsonify(result)

    # ----- API: Running Insights -----

    @app.route("/api/insights/running", methods=["GET"])
    def api_running_insights():
        """Last 3 runs + scheduled runs this week."""
        # Last 3 runs from Strava
        recent_runs = StravaActivity.query.filter(
            StravaActivity.activity_type.in_(["Run", "TrailRun"])
        ).order_by(StravaActivity.date.desc()).limit(3).all()

        # Weekly stats (last 7 days)
        week_ago = date.today() - timedelta(days=7)
        week_runs = StravaActivity.query.filter(
            StravaActivity.activity_type.in_(["Run", "TrailRun"]),
            StravaActivity.date >= week_ago,
        ).all()
        week_distance = sum(r.distance_meters or 0 for r in week_runs) / 1000
        week_duration = sum(r.duration_seconds or 0 for r in week_runs) / 60

        # 4-week rolling average for fitness proxy
        four_weeks_ago = date.today() - timedelta(days=28)
        month_runs = StravaActivity.query.filter(
            StravaActivity.activity_type.in_(["Run", "TrailRun"]),
            StravaActivity.date >= four_weeks_ago,
        ).all()
        month_distance = sum(r.distance_meters or 0 for r in month_runs) / 1000
        weekly_avg = month_distance / 4

        # Scheduled runs this week
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        scheduled = PlannedBlock.query.filter(
            PlannedBlock.date >= monday,
            PlannedBlock.date <= sunday,
            PlannedBlock.category == "exercise",
        ).order_by(PlannedBlock.date).all()

        return jsonify({
            "recent_runs": [{
                "date": r.date.isoformat(),
                "name": r.name,
                "distance_km": round((r.distance_meters or 0) / 1000, 1),
                "duration_mins": round((r.duration_seconds or 0) / 60),
                "pace": _calc_pace(r.distance_meters, r.duration_seconds),
                "avg_hr": r.average_heartrate,
                "suffer_score": r.suffer_score,
            } for r in recent_runs],
            "week_summary": {
                "distance_km": round(week_distance, 1),
                "duration_mins": round(week_duration),
                "run_count": len(week_runs),
            },
            "fitness": {
                "weekly_avg_km": round(weekly_avg, 1),
                "month_total_km": round(month_distance, 1),
            },
            "scheduled": [{
                "date": s.date.isoformat(),
                "title": s.title,
                "start_time": s.start_time.strftime("%H:%M"),
                "end_time": s.end_time.strftime("%H:%M"),
            } for s in scheduled],
        })

    # ----- API: Schedule a run -----

    @app.route("/api/schedule-run", methods=["POST"])
    def api_schedule_run():
        """Toggle a run on/off for a specific day. Auto-suggests time."""
        data = request.get_json()
        run_type = data["run_type"]  # "office", "sangsters", "long", "parkrun", "track_club"
        enabled = data.get("enabled", True)

        # Map run types to days and details
        RUN_CONFIG = {
            "track_club": {"day": 1, "title": "Tuesday Track Club", "duration": 120, "category": "exercise", "color": "#7ED321"},
            "office": {"day": 3, "title": "Office Run", "duration": 90, "category": "exercise", "color": "#7ED321"},
            "parkrun": {"day": 5, "title": "Parkrun", "duration": 90, "category": "exercise", "color": "#7ED321"},
            "long": {"day": 6, "title": "Long Run", "duration": 90, "category": "exercise", "color": "#7ED321"},
            "sangsters": {"day": None, "title": "Sangsters Run", "duration": 30, "category": "exercise", "color": "#7ED321"},
        }

        config = RUN_CONFIG.get(run_type)
        if not config:
            return jsonify({"error": "Unknown run type"}), 400

        today = date.today()
        monday = today - timedelta(days=today.weekday())

        # For sangsters, use the day from request or default to today's weekday
        if config["day"] is not None:
            target_date = monday + timedelta(days=config["day"])
        else:
            req_day = data.get("day_of_week", today.weekday())
            target_date = monday + timedelta(days=req_day)

        plan = WeeklyPlan.query.filter_by(week_start=monday).first()
        if not plan:
            plan = WeeklyPlan(week_start=monday)
            db.session.add(plan)
            db.session.flush()

        # Find existing block for this run type
        existing = PlannedBlock.query.filter_by(
            weekly_plan_id=plan.id,
            title=config["title"],
            source="run_toggle",
        ).first()

        if not enabled:
            if existing:
                db.session.delete(existing)
                db.session.commit()
            return jsonify({"removed": True})

        # Get smart time suggestion
        from services.scheduler import suggest_run_time
        suggestion = suggest_run_time(target_date, run_type)

        if not suggestion:
            return jsonify({"error": "No available slot found"}), 400

        start_time = time.fromisoformat(suggestion["start_time"])
        end_time = time.fromisoformat(suggestion["end_time"])

        if existing:
            existing.date = target_date
            existing.start_time = start_time
            existing.end_time = end_time
        else:
            block = PlannedBlock(
                weekly_plan_id=plan.id,
                title=config["title"],
                date=target_date,
                start_time=start_time,
                end_time=end_time,
                category=config["category"],
                color=config["color"],
                source="run_toggle",
            )
            db.session.add(block)

        db.session.commit()

        return jsonify({
            "scheduled": True,
            "date": target_date.isoformat(),
            "start_time": suggestion["start_time"],
            "end_time": suggestion["end_time"],
            "reason": suggestion.get("reason", ""),
        })

    # ----- API: Weather -----

    @app.route("/api/weather", methods=["GET"])
    def api_get_weather():
        forecasts = WeatherForecast.query.filter(
            WeatherForecast.date >= date.today(),
            WeatherForecast.date <= date.today() + timedelta(days=7),
        ).order_by(WeatherForecast.date).all()
        return jsonify([f.to_dict() for f in forecasts])

    @app.route("/api/weather/hourly", methods=["GET"])
    def api_get_weather_hourly():
        from models import WeatherHourly
        now = datetime.utcnow()
        forecasts = WeatherHourly.query.filter(
            WeatherHourly.datetime_local >= now,
            WeatherHourly.datetime_local <= now + timedelta(hours=48),
        ).order_by(WeatherHourly.datetime_local).all()
        return jsonify([f.to_dict() for f in forecasts])

    @app.route("/api/weather/refresh", methods=["POST"])
    def api_refresh_weather():
        settings = UserSettings.query.first()
        if not settings or not settings.latitude:
            return jsonify({"error": "Location not set"}), 400
        from services.weather import fetch_and_store_weather
        result = fetch_and_store_weather(settings.latitude, settings.longitude)
        return jsonify(result)

    return app


def _calc_pace(distance_meters, duration_seconds):
    """Calculate pace in min/km as a string like '5:23'."""
    if not distance_meters or not duration_seconds or distance_meters == 0:
        return None
    pace_seconds_per_km = duration_seconds / (distance_meters / 1000)
    mins = int(pace_seconds_per_km // 60)
    secs = int(pace_seconds_per_km % 60)
    return f"{mins}:{secs:02d}"


def _seed_defaults():
    """Seed default activity templates if the table is empty."""
    if ActivityTemplate.query.count() == 0:
        defaults = [
            ActivityTemplate(name="School dropoff", default_duration_mins=30, default_start_time=time(8, 15), category="family", color="#F5A623", icon="🚶"),
            ActivityTemplate(name="School pickup", default_duration_mins=30, default_start_time=time(15, 15), category="family", color="#F5A623", icon="🚶"),
            ActivityTemplate(name="Run", default_duration_mins=45, category="exercise", color="#7ED321", icon="🏃"),
            ActivityTemplate(name="Track club", default_duration_mins=90, default_start_time=time(18, 30), category="exercise", color="#7ED321", icon="🏃"),
            ActivityTemplate(name="Pilates", default_duration_mins=60, category="exercise", color="#BD10E0", icon="🧘"),
            ActivityTemplate(name="Stretch", default_duration_mins=15, default_start_time=time(6, 45), category="self-care", color="#BD10E0", icon="🙆"),
            ActivityTemplate(name="Skincare", default_duration_mins=10, default_start_time=time(7, 0), category="self-care", color="#4A90D9", icon="✨"),
            ActivityTemplate(name="Shopping", default_duration_mins=90, category="errand", color="#9B9B9B", icon="🛒"),
            ActivityTemplate(name="Fishmonger", default_duration_mins=30, category="errand", color="#50E3C2", icon="🐟"),
            ActivityTemplate(name="Cook dinner", default_duration_mins=60, default_start_time=time(17, 30), category="family", color="#F5A623", icon="🍳"),
            ActivityTemplate(name="Commute to city", default_duration_mins=45, category="travel", color="#9B9B9B", icon="🚆"),
        ]
        db.session.add_all(defaults)
        db.session.commit()


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5001)
