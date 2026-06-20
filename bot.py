import os
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, 
    CommandHandler, 
    ContextTypes, 
    ConversationHandler, 
    MessageHandler, 
    filters
)

# Google API Libraries
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
MY_ID = int(os.getenv("MI_TELEGRAM_ID"))

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# If modifying these SCOPES, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar']

# Conversation states for /new
TITLE, DATE, START_TIME, DESCRIPTION = range(4)

def get_calendar_service():
    """Authenticates the user and returns the Google Calendar service object."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                raise FileNotFoundError("❌ Error: 'credentials.json' not found. Please download it from Google Cloud Console.")
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds)

def is_authorized_user(update: Update) -> bool:
    """Security filter to restrict access to your Telegram User ID."""
    return update.effective_user.id == MY_ID

async def send_event_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """This function is executed by the Job Queue precisely at the event start time."""
    data = context.job.data
    message = (
        f"🚨 **EVENT STARTING NOW** 🚨\n\n"
        f"📌 **Event:** {data['summary']}\n"
        f"🕒 **Time:** {data['display_time']}\n"
        f"📝 **Description:** {data['description']}"
    )
    await context.bot.send_message(chat_id=MY_ID, text=message, parse_mode="Markdown")

async def check_calendar_logic(bot, job_queue):
    """Central logic to fetch events and schedule precise reminder alarms."""
    try:
        service = get_calendar_service()
        
        now = datetime.now()
        # Fetch events for the next 3 days to guarantee capturing updates safely
        end_time = now + timedelta(days=3)

        events_result = service.events().list(
            calendarId='primary',
            timeMin=now.astimezone().isoformat(),
            timeMax=end_time.astimezone().isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])

        if not events:
            return "No upcoming events found for the next few days."

        scheduled_jobs = 0
        for event in events:
            job_name = f"reminder_{event['id']}"
            current_jobs = job_queue.get_jobs_by_name(job_name)
            
            # If the reminder isn't scheduled in the Job Queue yet, we set it up
            if not current_jobs:
                start_time_str = event['start'].get('dateTime', event['start'].get('date'))
                
                # Handle All-day events
                if 'T' not in start_time_str:
                    event_start_dt = datetime.strptime(start_time_str, "%Y-%m-%d").replace(hour=8, minute=0)
                    display_time = "All Day (Reminder at 08:00)"
                else:
                    # Parse timestamp with timezone offsets correctly
                    clean_ts = start_time_str
                    if clean_ts[-3] == ':':
                        clean_ts = clean_ts[:-3] + clean_ts[-2:]
                    
                    try:
                        event_start_dt = datetime.strptime(clean_ts, "%Y-%m-%dT%H:%M:%S%z").replace(tzinfo=None)
                    except ValueError:
                        event_start_dt = datetime.strptime(clean_ts[:19], "%Y-%m-%dT%H:%M:%S")
                    
                    display_time = start_time_str.split('T')[1][:5]

                # Calculate remaining seconds from "now" until the event starts
                time_diff = (event_start_dt - datetime.now()).total_seconds()
                
                # Skip if the event is already in the past
                if time_diff <= 0:
                    continue

                event_data = {
                    'summary': event.get('summary', 'No Title'),
                    'display_time': display_time,
                    'description': event.get('description', 'No description')
                }

                # Schedule the task to trigger in exactly 'time_diff' seconds
                job_queue.run_once(send_event_reminder, when=time_diff, name=job_name, data=event_data)
                scheduled_jobs += 1

        if scheduled_jobs > 0:
            return f"Checked! Scheduled {scheduled_jobs} new precise event alarms."
        else:
            return "Checked! All up-to-date alarms are already set."

    except Exception as e:
        logging.error(f"Error checking calendar: {e}")
        return f"Error connecting to Google Calendar: {e}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command to immediately synchronize calendar alerts."""
    if not is_authorized_user(update):
        await update.message.reply_text("You are not authorized to use this assistant.")
        return
    
    await update.message.reply_text("Hey! Syncing and scheduling your alarms immediately, please wait...")
    status_message = await check_calendar_logic(context.bot, context.job_queue)
    await update.message.reply_text(status_message)

async def check_calendar_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Repetitive background job for the Job Queue."""
    await check_calendar_logic(context.bot, context.job_queue)

# ================= CONVERSATION FLOW FOR THE /NEW COMMAND =================

async def new_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Initiates the new event creation wizard."""
    if not is_authorized_user(update):
        await update.message.reply_text("You are not authorized.")
        return ConversationHandler.END
    
    await update.message.reply_text("Let's create a new event! 🗓️\nWhat is the **Title/Summary** of the event?")
    return TITLE

async def new_event_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves the title and asks for the date."""
    context.user_data['title'] = update.message.text
    await update.message.reply_text("Got it! Now, what **date**? Please use **YYYY-MM-DD** format (e.g., 2026-06-25):")
    return DATE

async def new_event_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validates the date format and asks for the start time."""
    date_text = update.message.text
    try:
        datetime.strptime(date_text, "%Y-%m-%d")
        context.user_data['date'] = date_text
    except ValueError:
        await update.message.reply_text("❌ Invalid format. Please write the date using **YYYY-MM-DD** (e.g., 2026-06-25):")
        return DATE

    await update.message.reply_text("Perfect. What **time** does it start? Use **HH:MM** 24-hour format (e.g., 14:30 or 09:15):")
    return START_TIME

async def new_event_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validates the time format and asks for the description."""
    time_text = update.message.text
    try:
        datetime.strptime(time_text, "%H:%M")
        context.user_data['time'] = time_text
    except ValueError:
        await update.message.reply_text("❌ Invalid format. Please write the time using **HH:MM** 24-hour format (e.g., 18:00):")
        return START_TIME

    await update.message.reply_text("Great! Finally, give it a short **Description** (or type /skip to leave it empty):")
    return DESCRIPTION

async def new_event_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Saves description, uploads the event to Google Calendar, and triggers an immediate sync."""
    desc_text = update.message.text
    if desc_text.lower() == '/skip':
        context.user_data['description'] = "Created via Telegram Bot"
    else:
        context.user_data['description'] = desc_text

    await update.message.reply_text("Creating event in Google Calendar, please hold on...")
    
    try:
        service = get_calendar_service()
        
        # Combine local date and time strings
        start_datetime_str = f"{context.user_data['date']}T{context.user_data['time']}:00"
        start_dt = datetime.strptime(start_datetime_str, "%Y-%m-%dT%H:%M:%S")
        # Defaults to a 1-hour duration window
        end_dt = start_dt + timedelta(hours=1)
        
        # Retrieve the local operating system timezone context automatically
        local_tz = datetime.now().astimezone().tzinfo
        
        event_body = {
            'summary': context.user_data['title'],
            'description': context.user_data['description'],
            'start': {
                'dateTime': start_dt.replace(tzinfo=local_tz).isoformat(),
                'timeZone': 'America/Bogota', # Adjusted to your default context location
            },
            'end': {
                'dateTime': end_dt.replace(tzinfo=local_tz).isoformat(),
                'timeZone': 'America/Bogota',
            },
        }

        # Insert entry into Google Calendar
        created_event = service.events().insert(calendarId='primary', body=event_body).execute()
        
        await update.message.reply_text(f"✅ **Event created successfully!**\n🔗 [Open in Google Calendar]({created_event.get('htmlLink')})", parse_mode="Markdown")
        
        # Force an immediate alarm synchronization run to instantly queue up the newly added event alert
        await check_calendar_logic(context.bot, context.job_queue)

    except Exception as e:
        logging.error(f"Error creating event: {e}")
        await update.message.reply_text(f"❌ Error creating the event: {e}")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Aborts the interactive creation wizard."""
    await update.message.reply_text("Process cancelled. No event was created.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()

    # Setup the conversation handler mapping for /new
    new_event_handler = ConversationHandler(
        entry_points=[CommandHandler("new", new_event_start)],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_event_title)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_event_date)],
            START_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_event_time)],
            DESCRIPTION: [MessageHandler(filters.TEXT, new_event_description), CommandHandler("skip", new_event_description)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(new_event_handler)
    
    # Automatically tracks and schedules upcoming structural database updates every 15 minutes (900 seconds)
    app.job_queue.run_repeating(check_calendar_job, interval=900, first=10)

    print("Assistant running... Use /start to sync or /new to create events.")
    app.run_polling()

if __name__ == "__main__":
    main()