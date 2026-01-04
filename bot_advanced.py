#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram Content Aggregator Bot - Advanced Version
Fetches content from Telegram channels and reposts with AI enhancement
Enhanced logging for debugging GitHub Actions publishing issues
"""

import os
import sys
import asyncio
import logging
import requests
import random
import base64
from datetime import datetime
from typing import Optional, List
from telethon import TelegramClient
from telethon.tl.types import Message

# ====== LOGGING SETUP ======
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ====== CONFIGURATION ======
TARGET_CHANNEL = os.getenv("TELEGRAM_CHANNEL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
USER_SESSION_BASE64 = os.getenv("USER_SESSION_BASE64")
SOURCE_CHANNELS = os.getenv("SOURCE_CHANNELS", "").split(",")
SOURCE_CHANNELS = [ch.strip() for ch in SOURCE_CHANNELS if ch.strip()]
POSTS_LIMIT = int(os.getenv("POSTS_LIMIT", "10"))

# ====== VALIDATION ======
if not all([TARGET_CHANNEL, OPENAI_API_KEY, API_ID, API_HASH, USER_SESSION_BASE64]):
    logger.error("❌ Missing one of the required secrets: USER_SESSION_BASE64, TELEGRAM_CHANNEL, OPENAI_API_KEY, TELEGRAM_API_ID, TELEGRAM_API_HASH")
    sys.exit(1)

if not SOURCE_CHANNELS:
    logger.error("❌ Missing: SOURCE_CHANNELS")
    sys.exit(1)

# ====== DECODE USER SESSION ======
with open("user_session.session", "wb") as f:
    f.write(base64.b64decode(USER_SESSION_BASE64))
logger.info("✅ USER_SESSION_BASE64 decoded to user_session.session")

# ====== TELETHON CLIENT ======
client = TelegramClient('user_session', int(API_ID), API_HASH)

# ====== FETCH FROM TELEGRAM ======
async def fetch_recent_posts(channel_username: str, limit: int = 10) -> List[Message]:
    messages = []
    try:
        logger.info(f"📥 Fetching from @{channel_username}...")
        async for message in client.iter_messages(channel_username, limit=limit):
            if message.text and len(message.text) > 50:
                messages.append(message)
        if messages:
            logger.info(f"✅ Fetched {len(messages)} posts from @{channel_username}")
        else:
            logger.warning(f"⚠️ No posts fetched from @{channel_username}")
    except Exception as e:
        logger.error(f"❌ Error fetching @{channel_username}: {str(e)}")
    return messages

async def get_content_from_sources() -> Optional[str]:
    all_messages = []
    for channel in SOURCE_CHANNELS:
        msgs = await fetch_recent_posts(channel, POSTS_LIMIT)
        all_messages.extend(msgs)
        logger.info(f"📊 Total messages collected so far: {len(all_messages)}")
    if not all_messages:
        logger.warning("⚠️ No content fetched from any source channel")
        return None
    selected = random.choice(all_messages)
    logger.info(f"✅ Selected post from @{selected.chat.username or 'unknown'} ({len(selected.text)} chars)")
    return selected.text

# ====== AI PROCESSING ======
async def ai_rewrite_content(text: str, max_retries: int = 3) -> Optional[str]:
    prompt = f"""
أنت محرر محتوى احترافي وخبير في إعادة الصياغة. مهمتك:

1. اقرأ المحتوى التالي بعناية
2. أعد صياغته بأسلوب جذاب ومختلف تماماً عن الأصل
3. إذا كان النص بالإنجليزية، ترجمه إلى العربية
4. احتفظ بالمعلومات والحقائق المهمة
5. اكتب عنوان قوي وجذاب مع إيموجي مناسب
6. استخدم أسلوب صحفي احترافي
7. اجعل الملخص في 3-5 أسطر فقط
8. أضف قيمة للقارئ (تحليل بسيط، سياق، أهمية الخبر)

المحتوى الأصلي:
{text}
"""
    for attempt in range(1, max_retries+1):
        try:
            logger.info(f"🤖 AI rewriting (attempt {attempt}/{max_retries})...")
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                json={"model": "gpt-4o-mini", "messages":[{"role":"user","content":prompt}], "temperature":0.8, "max_tokens":700},
                timeout=30
            )
            if response.status_code == 200:
                logger.info("✅ AI rewriting successful")
                return response.json()['choices'][0]['message']['content'].strip()
            else:
                logger.warning(f"⚠️ OpenAI API error: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"❌ Unexpected error: {str(e)}")
        if attempt < max_retries:
            await asyncio.sleep(attempt*2)
    logger.error("❌ AI processing failed after all retries")
    return None

# ====== TELEGRAM SENDER ======
async def test_channel_access():
    try:
        msg = await client.send_message(TARGET_CHANNEL, "🟢 اختبار صلاحية النشر")
        logger.info(f"✅ Test message sent to {TARGET_CHANNEL}")
        return True
    except Exception as e:
        logger.error(f"❌ Cannot send to {TARGET_CHANNEL}: {str(e)}")
        return False

async def send_to_channel(message: str) -> bool:
    try:
        await client.send_message(TARGET_CHANNEL, message)
        logger.info("✅ Message published successfully!")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to publish message: {str(e)}")
        return False

# ====== MAIN EXECUTION ======
async def main():
    logger.info("="*70)
    logger.info("🚀 Telegram Content Aggregator Bot - Debug Mode")
    await client.start()
    logger.info("✅ Connected successfully")

    if not await test_channel_access():
        logger.error("❌ Cannot post to target channel. Exiting.")
        await client.disconnect()
        return False

    raw_content = await get_content_from_sources()
    if not raw_content:
        logger.error("❌ No content fetched. Exiting.")
        await client.disconnect()
        return False

    rewritten = await ai_rewrite_content(raw_content)
    if not rewritten:
        logger.error("❌ AI processing failed. Exiting.")
        await client.disconnect()
        return False

    final_message = rewritten + f"\n\n🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    await send_to_channel(final_message)

    await client.disconnect()
    logger.info("✅ Finished all tasks")
    return True

if __name__ == "__main__":
    asyncio.run(main())
