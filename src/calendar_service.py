import os
import pickle
from datetime import datetime, UTC
import json
from typing import Dict, List, Optional, Any
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from models import CalendarEvent
from logger_config import setup_logger
from google.oauth2.service_account import Credentials

# Get configured logger
logger = setup_logger("calendar_service")

# Define access scopes
SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarService:
    """Service for working with Google Calendar API"""

    def __init__(self):
        # Get path to src directory
        src_dir = os.path.dirname(os.path.abspath(__file__))
        # Get path to the root directory of the project (one level above src)
        root_dir = os.path.dirname(src_dir)

        # Set file paths
        self.credentials_file = os.path.join(root_dir, "credentials.json")
        self.token_file = os.path.join(root_dir, "token.pickle")

        self.creds = None
        self.service = None

    def authenticate(self):
        """Authentication in Google Calendar API"""
        creds = None

        # Check for token existence
        if os.path.exists(self.token_file):
            with open(self.token_file, "rb") as token:
                creds = pickle.load(token)

        # If there are no valid credentials, request them
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save credentials for the next run
            with open(self.token_file, "wb") as token:
                pickle.dump(creds, token)

        # Create service
        self.service = build("calendar", "v3", credentials=creds)
        logger.info("Authentication in Google Calendar API successfully completed")

    def create_event(self, event: CalendarEvent, calendar_id="primary"):
        """Creates an event in Google Calendar"""

        custom_reminder = {
            "useDefault": False,
            "overrides": [
                # {"method": "email", "minutes": 30},  # Email 30 minutes before event
                {
                    "method": "popup",
                    "minutes": 10,
                },  # Popup notification 10 minutes before
            ],
        }

        if not self.service:
            self.authenticate()

        try:
            google_event = event.to_google_event()

            # Add reminder settings to the event body
            google_event["reminders"] = custom_reminder

            created_event = (
                self.service.events()
                .insert(
                    calendarId=calendar_id, body=google_event, sendNotifications=True
                )
                .execute()
            )
            logger.info(f"Event created: {created_event.get('htmlLink')}")
            return created_event
        except HttpError as error:
            logger.error(f"Error creating event: {error}")
            return None

    def get_events(self, max_results=10, calendar_id="primary"):
        """Gets a list of upcoming events from the calendar"""
        if not self.service:
            self.authenticate()

        try:
            now = datetime.now(UTC).isoformat()
            events_result = (
                self.service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=now,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = events_result.get("items", [])
            return events
        except HttpError as error:
            logger.error(f"Error getting events: {error}")
            return []
