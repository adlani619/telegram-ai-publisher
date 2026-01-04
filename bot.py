#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram Content Aggregator Bot - Advanced Version
Uses Telethon to fetch real content from Telegram channels
"""

import os
import sys
import asyncio
import logging
import requests
import random
from datetime import datetime, timedelta
from typing import Optional, List
from telethon import TelegramClient
from telethon.tl.types import Message

# ====== LOGGING ======
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
# Bot Token للنشر
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TARGET_CHANNEL = os.getenv("TELEGRAM_CHANNEL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Telethon credentials للقراءة من القنوات
API_ID = os.getenv("TELEGRAM_API_ID")  # احصل عليه من my.telegram.org
API_HASH = os.getenv("TELEGRAM_API_HASH")  # احصل عليه من my.telegram.org

# القنوات المصدر
SOURCE_CHANNELS = os.getenv("SOURCE_CHANNELS", "").split(",")
SOURCE_CHANNELS = [ch.strip() for ch in SOURCE_CHANNELS if ch.strip()]

# عدد المنشورات للجلب
POSTS_LIMIT = int(os.getenv("POSTS_LIMIT", "10"))

# التحقق من المتغيرات
if not all([BOT_TOKEN, TARGET_CHANNEL, OPENAI_API_KEY]):
    logger.error("❌ Missing: TELEGRAM_TOKEN, TELEGRAM_CHANNEL, OPENAI_API_KEY")
    sys.exit(1)

if not all([API_ID, API_HASH]):
    logger.error("❌ Missing: TELEGRAM_API_ID, TELEGRAM_API_HASH")
    logger.error("Get them from: https://my.telegram.org/apps")
    sys.exit(1)

# ====== TELETHON CLIENT ======
client = TelegramClient('bot_session', int(API_ID), API_HASH)

async def fetch_recent_posts(channel_username: str, limit: int = 10) -> List[Message]:
    """جلب آخر منشورات من قناة تيليغرام"""
    try:
        logger.info(f"📥 Fetching from @{channel_username}...")
        
        # جلب آخر منشورات
        messages = []
        async for message in client.iter_messages(channel_username, limit=limit):
            if message.text:  # فقط المنشورات النصية
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
        logger.warning("⚠️ No content fetched from any source")
        return None
    
    # اختيار منشور عشوائي
    selected = random.choice(all_messages)
    
    logger.info(f"✅ Selected post from {selected.chat.username}")
    logger.info(f"📅 Posted at: {selected.date}")
    
    return selected.text

# ====== AI PROCESSING ======
def ai_rewrite_content(text: str, max_retries: int = 3) -> Optional[str]:
    """
    إعادة كتابة المحتوى بالذكاء الاصطناعي
    """
    prompt = f"""
    أنت محرر محتوى إبداعي. مهمتك:

    1. اقرأ المحتوى التالي
    2. أعد صياغته بأسلوب جذاب ومختلف تماماً
    3. احتفظ بالمعلومات المهمة
    4. اكتب عنوان قوي مع إيموجي
    5. اجعل الأسلوب احترافي وسلس
    6. 3-5 أسطر فقط
    7. إذا كان بالإنجليزية، ترجمه للعربية

    المحتوى الأصلي:
    {text}
    
    اكتب الرد بصيغة Markdown:
    ### العنوان 🚀
    المحتوى هنا...
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
                    "temperature": 0.8,  # إبداع أكثر
                    "max_tokens": 700
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()['choices'][0]['message']['content']
                logger.info("✅ AI rewriting successful")
                return result.strip()
            else:
                logger.warning(f"⚠️ OpenAI error: {response.text}")
                
        except Exception as e:
            logger.error(f"❌ Error: {str(e)}")
        
        if attempt < max_retries:
            asyncio.sleep(attempt * 2)
    
    return None

# ====== TELEGRAM SENDER ======
def send_to_channel(message: str, max_retries: int = 3) -> bool:
    """نشر على قناة تيليغرام"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"📤 Publishing (attempt {attempt}/{max_retries})...")
            
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
                logger.info("✅ Published successfully!")
                return True
            else:
                logger.warning(f"⚠️ Telegram error: {response.json().get('description')}")
                
        except Exception as e:
            logger.error(f"❌ Error: {str(e)}")
    
    return False

# ====== MAIN ======
async def main():
    """Main execution"""
    logger.info("=" * 60)
    logger.info("🚀 Telegram Content Aggregator - Advanced Mode")
    logger.info(f"📅 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info(f"📢 Target: {TARGET_CHANNEL}")
    logger.info(f"📡 Sources: {', '.join(SOURCE_CHANNELS)}")
    logger.info("=" * 60)
    
    try:
        # الاتصال بـ Telethon
        logger.info("🔌 Connecting to Telegram...")
        await client.start(bot_token=BOT_TOKEN)
        logger.info("✅ Connected successfully")
        
        # جلب المحتوى
        logger.info("📥 Fetching content from source channels...")
        raw_content = await get_content_from_sources()
        
        if not raw_content:
            logger.error("❌ No content available")
            return False
        
        logger.info(f"✅ Content fetched: {len(raw_content)} chars")
        logger.info(f"Preview: {raw_content[:150]}...")
        
        # معالجة بالـ AI
        logger.info("🤖 Rewriting with AI...")
        rewritten = ai_rewrite_content(raw_content)
        
        if not rewritten:
            logger.error("❌ AI processing failed")
            return False
        
        # إضافة تذييل
        footer = f"\n\n🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        final_message = rewritten + footer
        
        logger.info("📝 Final message:")
        logger.info("-" * 60)
        logger.info(final_message)
        logger.info("-" * 60)
        
        # النشر
        success = send_to_channel(final_message)
        
        if success:
            logger.info("=" * 60)
            logger.info("✨ Mission accomplished!")
            logger.info("=" * 60)
            return True
        else:
            logger.error("💔 Publishing failed")
            return False
            
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        return False
    finally:
        await client.disconnect()

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        logger.info("\n⚠️ Stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        sys.exit(1)
