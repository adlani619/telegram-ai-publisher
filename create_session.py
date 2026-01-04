from telethon import TelegramClient

API_ID = 34804155
API_HASH = "489dda93b86a5537e65f347841e7390b"

with TelegramClient("user_session", API_ID, API_HASH) as client:
    print("✅ Session created successfully!")
