# GCal-to-Slack Holiday Status Updater

This project is a Python script that integrates with Google Calendar and Slack to automatically update your Slack status based on upcoming holiday events. It supports multi-day holidays by merging consecutive all-day events with similar summaries and provides notifications up to 3 days in advance.

Notes:
- This script is designed to work with all-day events only. It may not work as expected with events that have specific start and end times.
- Tested using calendar events from the [OfficeHolidays](https://www.officeholidays.com/)


## Features
- **Fetch All-Day Events**: Retrieves holiday events from a specified Google Calendar.

- **Merge Similar Events**: Normalizes event summaries (removing suffixes like "Holiday", "Day", and "(Regional Holiday)") and merges consecutive events with similar names.

- **Slack Status Updates**:
  - **Today’s Holiday**: If today is a holiday, update the Slack status with a red circle emoji.

   - **Upcoming Holiday**: If today isn’t a holiday, check sequentially for the next upcoming holiday (tomorrow, then 2 days ahead, then 3 days ahead) and update the Slack status with a large yellow circle emoji.

**Notifications**: Sends a notification using ntfy.sh when the Slack status is updated.

## Prerequisites
- Python 3.x
- Google Calendar API Credentials:
  - Enable the Google Calendar API in your Google Cloud project.
  - Create a service account and download the JSON credentials file.
  - Allow the service account to access your Google Calendar.
- Slack API Token:
  - Generate a Slack API token with permissions to update your Slack profile status.

## Installation
1. Clone the repository:
```bash
git clone https://github.com/rizaljamhari/gcal-to-slack.git
cd gcal-to-slack
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Configuration
1. **Google Calendar API**:
   - Place your service account credentials file in the repository root and name it gcalendar-to-slack-credentials.json (or update the script with your file path).
   - Update the CALENDAR_ID in the script with your target Google Calendar ID:
   ```python
   CALENDAR_ID = 'your-calendar-id@group.calendar.google.com'
   ```
2. **Slack API**:
   - Update the Slack token in the script:
   ```python
   SLACK_TOKEN = 'xoxp-your-slack-token'
   ```
3. **Notification** (Optional):
    - The script sends notifications via ntfy.sh. Update your ntfy topic in the script:
    ```python
    NTFY_TOPIC = 'your-ntfy-topic'
    ```

## Running the Script
You can run the script manually with:
```bash
python run.py
```

The script will:
- Fetch and merge holiday events from today through 3 days ahead.
- Check if today is a holiday. If so, it updates your Slack status immediately.
- If not, it sequentially checks for a holiday tomorrow, then 2 days ahead, then 3 days ahead, updating your Slack status with an upcoming notice for the first match found.

## Cron Job Setup
To run the script automatically every day at 00:05 (local time), add the following entry to your crontab (adjust the path to your run.py accordingly):
```bash
5 0 * * * /usr/bin/python3 /path/to/gcal-to-slack/run.py
```
*Note*: Even if your server’s timezone is set to Asia/Kuala_Lumpur (GMT+8) while the Google Calendar is in UTC, the script is designed to work with all-day events, so no additional timezone conversion is required.

