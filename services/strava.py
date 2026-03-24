"""Strava OAuth2 + activity sync."""

import json
from datetime import datetime, date, timedelta
import requests
from flask import current_app
from models import db, OAuthToken, StravaActivity


STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"


def get_auth_url() -> str:
    """Generate the Strava OAuth authorization URL."""
    client_id = current_app.config["STRAVA_CLIENT_ID"]
    redirect_uri = current_app.config["STRAVA_REDIRECT_URI"]
    return (
        f"{STRAVA_AUTH_URL}"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=read,activity:read_all"
        f"&approval_prompt=auto"
    )


def exchange_code(code: str) -> dict:
    """Exchange authorization code for access + refresh tokens."""
    resp = requests.post(
        STRAVA_TOKEN_URL,
        data={
            "client_id": current_app.config["STRAVA_CLIENT_ID"],
            "client_secret": current_app.config["STRAVA_CLIENT_SECRET"],
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    # Store tokens
    token = OAuthToken.query.filter_by(service="strava").first()
    if not token:
        token = OAuthToken(service="strava")
        db.session.add(token)

    token.access_token = data["access_token"]
    token.refresh_token = data["refresh_token"]
    token.expires_at = datetime.utcfromtimestamp(data["expires_at"])
    token.scope = "read,activity:read_all"
    token.raw_data = json.dumps(data)
    db.session.commit()

    return data


def _get_valid_token() -> str:
    """Get a valid access token, refreshing if expired."""
    token = OAuthToken.query.filter_by(service="strava").first()
    if not token:
        raise ValueError("Strava not connected. Visit /auth/strava to connect.")

    # Refresh if expired (or within 5 min of expiry)
    if token.expires_at and token.expires_at < datetime.utcnow() + timedelta(minutes=5):
        resp = requests.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": current_app.config["STRAVA_CLIENT_ID"],
                "client_secret": current_app.config["STRAVA_CLIENT_SECRET"],
                "grant_type": "refresh_token",
                "refresh_token": token.refresh_token,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        token.access_token = data["access_token"]
        token.refresh_token = data["refresh_token"]
        token.expires_at = datetime.utcfromtimestamp(data["expires_at"])
        token.raw_data = json.dumps(data)
        db.session.commit()

    return token.access_token


def sync_activities(days_back: int = 30) -> dict:
    """Fetch recent activities from Strava and store in DB."""
    access_token = _get_valid_token()

    after_timestamp = int(
        (datetime.utcnow() - timedelta(days=days_back)).timestamp()
    )

    all_activities = []
    page = 1
    per_page = 50

    while True:
        resp = requests.get(
            f"{STRAVA_API_BASE}/athlete/activities",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "after": after_timestamp,
                "page": page,
                "per_page": per_page,
            },
            timeout=15,
        )
        resp.raise_for_status()
        activities = resp.json()

        if not activities:
            break

        all_activities.extend(activities)
        if len(activities) < per_page:
            break
        page += 1

    # Store in DB
    new_count = 0
    updated_count = 0

    for act in all_activities:
        strava_id = act["id"]
        existing = StravaActivity.query.filter_by(strava_id=strava_id).first()

        if not existing:
            existing = StravaActivity(strava_id=strava_id)
            db.session.add(existing)
            new_count += 1
        else:
            updated_count += 1

        start_dt = datetime.fromisoformat(
            act["start_date_local"].replace("Z", "+00:00")
        )

        existing.activity_type = act.get("type", act.get("sport_type", "Unknown"))
        existing.name = act.get("name", "")
        existing.date = start_dt.date()
        existing.start_time = start_dt.time()
        existing.duration_seconds = act.get("elapsed_time")
        existing.distance_meters = act.get("distance")
        existing.elevation_gain = act.get("total_elevation_gain")
        existing.average_heartrate = act.get("average_heartrate")
        existing.suffer_score = act.get("suffer_score")
        existing.synced_at = datetime.utcnow()
        existing.raw_data = json.dumps(act)

    db.session.commit()

    return {
        "total": len(all_activities),
        "new": new_count,
        "updated": updated_count,
    }


def get_connection_status() -> dict:
    """Check if Strava is connected and token is valid."""
    token = OAuthToken.query.filter_by(service="strava").first()
    if not token:
        return {"connected": False}

    expired = token.expires_at and token.expires_at < datetime.utcnow()
    return {
        "connected": True,
        "expires_at": token.expires_at.isoformat() if token.expires_at else None,
        "expired": expired,
    }
