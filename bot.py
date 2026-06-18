import os
import logging
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Librerías de Google API
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

# Si modificas estos SCOPES, elimina el archivo token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def get_calendar_service():
    """Autentica al usuario y devuelve el servicio de Google Calendar."""
    creds = None
    # El archivo token.json almacena los tokens de acceso del usuario
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # Si no hay credenciales válidas disponibles, deja que el usuario inicie sesión.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                raise FileNotFoundError("❌ Error: 'credentials.json' not found. Please download it from Google Cloud Console.")
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Guardar las credenciales para la próxima ejecución
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds)

# Security filter
def is_authorized_user(update: Update) -> bool:
    return update.effective_user.id == MY_ID

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized_user(update):
        await update.message.reply_text("You are not authorized to use this assistant.")
        return
    await update.message.reply_text("Hi! I am now connected to your Google Calendar. I will check your events automatically.")

async def check_calendar_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Revisa los eventos de Google Calendar y envía recordatorios."""
    try:
        service = get_calendar_service()
        
        # Definir el rango de tiempo (desde ahora hasta el final del día de hoy)
        now = datetime.now(timezone.utc)
        end_of_day = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59)

        events_result = service.events().list(
            calendarId='primary',
            timeMin=now.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])

        if not events:
            return

        for event in events:
            # Evitar enviar duplicados usando el ID del evento
            job_name = f"reminder_{event['id']}"
            current_jobs = context.job_queue.get_jobs_by_name(job_name)
            
            if not current_jobs:
                start_time_str = event['start'].get('dateTime', event['start'].get('date'))
                # Limpiar formato de fecha para mostrarlo amigablemente
                display_time = start_time_str
                if 'T' in start_time_str:
                    display_time = start_time_str.split('T')[1][:5]

                message = (
                    f"⏰ **UPCOMING CALENDAR EVENT** ⏰\n\n"
                    f"📌 **Event:** {event.get('summary', 'No Title')}\n"
                    f"🕒 **Time:** {display_time}\n"
                    f"📝 **Description:** {event.get('description', 'No description')}"
                )
                
                # Enviar la notificación de inmediato al detectar el evento
                await context.bot.send_message(chat_id=MY_ID, text=message, parse_mode="Markdown")
                
                # Guardamos un registro ficticio en el job_queue para saber que ya se notificó
                context.job_queue.run_once(lambda x: None, when=1, name=job_name)

    except Exception as e:
        logging.error(f"Error checking calendar: {e}")

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    
    # Registrar la tarea automática para que revise Google Calendar cada 15 minutos (900 segundos)
    app.job_queue.run_repeating(check_calendar_job, interval=900, first=10)

    print("Assistant running with Google Calendar... Type /start in Telegram")
    app.run_polling()

if __name__ == "__main__":
    main()