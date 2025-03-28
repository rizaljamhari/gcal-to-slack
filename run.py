import datetime
import requests
import re
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Google Calendar API settings
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
SERVICE_ACCOUNT_FILE = '<path-to-service-account-json>'
CALENDAR_ID = '<calendar-id-to-monitor>' # https://docs.simplecalendar.io/find-google-calendar-id/

# Slack API settings
SLACK_TOKEN = '<slack-app-token>' # https://api.slack.com/apps
client = WebClient(token=SLACK_TOKEN)

# ntify.sh settings
NTFY_TOPIC = '<ntfy-topic>'

def normalize_summary(summary):
    """
    Normalize an event summary by converting to lowercase and removing known suffixes:
    ' Holiday', ' Day', and ' (regional holiday)'.
    """
    s = summary.lower().strip()
    # Define suffix patterns to remove.
    # Using regex ensures we only remove these suffixes at the end of the string.
    suffix_patterns = [r'\s+holiday$', r'\s+day$', r'\s+\(regional holiday\)$']
    for pattern in suffix_patterns:
        s = re.sub(pattern, '', s)
    return s.strip()

def is_same_summary(summary_a, summary_b):
    """
    Returns True if the normalized version of one summary is a substring
    of the normalized version of the other.
    """
    norm_a = normalize_summary(summary_a)
    norm_b = normalize_summary(summary_b)
    return (norm_a in norm_b) or (norm_b in norm_a)

def get_events_for_range(start_date, end_date):
    """
    Fetches all all-day events between start_date and end_date (inclusive),
    then merges consecutive single-day events that share the same (or subset) summary
    into a multi-day holiday.

    Returns a list of dicts, each containing:
        {
            "summary": str,
            "description": str,
            "start": date,
            "end": date  # exclusive
        }
    """
    credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('calendar', 'v3', credentials=credentials)

    # timeMin: midnight at start_date
    # timeMax: midnight at end_date + 1 (so we include the entire end_date)
    start_dt = datetime.datetime.combine(start_date, datetime.time.min)
    end_dt = datetime.datetime.combine(end_date + datetime.timedelta(days=1), datetime.time.min)

    events_result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=start_dt.isoformat() + 'Z',
        timeMax=end_dt.isoformat() + 'Z',
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    raw_events = events_result.get('items', [])

    # Collect events by a "canonical" summary key
    events_by_summary = {}

    for ev in raw_events:
        # Only handle all-day events that have a 'date' field in start/end
        if 'date' in ev.get('start', {}):
            summary = ev['summary']
            start_str = ev['start']['date']  # YYYY-MM-DD
            end_str = ev['end']['date']      # YYYY-MM-DD (exclusive)
            start_d = datetime.datetime.strptime(start_str, '%Y-%m-%d').date()
            end_d   = datetime.datetime.strptime(end_str, '%Y-%m-%d').date()

            description = ev.get('description', '')
            # Clean up description if needed
            if '\n' in description:
                description = description.split('\n')[0]

            # Attempt to find an existing summary key that matches (subset)
            found_key = None
            for existing_summary in events_by_summary:
                if is_same_summary(summary, existing_summary):
                    found_key = existing_summary
                    break

            if found_key is None:
                # If no matching key, use the current summary as a new key
                events_by_summary[summary] = [{
                    "summary": summary,
                    "description": description,
                    "start": start_d,
                    "end": end_d
                }]
            else:
                # Merge under the found key
                events_by_summary[found_key].append({
                    "summary": summary,
                    "description": description,
                    "start": start_d,
                    "end": end_d
                })

    # Merge consecutive/overlapping day events under each summary key
    merged_events = []
    for summary_key, ev_list in events_by_summary.items():
        # Sort by start date
        ev_list.sort(key=lambda x: x["start"])

        current_start = ev_list[0]["start"]
        current_end   = ev_list[0]["end"]
        current_desc  = ev_list[0]["description"]
        # We'll keep the "main" summary as the summary_key
        # (though you could choose the first or the shortest if you like)

        merged = []
        for i in range(1, len(ev_list)):
            nxt = ev_list[i]
            if nxt["start"] <= current_end:
                # They touch or overlap, extend the end if needed
                if nxt["end"] > current_end:
                    current_end = nxt["end"]
            else:
                # No overlap, push the previous chunk and start a new one
                merged.append({
                    "summary": summary_key,
                    "description": current_desc,
                    "start": current_start,
                    "end": current_end
                })
                current_start = nxt["start"]
                current_end   = nxt["end"]
                current_desc  = nxt["description"]

        # Push the last chunk
        merged.append({
            "summary": summary_key,
            "description": current_desc,
            "start": current_start,
            "end": current_end
        })

        merged_events.extend(merged)

    return merged_events

def find_holiday_for_date(events, target_date):
    """
    Given a list of merged holiday events (with date objects in 'start' and 'end'),
    returns the event whose range includes target_date, or None if none match.
    """
    for e in events:
        if e["start"] <= target_date < e["end"]:
            return e
    return None

def notify_to_ntfy(event):
    """
    Sends a simple notification to ntfy.sh indicating the Slack status update.
    """
    ntfy_message = f"PH: {event['summary']}"
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=ntfy_message,
            headers={
                "Title": "Slack status updated",
                "Tags": "mega",
            }
        )
    except requests.exceptions.RequestException as e:
        print(f"Error sending ntfy: {e}")

def update_slack_status(event):
    """
    Updates Slack status for TODAY's holiday using a red circle emoji.
    The status text is "PH: {summary}".
    Expires at midnight of the event's end date (exclusive).
    """
    end_in_unix = datetime.datetime.combine(event["end"], datetime.time.min).timestamp()

    status_text = f"PH: {event['summary']}"
    status_emoji = ":red_circle:"
    status = {
        "status_text": status_text,
        "status_emoji": status_emoji,
        "status_expiration": int(end_in_unix)
    }
    try:
        client.users_profile_set(profile=status)
        notify_to_ntfy(event)
    except SlackApiError as e:
        print(f"Error updating Slack status: {e.response['error']}")

def update_slack_status_upcoming(event):
    """
    Updates Slack status for an UPCOMING holiday (e.g. tomorrow).
    Uses a large yellow circle emoji and the format:
        [Upcoming PH]: {d/m-d/m} {summary}
    or if single-day:
        [Upcoming PH]: {d/m} {summary}
    The status expires at midnight of the event's start date.
    """
    event_start = event["start"]
    # real_end is event["end"] - 1 day, because end is exclusive
    real_end = event["end"] - datetime.timedelta(days=1)

    if event_start == real_end:
        # single-day event
        date_range_str = f"{event_start.day}/{event_start.month}"
    else:
        # multi-day event
        date_range_str = f"{event_start.day}/{event_start.month}-{real_end.day}/{real_end.month}"

    status_text = f"Upcoming PH: [{date_range_str}] {event['summary']}"

    # Set expiration at midnight of event_start
    start_in_unix = datetime.datetime.combine(event_start, datetime.time.min).timestamp()

    status = {
        "status_text": status_text,
        "status_emoji": ":large_yellow_circle:",
        "status_expiration": int(start_in_unix)
    }
    try:
        client.users_profile_set(profile=status)
        notify_to_ntfy(event)
    except SlackApiError as e:
        print(f"Error updating Slack status: {e.response['error']}")

def main():
    today = datetime.date.today()
    # Fetch events from today up to today + 3 days
    merged_events = get_events_for_range(today, today + datetime.timedelta(days=3))

    # First, check if today is a holiday.
    event_today = find_holiday_for_date(merged_events, today)
    if event_today:
        update_slack_status(event_today)
    else:
        # Sequentially check for an upcoming holiday:
        # first tomorrow, then 2 days from now, then 3 days from now.
        for days_ahead in range(1, 4):
            target_date = today + datetime.timedelta(days=days_ahead)
            event_notice = find_holiday_for_date(merged_events, target_date)
            if event_notice:
                update_slack_status_upcoming(event_notice)
                break

if __name__ == '__main__':
    main()