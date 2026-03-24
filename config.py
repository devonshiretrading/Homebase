import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///lifeblock.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Strava
    STRAVA_CLIENT_ID = os.environ.get("STRAVA_CLIENT_ID")
    STRAVA_CLIENT_SECRET = os.environ.get("STRAVA_CLIENT_SECRET")
    STRAVA_REDIRECT_URI = os.environ.get(
        "STRAVA_REDIRECT_URI", "http://localhost:5001/auth/strava/callback"
    )

    # Microsoft Graph (Office 365)
    MS_CLIENT_ID = os.environ.get("MS_CLIENT_ID")
    MS_CLIENT_SECRET = os.environ.get("MS_CLIENT_SECRET")
    MS_TENANT_ID = os.environ.get("MS_TENANT_ID")

    # Outlook ICS feed
    OUTLOOK_ICS_URL = os.environ.get("OUTLOOK_ICS_URL")

    # Location (set via browser geolocation, stored in DB)
    DEFAULT_LAT = os.environ.get("DEFAULT_LAT")
    DEFAULT_LON = os.environ.get("DEFAULT_LON")
