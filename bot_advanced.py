#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram Content Aggregator Bot
يجلب المحتوى من قنوات تيليغرام ويعيد نشره بشكل احترافي
Bilingual Edition: Arabic + English
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

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Settings
POSTS_LIMIT = int(os.getenv("POSTS_LIMIT", "10"))
MIN_CONTENT_LENGTH = int(os.getenv("MIN_CONTENT_LENGTH", "100"))

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

# ====== AI PROCESSING - ARABIC VERSION ======
async def ai_rewrite_arabic(text: str, max_retries: int = 3) -> Optional[str]:
    """إعادة صياغة المحتوى بالعربية"""
    
    if not text or len(text.strip()) < 50:
        logger.error("❌ المحتوى قصير جداً للمعالجة")
        return None
    
    prompt = f"""
أنت خبير تسويق محتوى على وسائل التواصل الاجتماعي (تيليغرام، فيسبوك، إنستغرام).

أعد صياغة المحتوى التالي بشكل احترافي وجذاب بالعربية:

✅ المتطلبات:
1. عنوان قوي وجذاب مع إيموجي مناسب
2. 4-6 أسطر واضحة ومنظمة
3. إذا كان المحتوى بالإنجليزية، ترجمه للعربية
4. أسلوب طبيعي وجذاب (ليس آلياً)
5. احتفظ بجميع المعلومات المهمة
6. أضف 5-8 هاشتاغات ذات صلة باللغة العربية والإنجليزية
7. اجعل الهاشتاغات متنوعة: عامة، متخصصة، وترند

❌ تجنب:
- كلمات مثل "بالطبع"، "يُرجى"، "سأكون سعيداً"
- الأسلوب الرسمي الممل
- النسخ الحرفي

المحتوى الأصلي:
{text}
"""
    
    return await _call_openai(prompt, max_retries, "Arabic")

# ====== AI PROCESSING - ENGLISH VERSION ======
async def ai_rewrite_english(text: str, max_retries: int = 3) -> Optional[str]:
    """إعادة صياغة المحتوى بالإنجليزية لتويتر"""
    
    if not text or len(text.strip()) < 50:
        logger.error("❌ المحتوى قصير جداً للمعالجة")
        return None
    
    prompt = f"""
You are an expert social media content strategist specializing in Twitter/X engagement and international audiences.

Rewrite the following content in PROFESSIONAL, ENGAGING ENGLISH optimized for Twitter/X:

✅ REQUIREMENTS:
1. Create a compelling hook with relevant emoji
2. 4-6 clear, punchy lines (Twitter-optimized)
3. Translate from Arabic if needed
4. Natural, conversational tone (not robotic or corporate)
5. Preserve all key information and insights
6. Add 5-8 trending hashtags (mix of general, niche, and trending)
7. Make it shareable and engaging for international tech/business audience
8. Use power words and curiosity gaps
9. Include a subtle call-to-action if appropriate

❌ AVOID:
- Generic corporate speak
- Overly formal language
- Boring, predictable phrasing
- Verbatim copying
- Too many hashtags in the main text (put them at the end)

ORIGINAL CONTENT:
{text}

Note: Make it viral-worthy for Twitter/X. Think: professional yet exciting, informative yet engaging.
"""
    
    return await _call_openai(prompt, max_retries, "English")

# ====== OPENAI API CALLER ======
async def _call_openai(prompt: str, max_retries: int, language: str) -> Optional[str]:
    """استدعاء OpenAI API مع إعادة المحاولة"""
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🤖 جاري إعادة صياغة المحتوى ({language}) (محاولة {attempt}/{max_retries})...")
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
                if language == "Arabic":
                    bad_phrases = ["بالطبع", "يُرجى تزويدي", "سأكون سعيد", "عذراً", "آسف"]
                else:
                    bad_phrases = ["of course", "please provide", "i'd be happy", "sorry", "i apologize"]
                
                if any(phrase.lower() in result[:150].lower() for phrase in bad_phrases):
                    logger.warning(f"⚠️ الذكاء الاصطناعي أعاد رد عام ({language})، إعادة المحاولة...")
                    if attempt < max_retries:
                        await asyncio.sleep(2)
                        continue
                
                if len(result) < 100:
                    logger.warning(f"⚠️ المخرج قصير جداً ({language})، إعادة المحاولة...")
                    if attempt < max_retries:
                        await asyncio.sleep(2)
                        continue
                
                # التحقق من وجود هاشتاغات
                if '#' not in result:
                    logger.warning(f"⚠️ لا توجد هاشتاغات ({language})، إعادة المحاولة...")
                    if attempt < max_retries:
                        await asyncio.sleep(2)
                        continue
                
                logger.info(f"✅ تمت المعالجة بنجاح ({language})! معاينة: {result[:120]}...")
                return result
            else:
                logger.warning(f"⚠️ خطأ من OpenAI: {response.status_code}")
                
        except requests.exceptions.Timeout:
            logger.error(f"⏱️ انتهت مهلة الطلب في المحاولة {attempt}")
        except Exception as e:
            logger.error(f"❌ خطأ في الذكاء الاصطناعي ({language}): {str(e)}")
        
        if attempt < max_retries:
            wait_time = attempt * 3
            logger.info(f"⏳ انتظار {wait_time} ثانية قبل إعادة المحاولة...")
            await asyncio.sleep(wait_time)
    
    logger.error(f"❌ فشلت المعالجة ({language}) بعد جميع المحاولات")
    return None

# ====== TELEGRAM SENDER ======
async def send_to_telegram(message: str, media_path: Optional[str] = None, language: str = "AR") -> bool:
    """نشر على قناة تيليغرام"""
    try:
        lang_label = "🇸🇦 Arabic" if language == "AR" else "🇬🇧 English"
        logger.info(f"📤 جاري النشر على تيليغرام ({lang_label})...")
        
        if media_path and os.path.exists(media_path):
            await client.send_file(TARGET_CHANNEL, media_path, caption=message)
            logger.info(f"✅ تم النشر ({lang_label}) مع الوسائط بنجاح!")
        else:
            await client.send_message(TARGET_CHANNEL, message)
            logger.info(f"✅ تم النشر ({lang_label}) بنجاح!")
        
        return True
    except Exception as e:
        logger.error(f"❌ فشل النشر على تيليغرام ({language}): {str(e)}")
        return False

# ====== MAIN EXECUTION ======
async def main():
    """البرنامج الرئيسي"""
    logger.info("=" * 70)
    logger.info("🤖 بوت النشر التلقائي على تيليغرام (ثنائي اللغة)")
    logger.info(f"📅 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info(f"📢 القناة: {TARGET_CHANNEL}")
    logger.info(f"📡 المصادر: {', '.join(SOURCE_CHANNELS)}")
    logger.info(f"🌐 اللغات: العربية + الإنجليزية")
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
        
        # ==== توليد المحتوى بالعربية ====
        logger.info("\n" + "=" * 70)
        logger.info("🇸🇦 توليد المحتوى بالعربية...")
        logger.info("=" * 70)
        
        arabic_content = await ai_rewrite_arabic(text)
        if not arabic_content:
            logger.error("❌ فشل في توليد المحتوى العربي")
            await client.disconnect()
            return False
        
        # ==== توليد المحتوى بالإنجليزية ====
        logger.info("\n" + "=" * 70)
        logger.info("🇬🇧 توليد المحتوى بالإنجليزية (لتويتر)...")
        logger.info("=" * 70)
        
        english_content = await ai_rewrite_english(text)
        if not english_content:
            logger.error("❌ فشل في توليد المحتوى الإنجليزي")
            await client.disconnect()
            return False
        
        # إضافة التوقيت
        timestamp = f"\n\n🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        
        arabic_final = arabic_content + timestamp
        english_final = english_content + timestamp
        
        # معاينة المحتوى
        logger.info("\n" + "=" * 70)
        logger.info("📝 معاينة المحتوى العربي:")
        logger.info("=" * 70)
        logger.info(arabic_final[:300] + "...")
        
        logger.info("\n" + "=" * 70)
        logger.info("📝 معاينة المحتوى الإنجليزي (Twitter-ready):")
        logger.info("=" * 70)
        logger.info(english_final[:300] + "...")
        
        # ==== النشر على تيليغرام ====
        logger.info("\n" + "=" * 70)
        logger.info("📤 بدء النشر على تيليغرام...")
        logger.info("=" * 70)
        
        # نشر النسخة العربية (مع الوسائط إن وجدت)
        success_ar = await send_to_telegram(arabic_final, media_path, "AR")
        await asyncio.sleep(3)  # تأخير بين المنشورين
        
        # نشر النسخة الإنجليزية (بدون وسائط لتجنب التكرار)
        success_en = await send_to_telegram(english_final, None, "EN")
        
        # تنظيف الملفات المؤقتة
        if media_path and os.path.exists(media_path):
            try:
                os.remove(media_path)
                logger.info(f"🗑️ تم حذف الملف المؤقت: {media_path}")
            except:
                pass
        
        await client.disconnect()
        
        # النتيجة النهائية
        logger.info("\n" + "=" * 70)
        if success_ar and success_en:
            logger.info("✨ نجح! تم النشر على تيليغرام بنجاح!")
            logger.info("🇸🇦 المنشور العربي: ✅")
            logger.info("🇬🇧 المنشور الإنجليزي: ✅")
            logger.info("\n💡 خطوات ما بعد النشر:")
            logger.info("  1. انسخ المنشور العربي لفيسبوك وإنستغرام")
            logger.info("  2. انسخ المنشور الإنجليزي لتويتر/X")
        elif success_ar or success_en:
            logger.warning("⚠️ نجح جزئياً:")
            logger.info(f"🇸🇦 المنشور العربي: {'✅' if success_ar else '❌'}")
            logger.info(f"🇬🇧 المنشور الإنجليزي: {'✅' if success_en else '❌'}")
        else:
            logger.error("❌ فشل النشر بالكامل")
        logger.info("=" * 70)
        
        return success_ar or success_en
        
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
