#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram Content Aggregator Bot
يجلب المحتوى من قنوات تيليغرام ويعيد نشره بشكل احترافي
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
# Telegram
TARGET_CHANNEL = os.getenv("TELEGRAM_CHANNEL")
API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
USER_SESSION_BASE64 = os.getenv("USER_SESSION_BASE64")
SOURCE_CHANNELS = os.getenv("SOURCE_CHANNELS", "").split(",")
SOURCE_CHANNELS = [ch.strip() for ch in SOURCE_CHANNELS if ch.strip()]

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Settings
POSTS_LIMIT = int(os.getenv("POSTS_LIMIT", "10"))
MIN_CONTENT_LENGTH = int(os.getenv("MIN_CONTENT_LENGTH", "100"))

# ====== Facebook Configuration (مخفي - يمكن تفعيله لاحقاً) ======
"""
FB_PAGE_ID = os.getenv("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN")
FB_PUBLISH_AS_DRAFT = os.getenv("FB_PUBLISH_AS_DRAFT", "false").lower() == "true"
POST_TO_FACEBOOK = os.getenv("POST_TO_FACEBOOK", "false").lower() == "true"
"""

# ====== VALIDATION ======
if not all([TARGET_CHANNEL, OPENAI_API_KEY, API_ID, API_HASH, USER_SESSION_BASE64]):
    logger.error("❌ بيانات تيليغرام غير مكتملة")
    sys.exit(1)

if not SOURCE_CHANNELS:
    logger.error("❌ قنوات المصدر غير محددة (SOURCE_CHANNELS)")
    sys.exit(1)

# ====== DECODE USER SESSION ======
try:
    with open("user_session.session", "wb") as f:
        f.write(base64.b64decode(USER_SESSION_BASE64))
    logger.info("✅ تم فك تشفير الجلسة بنجاح")
except Exception as e:
    logger.error(f"❌ فشل في فك تشفير الجلسة: {str(e)}")
    sys.exit(1)

# ====== TELETHON CLIENT ======
client = TelegramClient('user_session', int(API_ID), API_HASH)

# ====== FETCH FROM TELEGRAM ======
async def fetch_recent_posts(channel_username: str, limit: int = 10) -> List[Message]:
    """جلب المنشورات من قناة تيليغرام"""
    messages = []
    try:
        logger.info(f"📥 جاري جلب المحتوى من @{channel_username}...")
        async for message in client.iter_messages(channel_username, limit=limit):
            if message.text and len(message.text) >= MIN_CONTENT_LENGTH:
                messages.append(message)
            elif (message.photo or message.video) and message.text:
                messages.append(message)
        logger.info(f"✅ تم جلب {len(messages)} منشور من @{channel_username}")
    except Exception as e:
        logger.error(f"❌ خطأ في جلب المحتوى من @{channel_username}: {str(e)}")
    return messages

async def get_content_from_sources() -> Optional[Message]:
    """جلب محتوى عشوائي من المصادر"""
    all_messages = []
    for channel in SOURCE_CHANNELS:
        msgs = await fetch_recent_posts(channel, POSTS_LIMIT)
        all_messages.extend(msgs)
    
    if not all_messages:
        logger.warning("⚠️ لم يتم العثور على محتوى من أي مصدر")
        return None
    
    selected = random.choice(all_messages)
    source = selected.chat.username or selected.chat.title or 'unknown'
    logger.info(f"✅ تم اختيار منشور من @{source}")
    return selected

# ====== AI PROCESSING ======
async def ai_rewrite_content(text: str, max_retries: int = 3) -> Optional[str]:
    """إعادة صياغة المحتوى بالذكاء الاصطناعي مع هاشتاغات احترافية"""
    
    if not text or len(text.strip()) < 50:
        logger.error("❌ المحتوى قصير جداً للمعالجة")
        return None
    
    prompt = f"""
أنت خبير تسويق محتوى على وسائل التواصل الاجتماعي (تيليغرام، فيسبوك، إنستغرام).

أعد صياغة المحتوى التالي بشكل احترافي وجذاب:

✅ المتطلبات:
1. عنوان قوي وجذاب مع إيموجي مناسب
2. 4-6 أسطر واضحة ومنظمة
3. إذا كان المحتوى بالإنجليزية، ترجمه للعربية
4. أسلوب طبيعي وجذاب (ليس آلياً)
5. احتفظ بجميع المعلومات المهمة
6. أضف 5-8 هاشتاغات ذات صلة باللغة العربية والإنجليزية (مناسبة للتيليغرام وفيسبوك وإنستغرام)
7. اجعل الهاشتاغات متنوعة: عامة، متخصصة، وترند

❌ تجنب:
- كلمات مثل "بالطبع"، "يُرجى"، "سأكون سعيداً"
- الأسلوب الرسمي الممل
- النسخ الحرفي

المحتوى الأصلي:
{text}

ملاحظة: اجعل المحتوى صالحاً للنشر على تيليغرام وفيسبوك وإنستغرام معاً.
"""
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🤖 جاري إعادة صياغة المحتوى (محاولة {attempt}/{max_retries})...")
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
                    "max_tokens": 1000
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()['choices'][0]['message']['content'].strip()
                
                # فلترة الردود السيئة
                bad_phrases = ["بالطبع", "يُرجى تزويدي", "سأكون سعيد", "عذراً", "آسف"]
                if any(phrase in result[:150] for phrase in bad_phrases):
                    logger.warning(f"⚠️ الذكاء الاصطناعي أعاد رد عام، إعادة المحاولة...")
                    if attempt < max_retries:
                        await asyncio.sleep(2)
                        continue
                
                if len(result) < 100:
                    logger.warning(f"⚠️ المخرج قصير جداً، إعادة المحاولة...")
                    if attempt < max_retries:
                        await asyncio.sleep(2)
                        continue
                
                # التحقق من وجود هاشتاغات
                if '#' not in result:
                    logger.warning(f"⚠️ لا توجد هاشتاغات، إعادة المحاولة...")
                    if attempt < max_retries:
                        await asyncio.sleep(2)
                        continue
                
                logger.info(f"✅ تمت المعالجة بنجاح! معاينة: {result[:120]}...")
                return result
            else:
                logger.warning(f"⚠️ خطأ من OpenAI: {response.status_code}")
                
        except requests.exceptions.Timeout:
            logger.error(f"⏱️ انتهت مهلة الطلب في المحاولة {attempt}")
        except Exception as e:
            logger.error(f"❌ خطأ في الذكاء الاصطناعي: {str(e)}")
        
        if attempt < max_retries:
            wait_time = attempt * 3
            logger.info(f"⏳ انتظار {wait_time} ثانية قبل إعادة المحاولة...")
            await asyncio.sleep(wait_time)
    
    logger.error("❌ فشلت المعالجة بعد جميع المحاولات")
    return None

# ====== TELEGRAM SENDER ======
async def send_to_telegram(message: str, media_path: Optional[str] = None) -> bool:
    """نشر على قناة تيليغرام"""
    try:
        logger.info("📤 جاري النشر على تيليغرام...")
        if media_path and os.path.exists(media_path):
            await client.send_file(TARGET_CHANNEL, media_path, caption=message)
            logger.info("✅ تم النشر مع الوسائط بنجاح!")
        else:
            await client.send_message(TARGET_CHANNEL, message)
            logger.info("✅ تم النشر بنجاح!")
        return True
    except Exception as e:
        logger.error(f"❌ فشل النشر على تيليغرام: {str(e)}")
        return False

# ====== Facebook Functions (مخفية - يمكن تفعيلها لاحقاً) ======
"""
def send_to_facebook(message: str, media_path: Optional[str] = None) -> bool:
    if not POST_TO_FACEBOOK:
        logger.info("⏭️ النشر على فيسبوك معطل")
        return True
    
    try:
        published_status = "false" if FB_PUBLISH_AS_DRAFT else "true"
        status_text = "مسودة 📝" if FB_PUBLISH_AS_DRAFT else "مباشر ✅"
        
        logger.info(f"📤 جاري النشر على فيسبوك كـ {status_text}...")
        
        base_url = f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}"
        
        if media_path and os.path.exists(media_path):
            file_ext = media_path.lower()
            
            if any(ext in file_ext for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                logger.info(f"📸 نشر صورة كـ {status_text}...")
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
                logger.info(f"🎥 نشر فيديو كـ {status_text}...")
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
                logger.warning(f"⚠️ نوع ملف غير مدعوم، نشر نص فقط")
                return send_to_facebook(message, None)
        else:
            logger.info(f"📝 نشر نص كـ {status_text}...")
            endpoint = f"{base_url}/feed"
            
            data = {
                'message': message,
                'access_token': FB_ACCESS_TOKEN,
                'published': published_status
            }
            response = requests.post(endpoint, data=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            post_id = result.get('id', result.get('post_id', 'unknown'))
            
            if FB_PUBLISH_AS_DRAFT:
                logger.info(f"✅ فيسبوك: تم الحفظ كمسودة! معرف المنشور: {post_id}")
            else:
                logger.info(f"✅ فيسبوك: تم النشر مباشرة! معرف المنشور: {post_id}")
            
            return True
        else:
            logger.error(f"❌ خطأ في واجهة فيسبوك: {response.status_code}")
            logger.error(f"الرد: {response.text}")
            
            if media_path:
                logger.warning("⚠️ إعادة المحاولة بدون وسائط...")
                return send_to_facebook(message, None)
            
            return False
            
    except FileNotFoundError:
        logger.error(f"❌ الملف غير موجود: {media_path}")
        return send_to_facebook(message, None)
    except Exception as e:
        logger.error(f"❌ فشل النشر على فيسبوك: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False
"""

# ====== MAIN EXECUTION ======
async def main():
    """البرنامج الرئيسي"""
    logger.info("=" * 70)
    logger.info("🤖 بوت النشر التلقائي على تيليغرام")
    logger.info(f"📅 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info(f"📢 القناة: {TARGET_CHANNEL}")
    logger.info(f"📡 المصادر: {', '.join(SOURCE_CHANNELS)}")
    logger.info("=" * 70)
    
    try:
        # الاتصال بـ Telegram
        await client.start()
        logger.info("✅ تم الاتصال بتيليغرام")
        
        # جلب المحتوى
        post = await get_content_from_sources()
        if not post:
            logger.error("❌ لم يتم العثور على محتوى")
            await client.disconnect()
            return False
        
        text = post.text if post.text else ""
        
        if len(text.strip()) < MIN_CONTENT_LENGTH:
            logger.error(f"❌ المحتوى قصير جداً ({len(text)} حرف)")
            await client.disconnect()
            return False
        
        logger.info(f"📄 المحتوى الأصلي: {text[:150]}...")
        
        # تحميل الوسائط إن وجدت
        media_path = None
        if post.photo or post.video:
            try:
                logger.info("📥 جاري تحميل الوسائط...")
                media_path = await post.download_media()
                logger.info(f"✅ تم تحميل الوسائط: {media_path}")
            except Exception as e:
                logger.warning(f"⚠️ فشل تحميل الوسائط: {str(e)}")
        
        # إعادة صياغة المحتوى
        logger.info("🤖 جاري توليد المحتوى بالذكاء الاصطناعي...")
        
        rewritten_content = await ai_rewrite_content(text)
        if not rewritten_content:
            logger.error("❌ فشل في توليد المحتوى")
            await client.disconnect()
            return False
        
        # إضافة التوقيت
        timestamp = f"\n\n🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        final_message = rewritten_content + timestamp
        
        logger.info("=" * 70)
        logger.info("📝 معاينة المحتوى النهائي:")
        logger.info(final_message[:300] + "...")
        logger.info("=" * 70)
        
        # النشر على تيليغرام
        success = await send_to_telegram(final_message, media_path)
        
        # تنظيف الملفات المؤقتة
        if media_path and os.path.exists(media_path):
            try:
                os.remove(media_path)
                logger.info(f"🗑️ تم حذف الملف المؤقت: {media_path}")
            except:
                pass
        
        await client.disconnect()
        
        # النتيجة النهائية
        logger.info("=" * 70)
        if success:
            logger.info("✨ نجح! تم النشر على تيليغرام بنجاح!")
            logger.info("💡 يمكنك الآن نسخ المحتوى يدوياً لفيسبوك وإنستغرام")
        else:
            logger.error("❌ فشل النشر")
        logger.info("=" * 70)
        
        return success
        
    except Exception as e:
        logger.error(f"❌ خطأ فادح: {str(e)}")
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
        logger.info("\n⚠️ تم الإيقاف بواسطة المستخدم")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ خطأ فادح: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
