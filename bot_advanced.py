#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram Content Aggregator Bot - Advanced Version
Fetches content from Telegram channels and reposts with AI enhancement
"""

import os
import sys
import asyncio
import logging
import requests
import random
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
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TARGET_CHANNEL = os.getenv("TELEGRAM_CHANNEL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")

# القنوات المصدر
SOURCE_CHANNELS = os.getenv("SOURCE_CHANNELS", "").split(",")
SOURCE_CHANNELS = [ch.strip() for ch in SOURCE_CHANNELS if ch.strip()]

# عدد المنشورات للجلب من كل قناة
POSTS_LIMIT = int(os.getenv("POSTS_LIMIT", "10"))

# ====== VALIDATION ======
if not all([BOT_TOKEN, TARGET_CHANNEL, OPENAI_API_KEY]):
    logger.error("❌ Missing: TELEGRAM_TOKEN, TELEGRAM_CHANNEL, OPENAI_API_KEY")
    sys.exit(1)

if not all([API_ID, API_HASH]):
    logger.error("❌ Missing: TELEGRAM_API_ID, TELEGRAM_API_HASH")
    logger.error("Get them from: https://my.telegram.org/apps")
    sys.exit(1)

if not SOURCE_CHANNELS:
    logger.error("❌ Missing: SOURCE_CHANNELS")
    logger.error("Add channel usernames separated by comma (e.g., TechNewsAR,AINews)")
    sys.exit(1)

# ====== TELETHON CLIENT ======
client = TelegramClient('bot_session', int(API_ID), API_HASH)

# ====== FETCH FROM TELEGRAM ======
async def fetch_recent_posts(channel_username: str, limit: int = 10) -> List[Message]:
    """جلب آخر منشورات من قناة تيليغرام"""
    try:
        logger.info(f"📥 Fetching from @{channel_username}...")
        
        messages = []
        async for message in client.iter_messages(channel_username, limit=limit):
            if message.text and len(message.text) > 50:  # فقط المنشورات النصية الطويلة
                messages.append(message)
        
        logger.info(f"✅ Fetched {len(messages)} posts from @{channel_username}")
        return messages
        
    except Exception as e:
        logger.error(f"❌ Error fetching @{channel_username}: {str(e)}")
        return []

async def get_content_from_sources() -> Optional[str]:
    """جلب محتوى من جميع القنوات المصدر"""
    all_messages = []
    
    for channel in SOURCE_CHANNELS:
        messages = await fetch_recent_posts(channel, POSTS_LIMIT)
        all_messages.extend(messages)
    
    if not all_messages:
        logger.warning("⚠️ No content fetched from any source channel")
        return None
    
    # اختيار منشور عشوائي
    selected = random.choice(all_messages)
    
    logger.info(f"✅ Selected post from @{selected.chat.username or 'unknown'}")
    logger.info(f"📅 Posted at: {selected.date}")
    logger.info(f"📏 Length: {len(selected.text)} characters")
    
    return selected.text

# ====== AI PROCESSING ======
async def ai_rewrite_content(text: str, max_retries: int = 3) -> Optional[str]:
    """إعادة صياغة المحتوى بالذكاء الاصطناعي"""
    
    prompt = f"""
أنت محرر محتوى احترافي وخبير في إعادة الصياغة. مهمتك:

1. اقرأ المحتوى التالي بعناية
2. أعد صياغته بأسلوب جذاب ومختلف **تماماً** عن الأصل
3. إذا كان النص بالإنجليزية، ترجمه إلى العربية
4. احتفظ بالمعلومات والحقائق المهمة
5. اكتب عنوان قوي وجذاب مع إيموجي مناسب
6. استخدم أسلوب صحفي احترافي
7. اجعل الملخص في 3-5 أسطر فقط
8. أضف قيمة للقارئ (تحليل بسيط، سياق، أهمية الخبر)

المحتوى الأصلي:
---
{text}
---

اكتب الرد بصيغة Markdown مع عنوان وإيموجي:
### العنوان الجذاب 🚀
المحتوى المعاد صياغته هنا بأسلوب احترافي...
"""
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🤖 AI rewriting (attempt {attempt}/{max_retries})...")
            
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.8,
                    "max_tokens": 700
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()['choices'][0]['message']['content']
                logger.info("✅ AI rewriting successful")
                return result.strip()
            else:
                logger.warning(f"⚠️ OpenAI API error: {response.status_code}")
                logger.warning(f"Response: {response.text}")
                
        except requests.exceptions.Timeout:
            logger.warning(f"⏱️ Request timeout (attempt {attempt}/{max_retries})")
        except Exception as e:
            logger.error(f"❌ Unexpected error: {str(e)}")
        
        if attempt < max_retries:
            wait_time = attempt * 2
            logger.info(f"⏳ Waiting {wait_time}s before retry...")
            await asyncio.sleep(wait_time)
    
    logger.error("❌ AI processing failed after all retries")
    return None

# ====== TELEGRAM SENDER ======
def send_to_channel(message: str, max_retries: int = 3) -> bool:
    """نشر رسالة على قناة تيليغرام"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"📤 Publishing to channel (attempt {attempt}/{max_retries})...")
            
            response = requests.post(
                url,
                json={
                    "chat_id": TARGET_CHANNEL,
                    "text": message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": False
                },
                timeout=15
            )
            
            if response.status_code == 200:
                logger.info("✅ Message published successfully!")
                return True
            else:
                error_msg = response.json().get('description', 'Unknown error')
                logger.warning(f"⚠️ Telegram API error: {error_msg}")
                
        except requests.exceptions.Timeout:
            logger.warning(f"⏱️ Request timeout (attempt {attempt}/{max_retries})")
        except Exception as e:
            logger.error(f"❌ Unexpected error: {str(e)}")
        
        if attempt < max_retries:
            wait_time = attempt * 2
            logger.info(f"⏳ Waiting {wait_time}s before retry...")
            import time
            time.sleep(wait_time)
    
    logger.error("❌ Failed to publish message after all retries")
    return False

# ====== MAIN EXECUTION ======
async def main():
    """Main execution flow"""
    logger.info("=" * 70)
    logger.info("🚀 Telegram Content Aggregator Bot - Advanced Mode")
    logger.info(f"📅 Timestamp: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info(f"📢 Target channel: {TARGET_CHANNEL}")
    logger.info(f"📡 Source channels: {', '.join(SOURCE_CHANNELS)}")
    logger.info(f"📊 Posts limit per channel: {POSTS_LIMIT}")
    logger.info("=" * 70)
    
    try:
        # Step 1: Connect to Telegram
        logger.info("🔌 Connecting to Telegram...")
        await client.start(bot_token=BOT_TOKEN)
        logger.info("✅ Connected successfully")
        
        # Step 2: Fetch content from source channels
        logger.info("📥 Fetching content from source channels...")
        raw_content = await get_content_from_sources()
        
        if not raw_content:
            logger.error("❌ No content available. Exiting.")
            return False
        
        logger.info(f"✅ Content fetched successfully")
        logger.info(f"📄 Preview (first 200 chars): {raw_content[:200]}...")
        
        # Step 3: Process with AI
        logger.info("🤖 Processing content with AI...")
        rewritten_content = await ai_rewrite_content(raw_content)
        
        if not rewritten_content:
            logger.error("❌ AI processing failed. Exiting.")
            return False
        
        # Step 4: Add footer with timestamp
        footer = f"\n\n🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        final_message = rewritten_content + footer
        
        logger.info("📝 Final message prepared:")
        logger.info("-" * 70)
        logger.info(final_message)
        logger.info("-" * 70)
        
        # Step 5: Publish to target channel
        logger.info("📤 Publishing to target channel...")
        success = send_to_channel(final_message)
        
        if success:
            logger.info("=" * 70)
            logger.info("✨ Mission accomplished! Content published successfully.")
            logger.info("=" * 70)
            return True
        else:
            logger.error("=" * 70)
            logger.error("💔 Mission failed. Publishing unsuccessful.")
            logger.error("=" * 70)
            return False
            
    except Exception as e:
        logger.error(f"❌ Fatal error in main execution: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False
    finally:
        logger.info("🔌 Disconnecting from Telegram...")
        await client.disconnect()
        logger.info("✅ Disconnected")

# ====== ENTRY POINT ======
if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        logger.info("\n⚠️ Bot stopped by user (Ctrl+C)")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
