import os
import logging
from datetime import datetime, time
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
raw_id = os.getenv("MI_TELEGRAM_ID")

if not TOKEN or not raw_id:
    raise ValueError("❌ Error: TELEGRAM_TOKEN or MI_TELEGRAM_ID missing in .env file!")

MY_ID = int(raw_id)

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Conversation states
EVENT, TYPE, PRIORITY, TIME = range(4)

# Priority to Emoji mapping dictionary
PRIORITY_EMOJIS = {
    "Low": "🟢 Low",
    "Medium": "🟡 Medium",
    "High": "🔴 High"
}

# Security filter to ensure only you can use the bot
def is_authorized_user(update: Update) -> bool:
    return update.effective_user.id == MY_ID

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_authorized_user(update):
        await update.message.reply_text("You are not authorized to use this assistant.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "Hey! What event are we going to add today?\n"
        "What is the name of the **Event** or task?"
    )
    return EVENT

async def receive_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['event'] = update.message.text
    
    # Keyboard with the specific categories requested
    keyboard = [['Work', 'Production'], ['Projects', 'House']]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text("Perfect. What **Type** is it?", reply_markup=markup)
    return TYPE

async def receive_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['type'] = update.message.text
    
    # Updated to your requested priorities
    keyboard = [['High', 'Medium', 'Low']]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text("What is the **Priority**?", reply_markup=markup)
    return PRIORITY

async def receive_priority(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Save the exact text selected ('High', 'Medium' or 'Low')
    context.user_data['priority'] = update.message.text
    
    await update.message.reply_text(
        "What time do you want me to send the reminder? (Use HH:MM format, e.g., 17:30 or 09:00)",
        reply_markup=ReplyKeyboardRemove()
    )
    return TIME

# This function runs when the scheduled time is reached
async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    
    # Get the priority and match it with its custom emoji (defaults to info emoji if something goes wrong)
    priority_text = data['priority']
    priority_display = PRIORITY_EMOJIS.get(priority_text, f"ℹ️ {priority_text}")
    
    message = (
        f"⏰ **SCHEDULED REMINDER** ⏰\n\n"
        f"📌 **Event:** {data['event']}\n"
        f"📂 **Type:** {data['type']}\n"
        f"🔥 **Priority:** {priority_display}"
    )
    await context.bot.send_message(chat_id=MY_ID, text=message, parse_mode="Markdown")

async def receive_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    time_text = update.message.text
    try:
        # Validate time format
        time_obj = datetime.strptime(time_text, "%H:%M").time()
        
        # Save current data structurally
        reminder_data = {
            'event': context.user_data['event'],
            'type': context.user_data['type'],
            'priority': context.user_data['priority']
        }
        
        # Schedule daily alarm (JobQueue)
        context.job_queue.run_daily(
            send_reminder,
            time=time_obj,
            data=reminder_data,
            name=f"job_{reminder_data['event']}"
        )
        
        # Just a nice touch: show the emoji also in the confirmation message
        priority_emoji = PRIORITY_EMOJIS.get(reminder_data['priority'], "")
        await update.message.reply_text(
            f"✅ All set!\n"
            f"I will remind you about '{reminder_data['event']}' ({priority_emoji}) every day at {time_text}."
        )
        
    except ValueError:
        await update.message.reply_text("Incorrect time format. Please use HH:MM (e.g., 14:05). Try again:")
        return TIME
        
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Process canceled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main():
    # Modificamos esta línea para inicializar correctamente el JobQueue
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("new", start)],
        states={
            EVENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_event)],
            TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_type)],
            PRIORITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_priority)],
            TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_time)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    
    print("Assistant running... Type /new in Telegram")
    app.run_polling()

if __name__ == "__main__":
    main()