#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram + Facebook/Instagram Content Aggregator Bot
Fetches content from Telegram channels and reposts to Telegram & Facebook/Instagram
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

# Facebook/Instagram
FB_PAGE_ID = os.getenv("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN")
# خيار جديد: true = مسودة، false = نشر مباشر
FB_PUBLISH_AS_DRAFT = os.getenv("FB_PUBLISH_AS_DRAFT", "true").lower() == "true"

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Settings
POSTS_LIMIT = int(os.getenv("POSTS_LIMIT", "10"))
POST_TO_TELEGRAM = os.getenv("POST_TO_TELEGRAM", "true").lower() == "true"
POST_TO_FACEBOOK = os.getenv("POST_TO_FACEBOOK", "true").lower() == "true"
MIN_CONTENT_LENGTH = int(os.getenv("MIN_CONTENT_LENGTH", "100"))

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
try:
    with open("user_session.session", "wb") as f:
        f.write(base64.b64decode(USER_SESSION_BASE64))
    logger.info("✅ USER_SESSION_BASE64 decoded")
except Exception as e:
    logger.error(f"❌ Failed to decode session: {str(e)}")
    sys.exit(1)

# ====== TELETHON CLIENT ======
client = TelegramClient('user_session', int(API_ID), API_HASH)

# ====== FETCH FROM TELEGRAM ======
async def fetch_recent_posts(channel_username: str, limit: int = 10) -> List[Message]:
    """جلب المنشورات من قناة تيليغرام"""
    messages = []
    try:
        logger.info(f"📥 Fetching from @{channel_username}...")
        async for message in client.iter_messages(channel_username, limit=limit):
            # تحسين: التحقق من طول المحتوى
            if message.text and len(message.text) >= MIN_CONTENT_LENGTH:
                messages.append(message)
            elif (message.photo or message.video) and message.text:
                messages.append(message)
        logger.info(f"✅ Fetched {len(messages)} quality posts from @{channel_username}")
    except Exception as e:
        logger.error(f"❌ Error fetching @{channel_username}: {str(e)}")
    return messages

async def get_content_from_sources() -> Optional[Message]:
    """جلب محتوى عشوائي من المصادر"""
    all_messages = []
    for channel in SOURCE_CHANNELS:
        msgs = await fetch_recent_posts(channel, POSTS_LIMIT)
        all_messages.extend(msgs)
    
    if not all_messages:
        logger.warning("⚠️ No suitable content found from any source")
        return None
    
    # اختيار عشوائي من المنشورات الجيدة
    selected = random.choice(all_messages)
    source = selected.chat.username or selected.chat.title or 'unknown'
    logger.info(f"✅ Selected quality post from @{source}")
    return selected

# ====== AI PROCESSING ======
async def ai_rewrite_content(text: str, platform: str = "general", max_retries: int = 3) -> Optional[str]:
    """
    إعادة صياغة المحتوى بذكاء اصطناعي حسب المنصة
    platform: 'telegram', 'facebook', 'general'
    """
    
    # تحسين: التأكد من وجود محتوى حقيقي
    if not text or len(text.strip()) < 50:
        logger.error("❌ Content too short or empty for AI processing")
        return None
    
    if platform == "facebook":
        prompt = f"""
أنت خبير تسويق محتوى على فيسبوك وإنستغرام. أعد صياغة المحتوى التالي بطريقة احترافية:

متطلبات:
✅ عنوان جذاب مع إيموجي مناسب
✅ محتوى من 4-6 أسطر واضح ومشوق
✅ أسلوب طبيعي وليس آلي
✅ إذا كان النص بالإنجليزية، ترجمه للعربية مع الحفاظ على المصطلحات التقنية
✅ أضف دعوة للتفاعل في النهاية (مثل: "ما رأيك؟" أو "شاركنا تجربتك")
✅ احتفظ بالحقائق والأرقام المهمة
❌ لا تستخدم عبارات مثل "بالطبع!" أو "يُرجى"
❌ لا تبدأ بعبارات ركيكة

المحتوى الأصلي:
{text}

أعد الصياغة الآن:
"""
    else:  # telegram or general
        prompt = f"""
أنت محرر محتوى احترافي على تيليغرام. أعد صياغة المحتوى التالي:

متطلبات:
✅ عنوان قوي مع إيموجي
✅ 4-5 أسطر واضحة ومباشرة
✅ إذا كان بالإنجليزية، ترجمه للعربية مع الحفاظ على المصطلحات التقنية
✅ أسلوب طبيعي وليس آلي
✅ احتفظ بالمعلومات المهمة والأرقام
❌ لا تستخدم عبارات مثل "بالطبع!" أو "يُرجى تزويدي"
❌ لا تبدأ بمقدمات ركيكة

المحتوى الأصلي:
{text}

أعد الصياغة الآن:
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
                    "temperature": 0.7,  # خفضنا قليلاً لنتائج أكثر اتساقاً
                    "max_tokens": 800
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()['choices'][0]['message']['content'].strip()
                
                # تحسين: فلترة الردود السيئة
                bad_phrases = [
                    "بالطبع",
                    "يُرجى تزويدي",
                    "سأكون سعيد",
                    "يرجى تقديم",
                    "لا أستطيع",
                    "عذراً"
                ]
                
                if any(phrase in result[:100] for phrase in bad_phrases):
                    logger.warning(f"⚠️ AI returned generic response, retrying...")
                    if attempt < max_retries:
                        await asyncio.sleep(2)
                        continue
                
                if len(result) < 100:
                    logger.warning(f"⚠️ AI output too short, retrying...")
                    if attempt < max_retries:
                        await asyncio.sleep(2)
                        continue
                
                logger.info(f"✅ AI success! Preview: {result[:120]}...")
                return result
            else:
                logger.warning(f"⚠️ OpenAI API error: {response.status_code} - {response.text[:200]}")
                
        except requests.exceptions.Timeout:
            logger.error(f"⏱️ Request timeout on attempt {attempt}")
        except Exception as e:
            logger.error(f"❌ AI Error: {str(e)}")
        
        if attempt < max_retries:
            wait_time = attempt * 3
            logger.info(f"⏳ Waiting {wait_time}s before retry...")
            await asyncio.sleep(wait_time)
    
    logger.error("❌ AI processing failed after all retries")
    return None

# ====== TELEGRAM SENDER ======
async def send_to_telegram(message: str, media_path: Optional[str] = None) -> bool:
    """نشر على قناة تيليغرام"""
    if not POST_TO_TELEGRAM:
        logger.info("⏭️ Telegram posting disabled")
        return True
    
    try:
        logger.info("📤 Publishing to Telegram...")
        if media_path and os.path.exists(media_path):
            await client.send_file(TARGET_CHANNEL, media_path, caption=message)
        else:
            await client.send_message(TARGET_CHANNEL, message)
        logger.info("✅ Telegram: Published successfully!")
        return True
    except Exception as e:
        logger.error(f"❌ Telegram publishing failed: {str(e)}")
        return False

# ====== FACEBOOK/INSTAGRAM SENDER ======
def send_to_facebook(message: str, media_path: Optional[str] = None) -> bool:
    """
    نشر على Facebook/Instagram
    يدعم النشر المباشر أو كمسودة (Draft)
    """
    if not POST_TO_FACEBOOK:
        logger.info("⏭️ Facebook posting disabled")
        return True
    
    try:
        # تحديد حالة النشر
        published_status = "false" if FB_PUBLISH_AS_DRAFT else "true"
        status_text = "draft 📝" if FB_PUBLISH_AS_DRAFT else "live ✅"
        
        logger.info(f"📤 Publishing to Facebook as {status_text}...")
        
        base_url = f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}"
        
        if media_path and os.path.exists(media_path):
            file_ext = media_path.lower()
            
            if any(ext in file_ext for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                # نشر صورة
                logger.info(f"📸 Posting photo as {status_text}...")
                endpoint = f"{base_url}/photos"
                
                with open(media_path, 'rb') as photo:
                    files = {'source': photo}
                    data = {
                        'message': message,
                        'access_token': FB_ACCESS_TOKEN,
                        'published': published_status
                    }
                    response = requests.post(endpoint, files=files, data=data, timeout=60)
                    
            elif any(ext in file_ext for ext in ['.mp4', '.mov', '.avi', '.mkv']):
                # نشر فيديو
                logger.info(f"🎥 Posting video as {status_text}...")
                endpoint = f"{base_url}/videos"
                
                with open(media_path, 'rb') as video:
                    files = {'source': video}
                    data = {
                        'description': message,
                        'access_token': FB_ACCESS_TOKEN,
                        'published': published_status
                    }
                    response = requests.post(endpoint, files=files, data=data, timeout=120)
            else:
                logger.warning(f"⚠️ Unsupported media type: {file_ext}, posting text only")
                return send_to_facebook(message, None)
        else:
            # نشر نص فقط
            logger.info(f"📝 Posting text as {status_text}...")
            endpoint = f"{base_url}/feed"
            
            data = {
                'message': message,
                'access_token': FB_ACCESS_TOKEN,
                'published': published_status
            }
            response = requests.post(endpoint, data=data, timeout=30)
        
        # معالجة الاستجابة
        if response.status_code == 200:
            result = response.json()
            post_id = result.get('id', result.get('post_id', 'unknown'))
            
            if FB_PUBLISH_AS_DRAFT:
                logger.info(f"✅ Facebook: Saved as DRAFT! Post ID: {post_id}")
                logger.info(f"📝 Review at: https://business.facebook.com/latest/content_publishing")
                logger.info(f"💡 You can now review and publish to Facebook & Instagram!")
            else:
                logger.info(f"✅ Facebook: Published LIVE! Post ID: {post_id}")
                logger.info(f"🔗 View at: https://facebook.com/{post_id}")
            
            return True
        else:
            logger.error(f"❌ Facebook API error: {response.status_code}")
            logger.error(f"Response: {response.text}")
            
            # محاولة بدون وسائط إذا فشل
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
    """البرنامج الرئيسي"""
    logger.info("=" * 70)
    logger.info("🚀 Telegram + Facebook/Instagram Content Aggregator Bot")
    logger.info(f"📅 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info(f"📢 Telegram: {TARGET_CHANNEL if POST_TO_TELEGRAM else 'Disabled'}")
    
    if POST_TO_FACEBOOK:
        fb_mode = "Draft Mode 📝" if FB_PUBLISH_AS_DRAFT else "Live Mode ✅"
        logger.info(f"📘 Facebook: {FB_PAGE_ID} ({fb_mode})")
    else:
        logger.info(f"📘 Facebook: Disabled")
    
    logger.info(f"📡 Sources: {', '.join(SOURCE_CHANNELS)}")
    logger.info("=" * 70)
    
    try:
        # الاتصال بـ Telegram
        await client.start()
        logger.info("✅ Connected to Telegram")
        
        # جلب المحتوى
        post = await get_content_from_sources()
        if not post:
            logger.error("❌ No suitable content found in any source channel")
            await client.disconnect()
            return False
        
        text = post.text if post.text else ""
        
        if len(text.strip()) < MIN_CONTENT_LENGTH:
            logger.error(f"❌ Content too short ({len(text)} chars, min: {MIN_CONTENT_LENGTH})")
            await client.disconnect()
            return False
        
        logger.info(f"📄 Original content: {text[:150]}...")
        
        # تحميل الوسائط
        media_path = None
        if post.photo or post.video:
            try:
                logger.info("📥 Downloading media...")
                media_path = await post.download_media()
                logger.info(f"✅ Media downloaded: {media_path}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to download media: {str(e)}")
        
        # إعادة صياغة للمنصتين
        logger.info("🤖 Starting AI content generation...")
        
        telegram_content = await ai_rewrite_content(text, "telegram")
        if not telegram_content:
            logger.error("❌ Failed to generate Telegram content")
            await client.disconnect()
            return False
        
        facebook_content = await ai_rewrite_content(text, "facebook")
        if not facebook_content:
            logger.error("❌ Failed to generate Facebook content")
            await client.disconnect()
            return False
        
        # إضافة التوقيت
        timestamp = f"\n\n🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        telegram_message = telegram_content + timestamp
        facebook_message = facebook_content + timestamp
        
        logger.info("=" * 70)
        logger.info("📝 CONTENT PREVIEW:")
        logger.info(f"Telegram: {telegram_message[:200]}...")
        logger.info(f"Facebook: {facebook_message[:200]}...")
        logger.info("=" * 70)
        
        # النشر
        telegram_success = await send_to_telegram(telegram_message, media_path)
        facebook_success = send_to_facebook(facebook_message, media_path)
        
        # تنظيف
        if media_path and os.path.exists(media_path):
            try:
                os.remove(media_path)
                logger.info(f"🗑️ Cleaned up: {media_path}")
            except:
                pass
        
        await client.disconnect()
        
        # النتيجة
        logger.info("=" * 70)
        if telegram_success and facebook_success:
            logger.info("✨ SUCCESS! Published to all platforms!")
            if FB_PUBLISH_AS_DRAFT:
                logger.info("💡 Facebook post is in DRAFT - review before publishing")
        elif telegram_success or facebook_success:
            logger.warning("⚠️ Partial success - check logs")
        else:
            logger.error("❌ All platforms failed")
        logger.info("=" * 70)
        
        return telegram_success or facebook_success
        
    except Exception as e:
        logger.error(f"❌ Fatal error in main: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        try:
            await client.disconnect()
        except:
            pass
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
