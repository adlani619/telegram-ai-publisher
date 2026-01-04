#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram Content Aggregator Bot
Fetches content from other Telegram channels and reposts with AI enhancement
"""

import os
import sys
import time
import logging
import requests
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict

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
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# قائمة القنوات المصدر (عدّلها حسب رغبتك)
SOURCE_CHANNELS = os.getenv("SOURCE_CHANNELS", "").split(",")
# مثال: "TechNewsAR,AINewsArabic,ProgrammingAR"

# إزالة المسافات الفارغة
SOURCE_CHANNELS = [ch.strip() for ch in SOURCE_CHANNELS if ch.strip()]

# عدد المنشورات التي يجلبها من كل قناة
POSTS_LIMIT = int(os.getenv("POSTS_LIMIT", "5"))

# Validation
if not all([TELEGRAM_TOKEN, TELEGRAM_CHANNEL, OPENAI_API_KEY]):
    logger.error("❌ Missing required environment variables!")
    logger.error("Required: TELEGRAM_TOKEN, TELEGRAM_CHANNEL, OPENAI_API_KEY")
    sys.exit(1)

if not SOURCE_CHANNELS:
    logger.warning("⚠️ No SOURCE_CHANNELS defined. Using sample content.")

# ====== TELEGRAM API FUNCTIONS ======
def get_channel_posts(channel_username: str, limit: int = 5) -> List[Dict]:
    """
    جلب آخر منشورات من قناة تيليغرام
    
    ملاحظة: يتطلب أن يكون البوت عضواً في القناة المصدر
    """
    try:
        logger.info(f"📥 Fetching posts from @{channel_username}...")
        
        # محاولة الحصول على معلومات القناة أولاً
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChat"
        response = requests.post(url, json={"chat_id": f"@{channel_username}"}, timeout=10)
        
        if response.status_code != 200:
            logger.warning(f"⚠️ Cannot access @{channel_username}: {response.json().get('description')}")
            return []
        
        # للأسف، Telegram Bot API لا يسمح بقراءة منشورات القنوات مباشرة
        # سنستخدم طريقة بديلة: قراءة آخر رسائل من chat مع البوت
        # الحل الأفضل: استخدام Telethon أو Pyrogram
        
        logger.info(f"✅ Channel @{channel_username} is accessible")
        return []
        
    except Exception as e:
        logger.error(f"❌ Error fetching from @{channel_username}: {str(e)}")
        return []

def fetch_content_from_sources() -> Optional[str]:
    """
    جلب محتوى من القنوات المصدر
    
    ملاحظة: هذه دالة نموذجية. للحصول على وظيفة كاملة، 
    يجب استخدام مكتبات مثل Telethon أو Pyrogram
    """
    if not SOURCE_CHANNELS:
        return None
    
    all_content = []
    
    for channel in SOURCE_CHANNELS:
        posts = get_channel_posts(channel, POSTS_LIMIT)
        if posts:
            all_content.extend(posts)
    
    if not all_content:
        logger.warning("⚠️ No content fetched from source channels")
        return None
    
    # اختيار منشور عشوائي
    selected = random.choice(all_content)
    return selected.get('text', '')

# ====== RSS FEED FETCHER ======
def fetch_from_rss(rss_url: str) -> Optional[str]:
    """
    جلب محتوى من RSS feed
    يمكنك استخدام هذا بدلاً من قنوات تيليغرام
    """
    try:
        logger.info(f"📡 Fetching from RSS: {rss_url}")
        
        response = requests.get(rss_url, timeout=15)
        if response.status_code != 200:
            return None
        
        # هنا يجب إضافة parser لـ RSS (feedparser)
        # pip install feedparser
        # import feedparser
        # feed = feedparser.parse(response.text)
        # return feed.entries[0].summary
        
        logger.info("✅ RSS feed fetched (parser needed)")
        return None
        
    except Exception as e:
        logger.error(f"❌ RSS fetch error: {str(e)}")
        return None

# ====== AI PROCESSING ======
def ai_translate_and_summarize(text: str, max_retries: int = 3) -> Optional[str]:
    """
    معالجة النص بالذكاء الاصطناعي
    - تلخيص
    - ترجمة إذا لزم الأمر
    - إعادة صياغة بأسلوب احترافي
    """
    prompt = f"""
    أنت محرر محتوى محترف. المهمة:

    1. اقرأ النص التالي
    2. إذا كان بالإنجليزية، ترجمه للعربية
    3. لخصه في 3-4 أسطر فقط
    4. اكتب عنوان جذاب مع إيموجي
    5. استخدم أسلوب صحفي احترافي
    6. أضف قيمة للقارئ (سياق، تحليل بسيط)

    النص:
    {text}
    
    الرد يجب أن يكون بهذا الشكل:
    ### عنوان جذاب 🚀
    محتوى الملخص هنا...
    """
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🤖 Processing with AI (attempt {attempt}/{max_retries})...")
            
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,  # زيادة الإبداع قليلاً
                    "max_tokens": 600
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()['choices'][0]['message']['content']
                logger.info("✅ AI processing successful")
                return result.strip()
            else:
                logger.warning(f"⚠️ OpenAI API error: {response.status_code} - {response.text}")
                
        except requests.exceptions.Timeout:
            logger.warning(f"⏱️ Request timeout (attempt {attempt}/{max_retries})")
        except Exception as e:
            logger.error(f"❌ Unexpected error: {str(e)}")
        
        if attempt < max_retries:
            wait_time = attempt * 2
            logger.info(f"⏳ Waiting {wait_time}s before retry...")
            time.sleep(wait_time)
    
    logger.error("❌ AI processing failed after all retries")
    return None

# ====== TELEGRAM SENDER ======
def send_to_telegram(message: str, max_retries: int = 3) -> bool:
    """إرسال رسالة إلى قناة تيليغرام"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"📤 Sending to Telegram (attempt {attempt}/{max_retries})...")
            
            response = requests.post(
                url,
                json={
                    "chat_id": TELEGRAM_CHANNEL,
                    "text": message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": False
                },
                timeout=15
            )
            
            if response.status_code == 200:
                logger.info("✅ Message sent successfully!")
                return True
            else:
                error_msg = response.json().get('description', 'Unknown error')
                logger.warning(f"⚠️ Telegram API error: {error_msg}")
                
        except Exception as e:
            logger.warning(f"⚠️ Error: {str(e)}")
        
        if attempt < max_retries:
            wait_time = attempt * 2
            logger.info(f"⏳ Waiting {wait_time}s before retry...")
            time.sleep(wait_time)
    
    logger.error("❌ Failed to send message after all retries")
    return False

# ====== CONTENT FETCHER ======
def fetch_content() -> Optional[str]:
    """
    جلب المحتوى من مصادر مختلفة
    """
    # محاولة 1: من قنوات تيليغرام
    content = fetch_content_from_sources()
    if content:
        return content
    
    # محاولة 2: من RSS (إذا كنت تريد إضافة feeds)
    # rss_feeds = [
    #     "https://example.com/tech-news/rss",
    #     "https://another-site.com/feed.xml"
    # ]
    # for feed_url in rss_feeds:
    #     content = fetch_from_rss(feed_url)
    #     if content:
    #         return content
    
    # محتوى نموذجي للتجربة
    logger.info("📝 Using sample content for testing")
    sample_contents = [
        """
        Microsoft announces new AI features in Windows 11. 
        The update includes Copilot integration across all apps, 
        making productivity tools smarter and more intuitive.
        """,
        """
        Google releases Gemini 2.0 with improved reasoning capabilities.
        The new model outperforms previous versions in coding and math tasks.
        """,
        """
        Apple reveals breakthrough in chip design with M4 processor.
        The new chip promises 40% better performance with lower power consumption.
        """
    ]
    
    return random.choice(sample_contents).strip()

# ====== MAIN EXECUTION ======
def main():
    """Main execution flow"""
    logger.info("=" * 60)
    logger.info("🚀 Telegram Content Aggregator Started")
    logger.info(f"📅 Timestamp: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info(f"📢 Target channel: {TELEGRAM_CHANNEL}")
    logger.info(f"📡 Source channels: {SOURCE_CHANNELS if SOURCE_CHANNELS else 'None (using sample)'}")
    logger.info("=" * 60)
    
    # Step 1: Fetch content
    logger.info("📥 Fetching content from sources...")
    raw_content = fetch_content()
    
    if not raw_content:
        logger.error("❌ No content available. Exiting.")
        sys.exit(1)
    
    logger.info(f"✅ Content fetched: {len(raw_content)} characters")
    logger.info(f"📄 Original content preview: {raw_content[:100]}...")
    
    # Step 2: Process with AI
    logger.info("🤖 Processing content with AI...")
    processed_content = ai_translate_and_summarize(raw_content)
    
    if not processed_content:
        logger.error("❌ AI processing failed. Exiting.")
        sys.exit(1)
    
    # Step 3: Add footer with timestamp
    footer = f"\n\n🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    final_message = processed_content + footer
    
    logger.info("📝 Final message prepared:")
    logger.info("-" * 60)
    logger.info(final_message)
    logger.info("-" * 60)
    
    # Step 4: Send to Telegram
    success = send_to_telegram(final_message)
    
    if success:
        logger.info("=" * 60)
        logger.info("✨ Mission accomplished! Content published successfully.")
        logger.info("=" * 60)
        sys.exit(0)
    else:
        logger.error("=" * 60)
        logger.error("💔 Mission failed. Check logs for details.")
        logger.error("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n⚠️ Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        sys.exit(1)
