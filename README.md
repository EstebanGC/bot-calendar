# 📅 Telegram Google Calendar Assistant Bot

A lightweight, automated Telegram bot written in Python that seamlessly integrates with **Google Calendar**. It enables event scheduling via interactive Telegram chat commands and delivers precise, real-time reminder alarms directly to your Telegram chat when events start.

---

## ✨ Features

* **Real-time Reminders:** Sets precise background timers to notify you the exact moment an event starts.
* **Interactive Event Creation (`/new`):** Step-by-step chat wizard to create events directly in your primary Google Calendar.
* **Instant Sync (`/start`):** Synchronizes calendar entries for upcoming days and schedules missing reminders.
* **Access Control:** User authorization check restricts bot access exclusively to your Telegram User ID.
* **24/7 Cloud Ready:** Embedded lightweight HTTP dummy server to bypass health check timeouts on free hosting platforms like Render.

---

## 🛠️ Prerequisites

* **Python 3.10+**
* A Telegram Bot Token from **[@BotFather](https://t.me/BotFather)**.
* Your numeric Telegram User ID (retrievable via **[@userinfobot](https://t.me/userinfobot)**).
* A **Google Cloud Platform (GCP)** project with the **Google Calendar API** enabled.

---

## 🚀 Local Installation & Setup

### 1. Clone the Repository
```bash
git clone [https://github.com/EstebanGC/bot-calendar.git](https://github.com/EstebanGC/bot-calendar.git)
cd bot-calendar