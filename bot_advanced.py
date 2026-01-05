#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram + Facebook Content Aggregator Bot
Fetches content from Telegram channels and reposts to both Telegram & Facebook
"""

import os
import sys
import asyncio
import logging
import requests
import random
import base64
from datetime import datetime
from typing import Optional, List, Dict
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
# Telegram
TARGET_CHANNEL = os.getenv("TELEGRAM_CHANNEL")
API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
USER_SESSION_BASE64 = os.getenv("USER_SESSION_BASE64")
SOURCE_CHANNELS = os.getenv("SOURCE_CHANNELS", "").split(",")
SOURCE_CHANNELS = [ch.strip() for ch in SOURCE_CHANNELS if ch.strip()]

# Facebook
FB_PAGE_ID = os.getenv("FB_PAGE_ID")  # معرّف صفحة فيسبوك
FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN")  # توكن الوصول

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Settings
POSTS_LIMIT = int(os.getenv("POSTS_LIMIT", "10"))
POST_TO_TELEGRAM = os.getenv("POST_TO_TELEGRAM", "true").lower() == "true"
POST_TO_FACEBOOK = os.getenv("POST_TO_FACEBOOK", "true").lower() == "true"

# ====== VALIDATION ======
if not all([TARGET_CHANNEL, OPENAI_API_KEY, API_ID, API_HASH, USER_SESSION_BASE64]):
    logger.error("❌ Missing Telegram credentials")
    sys.exit(1)

if POST_TO_FACEBOOK and not all([FB_PAGE_ID, FB_ACCESS_TOKEN]):
    logger.error("❌ Missing Facebook credentials (FB_PAGE_ID, FB_ACCESS_TOKEN)")
    logger.error("Set POST_TO_FACEBOOK=false to disable Facebook posting")
    sys.exit(1)

if not SOURCE_CHANNELS:
    logger.error("❌ SOURCE_CHANNELS not set")
    sys.exit(1)

# ====== DECODE USER SESSION ======
with open("user_session.session", "wb") as f:
    f.write(base64.b64decode(USER_SESSION_BASE64))
logger.info("✅ USER_SESSION_BASE64 decoded")

# ====== TELETHON CLIENT ======
client = TelegramClient('user_session', int(API_ID), API_HASH)

# ====== FETCH FROM TELEGRAM ======
async def fetch_recent_posts(channel_username: str, limit: int = 10) -> List[Message]:
    messages = []
    try:
        logger.info(f"📥 Fetching from @{channel_username}...")
        async for message in client.iter_messages(channel_username, limit=limit):
            if (message.text and len(message.text) > 50) or message.photo or message.video:
                messages.append(message)
        logger.info(f"✅ Fetched {len(messages)} posts from @{channel_username}")
    except Exception as e:
        logger.error(f"❌ Error fetching @{channel_username}: {str(e)}")
    return messages

async def get_content_from_sources() -> Optional[Message]:
    all_messages = []
    for channel in SOURCE_CHANNELS:
        msgs = await fetch_recent_posts(channel, POSTS_LIMIT)
        all_messages.extend(msgs)
    if not all_messages:
        logger.warning("⚠️ No content fetched")
        return None
    selected = random.choice(all_messages)
    logger.info(f"✅ Selected post from @{selected.chat.username or 'unknown'}")
    return selected

# ====== AI PROCESSING ======
async def ai_rewrite_content(text: str, platform: str = "general", max_retries: int = 3) -> Optional[str]:
    """
    إعادة صياغة المحتوى حسب المنصة
    platform: 'telegram', 'facebook', 'general'
    """
    
    if platform == "facebook":
        prompt = f"""
أنت محرر محتوى على فيسبوك. أعد صياغة المحتوى التالي بأسلوب:
- جذاب ومشوّق
- يشجع على التفاعل (Engagement)
- عنوان قوي مع إيموجي
- 3-5 أسطر
- أضف دعوة للتفاعل في النهاية (CTA) مثل "ما رأيك؟" أو "شاركنا رأيك"

المحتوى:
{text}
"""
    else:  # telegram or general
        prompt = f"""
أنت محرر محتوى احترافي. أعد صياغة المحتوى التالي:
- بأسلوب جذاب ومختلف تماماً
- إذا كان بالإنجليزية، ترجمه للعربية
- احتفظ بالمعلومات المهمة
- عنوان قوي مع إيموجي
- 3-5 أسطر

المحتوى:
{text}
"""
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🤖 AI rewriting for {platform} (attempt {attempt}/{max_retries})...")
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
                result = response.json()['choices'][0]['message']['content'].strip()
                logger.info(f"✅ AI output preview: {result[:150]}...")
                return result
            else:
                logger.warning(f"⚠️ OpenAI error: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Error: {str(e)}")
        if attempt < max_retries:
            await asyncio.sleep(attempt * 2)
    return None

# ====== TELEGRAM SENDER ======
async def send_to_telegram(message: str, media_path: Optional[str] = None) -> bool:
    """نشر على قناة تيليغرام"""
    if not POST_TO_TELEGRAM:
        logger.info("⏭️ Telegram posting disabled")
        return True
    
    try:
        logger.info("📤 Publishing to Telegram...")
        if media_path:
            await client.send_file(TARGET_CHANNEL, media_path, caption=message)
        else:
            await client.send_message(TARGET_CHANNEL, message)
        logger.info("✅ Telegram: Published successfully!")
        return True
    except Exception as e:
        logger.error(f"❌ Telegram publishing failed: {str(e)}")
        return False

# ====== FACEBOOK SENDER ======
def send_to_facebook(message: str, media_path: Optional[str] = None) -> bool:
    """نشر على صفحة فيسبوك"""
    if not POST_TO_FACEBOOK:
        logger.info("⏭️ Facebook posting disabled")
        return True
    
    try:
        logger.info("📤 Publishing to Facebook...")
        
        # استخدام v21.0 (الأحدث)
        base_url = f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}"
        
        if media_path and os.path.exists(media_path):
            # نشر مع صورة أو فيديو
            file_ext = media_path.lower()
            
            if any(ext in file_ext for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                # نشر صورة
                logger.info("📸 Posting photo to Facebook...")
                endpoint = f"{base_url}/photos"
                
                with open(media_path, 'rb') as photo:
                    files = {'source': photo}
                    data = {
                        'message': message,  # استخدم 'message' بدلاً من 'caption'
                        'access_token': FB_ACCESS_TOKEN,
                        'published': 'true'
                    }
                    response = requests.post(endpoint, files=files, data=data, timeout=60)
                    
            elif any(ext in file_ext for ext in ['.mp4', '.mov', '.avi', '.mkv']):
                # نشر فيديو
                logger.info("🎥 Posting video to Facebook...")
                endpoint = f"{base_url}/videos"
                
                with open(media_path, 'rb') as video:
                    files = {'source': video}
                    data = {
                        'description': message,
                        'access_token': FB_ACCESS_TOKEN,
                        'published': 'true'
                    }
                    response = requests.post(endpoint, files=files, data=data, timeout=120)
            else:
                # نوع ملف غير مدعوم، انشر نص فقط
                logger.warning(f"⚠️ Unsupported media type: {file_ext}, posting text only")
                return send_to_facebook(message, None)
        else:
            # نشر نص فقط (بدون وسائط)
            logger.info("📝 Posting text to Facebook...")
            endpoint = f"{base_url}/feed"
            
            data = {
                'message': message,
                'access_token': FB_ACCESS_TOKEN,
                'published': 'true'
            }
            response = requests.post(endpoint, data=data, timeout=30)
        
        # معالجة الاستجابة
        if response.status_code == 200:
            result = response.json()
            post_id = result.get('id', result.get('post_id', 'unknown'))
            logger.info(f"✅ Facebook: Published successfully! Post ID: {post_id}")
            logger.info(f"🔗 View at: https://facebook.com/{post_id}")
            return True
        else:
            logger.error(f"❌ Facebook API error: {response.status_code}")
            logger.error(f"Response: {response.text}")
            
            # محاولة النشر كنص فقط إذا فشل النشر مع الوسائط
            if media_path:
                logger.warning("⚠️ Retrying without media...")
                return send_to_facebook(message, None)
            
            return False
            
    except FileNotFoundError:
        logger.error(f"❌ Media file not found: {media_path}")
        return send_to_facebook(message, None)
    except Exception as e:
        logger.error(f"❌ Facebook publishing failed: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

# ====== MAIN EXECUTION ======
async def main():
    logger.info("=" * 70)
    logger.info("🚀 Telegram + Facebook Content Aggregator Bot")
    logger.info(f"📅 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info(f"📢 Telegram: {TARGET_CHANNEL if POST_TO_TELEGRAM else 'Disabled'}")
    logger.info(f"📘 Facebook: {FB_PAGE_ID if POST_TO_FACEBOOK else 'Disabled'}")
    logger.info(f"📡 Sources: {', '.join(SOURCE_CHANNELS)}")
    logger.info("=" * 70)
    
    # الاتصال بـ Telegram
    await client.start()
    logger.info("✅ Connected to Telegram")
    
    # جلب المحتوى
    post = await get_content_from_sources()
    if not post:
        logger.error("❌ No content fetched")
        await client.disconnect()
        return False
    
    text = post.text if post.text else ""
    logger.info(f"📄 Original text preview: {text[:200]}...")
    
    # تحميل الوسائط إن وجدت
    media_path = None
    if post.photo or post.video:
        try:
            media_path = await post.download_media()
            logger.info(f"📦 Downloaded media: {media_path}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to download media: {str(e)}")
    
    # إعادة صياغة للمنصتين
    telegram_content = await ai_rewrite_content(text, "telegram")
    facebook_content = await ai_rewrite_content(text, "facebook")
    
    if not telegram_content or not facebook_content:
        logger.error("❌ AI processing failed")
        await client.disconnect()
        return False
    
    # إضافة تذييل
    timestamp = f"\n\n🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    telegram_message = telegram_content + timestamp
    facebook_message = facebook_content + timestamp
    
    logger.info("📝 Content prepared for both platforms")
    
    # النشر على Telegram
    telegram_success = await send_to_telegram(telegram_message, media_path)
    
    # النشر على Facebook
    facebook_success = send_to_facebook(facebook_message, media_path)
    
    # تنظيف الملف المؤقت
    if media_path and os.path.exists(media_path):
        try:
            os.remove(media_path)
            logger.info(f"🗑️ Cleaned up media file: {media_path}")
        except:
            pass
    
    # النتيجة النهائية
    await client.disconnect()
    
    if telegram_success and facebook_success:
        logger.info("=" * 70)
        logger.info("✨ Mission accomplished! Published to both platforms!")
        logger.info("=" * 70)
        return True
    elif telegram_success or facebook_success:
        logger.warning("⚠️ Partial success - check logs for details")
        return True
    else:
        logger.error("❌ Both platforms failed")
        return False

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        logger.info("\n⚠️ Stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
