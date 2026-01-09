#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram & Twitter Content Aggregator Bot
يجلب المحتوى من قنوات تيليغرام ويعيد نشره بشكل احترافي
Bilingual Edition: Arabic (Facebook/Instagram) + English (Twitter/X)
Multi-API Support: Automatic Failover between multiple OpenAI keys
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

# OpenAI - Multiple API Keys Support
OPENAI_API_KEYS = []
primary_key = os.getenv("OPENAI_API_KEY")
if primary_key:
    OPENAI_API_KEYS.append(primary_key)

# إضافة مفاتيح إضافية
for i in range(2, 6):
    key = os.getenv(f"OPENAI_API_KEY_{i}")
    if key:
        OPENAI_API_KEYS.append(key)

# تتبع المفاتيح المحظورة مؤقتاً
BLOCKED_KEYS = set()

# Settings
POSTS_LIMIT = int(os.getenv("POSTS_LIMIT", "10"))
MIN_CONTENT_LENGTH = int(os.getenv("MIN_CONTENT_LENGTH", "100"))

# ====== VALIDATION ======
if not all([TARGET_CHANNEL, API_ID, API_HASH, USER_SESSION_BASE64]):
    logger.error("❌ بيانات تيليغرام غير مكتملة")
    sys.exit(1)

if not OPENAI_API_KEYS:
    logger.error("❌ لا يوجد أي مفتاح OpenAI API")
    sys.exit(1)

if not SOURCE_CHANNELS:
    logger.error("❌ قنوات المصدر غير محددة (SOURCE_CHANNELS)")
    sys.exit(1)

logger.info(f"🔑 عدد مفاتيح OpenAI المتاحة: {len(OPENAI_API_KEYS)}")

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

# ====== API KEY MANAGER ======
def get_next_available_key() -> Optional[str]:
    """الحصول على المفتاح التالي المتاح"""
    available_keys = [key for key in OPENAI_API_KEYS if key not in BLOCKED_KEYS]
    
    if not available_keys:
        logger.error("❌ جميع مفاتيح API محظورة أو مستنفدة!")
        BLOCKED_KEYS.clear()
        logger.warning("⚠️ إعادة تعيين قائمة المفاتيح المحظورة...")
        return OPENAI_API_KEYS[0] if OPENAI_API_KEYS else None
    
    return available_keys[0]

def mark_key_as_blocked(api_key: str):
    """وضع علامة على مفتاح كمحظور مؤقتاً"""
    if api_key:
        BLOCKED_KEYS.add(api_key)
        key_preview = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
        logger.warning(f"🚫 تم حظر المفتاح مؤقتاً: {key_preview}")
        logger.info(f"📊 المفاتيح المتبقية: {len(OPENAI_API_KEYS) - len(BLOCKED_KEYS)}/{len(OPENAI_API_KEYS)}")

# ====== LANGUAGE DETECTION ======
def detect_language(text: str) -> str:
    """كشف اللغة الأساسية للنص"""
    arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
    latin_chars = sum(1 for c in text if c.isalpha() and not ('\u0600' <= c <= '\u06FF'))
    cyrillic_chars = sum(1 for c in text if '\u0400' <= c <= '\u04FF')
    
    total_alpha = arabic_chars + latin_chars + cyrillic_chars
    
    if total_alpha == 0:
        return "unknown"
    
    arabic_ratio = arabic_chars / total_alpha
    
    if arabic_ratio > 0.5:
        return "arabic"
    elif cyrillic_chars > latin_chars:
        return "russian"
    else:
        return "other"

# ====== TRANSLATION TO ARABIC ======
async def translate_to_arabic(text: str, max_retries: int = 2) -> Optional[str]:
    """ترجمة النص إلى العربية باستخدام OpenAI"""
    
    for attempt in range(1, max_retries + 1):
        current_key = get_next_available_key()
        if not current_key:
            logger.error("❌ لا توجد مفاتيح API متاحة للترجمة!")
            return None
        
        key_preview = current_key[:8] + "..." + current_key[-4:]
        logger.info(f"🔄 ترجمة المحتوى إلى العربية - محاولة {attempt}/{max_retries}")
        logger.info(f"🔑 استخدام المفتاح: {key_preview}")
        
        system_message = "أنت مترجم محترف. مهمتك ترجمة أي نص إلى العربية الفصحى بدقة عالية."
        
        user_prompt = f"""ترجم هذا النص إلى العربية الفصحى:

{text}

الترجمة العربية (فقط الترجمة بدون أي إضافات):"""
        
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {current_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2000
                },
                timeout=45
            )
            
            if response.status_code == 200:
                translation = response.json()['choices'][0]['message']['content'].strip()
                
                # تحقق من أن الترجمة بالعربية
                arabic_chars = sum(1 for c in translation if '\u0600' <= c <= '\u06FF')
                total_chars = len([c for c in translation if c.isalpha()])
                
                if total_chars > 0:
                    arabic_ratio = arabic_chars / total_chars
                    if arabic_ratio > 0.5:
                        logger.info(f"✅ تمت الترجمة بنجاح! ({len(translation)} حرف)")
                        return translation
                    else:
                        logger.warning(f"⚠️ الترجمة ليست بالعربية ({arabic_ratio*100:.1f}% فقط)")
                        if attempt < max_retries:
                            await asyncio.sleep(2)
                            continue
                
            elif response.status_code == 429:
                logger.error(f"🚫 خطأ 429 - المفتاح {key_preview}")
                mark_key_as_blocked(current_key)
                
                # تحذير إذا نفذت المفاتيح
                if len(BLOCKED_KEYS) >= len(OPENAI_API_KEYS):
                    logger.error("❌ جميع المفاتيح وصلت للحد الأقصى في الترجمة!")
                    return None
                
                await asyncio.sleep(2)
                continue
                
            else:
                logger.error(f"❌ خطأ في الترجمة: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ خطأ في الترجمة: {str(e)}")
        
        if attempt < max_retries:
            await asyncio.sleep(3)
    
    logger.error("❌ فشلت الترجمة بعد جميع المحاولات")
    return None

# ====== TRANSLATION TO ENGLISH ======
async def translate_to_english(text: str, max_retries: int = 2) -> Optional[str]:
    """ترجمة النص إلى الإنجليزية باستخدام OpenAI"""
    
    for attempt in range(1, max_retries + 1):
        current_key = get_next_available_key()
        if not current_key:
            logger.error("❌ لا توجد مفاتيح API متاحة للترجمة!")
            return None
        
        key_preview = current_key[:8] + "..." + current_key[-4:]
        logger.info(f"🔄 ترجمة المحتوى إلى الإنجليزية - محاولة {attempt}/{max_retries}")
        logger.info(f"🔑 استخدام المفتاح: {key_preview}")
        
        system_message = "You are a professional translator. Your task is to translate any text to clear, natural English."
        
        user_prompt = f"""Translate this text to English:

{text}

English translation (only the translation, no extra comments):"""
        
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {current_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2000
                },
                timeout=45
            )
            
            if response.status_code == 200:
                translation = response.json()['choices'][0]['message']['content'].strip()
                
                # تحقق من أن الترجمة بالإنجليزية (لا توجد أحرف عربية)
                arabic_chars = sum(1 for c in translation if '\u0600' <= c <= '\u06FF')
                
                if arabic_chars == 0 and len(translation) > 20:
                    logger.info(f"✅ تمت الترجمة للإنجليزية بنجاح! ({len(translation)} حرف)")
                    return translation
                else:
                    logger.warning(f"⚠️ الترجمة تحتوي على {arabic_chars} حرف عربي")
                    if attempt < max_retries:
                        await asyncio.sleep(2)
                        continue
                
            elif response.status_code == 429:
                logger.error(f"🚫 خطأ 429 - المفتاح {key_preview}")
                mark_key_as_blocked(current_key)
                await asyncio.sleep(2)
                continue
                
            else:
                logger.error(f"❌ خطأ في الترجمة: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ خطأ في الترجمة: {str(e)}")
        
        if attempt < max_retries:
            await asyncio.sleep(3)
    
    logger.error("❌ فشلت الترجمة للإنجليزية بعد جميع المحاولات")
    return None

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
    
    filtered_messages = [
        msg for msg in all_messages 
        if msg.text and len(msg.text.strip()) >= MIN_CONTENT_LENGTH
    ]
    
    if not filtered_messages:
        min_acceptable = MIN_CONTENT_LENGTH // 2
        filtered_messages = [
            msg for msg in all_messages 
            if msg.text and len(msg.text.strip()) >= min_acceptable
        ]
        
        if not filtered_messages:
            logger.error("❌ لا توجد منشورات مناسبة")
            return None
    
    filtered_messages.sort(key=lambda m: len(m.text) if m.text else 0, reverse=True)
    top_candidates = filtered_messages[:max(1, len(filtered_messages) // 3)]
    selected = random.choice(top_candidates)
    
    source = selected.chat.username or selected.chat.title or 'unknown'
    text_length = len(selected.text) if selected.text else 0
    logger.info(f"✅ تم اختيار منشور من @{source} ({text_length} حرف)")
    
    return selected

# ====== AI CONTENT GENERATION - ARABIC ======
async def generate_arabic_post(text: str, max_retries: int = 3) -> Optional[str]:
    """توليد منشور عربي احترافي لفيسبوك/إنستغرام"""
    
    for attempt in range(1, max_retries + 1):
        current_key = get_next_available_key()
        if not current_key:
            logger.error("❌ لا توجد مفاتيح API متاحة!")
            return None
        
        key_preview = current_key[:8] + "..." + current_key[-4:]
        logger.info(f"🤖 توليد المنشور العربي - محاولة {attempt}/{max_retries}")
        logger.info(f"🔑 استخدام المفتاح: {key_preview}")
        
        system_message = """أنت خبير تسويق محتوى عربي متخصص في إنشاء منشورات جذابة لفيسبوك وإنستغرام.
يجب أن تكتب باللغة العربية فقط وبأسلوب احترافي جذاب."""

        user_prompt = f"""أعد كتابة هذا المحتوى بشكل احترافي وجذاب للنشر على فيسبوك وإنستغرام:

📋 المحتوى الأصلي:
{text}

✅ المتطلبات:
1. عنوان قوي وجذاب بالعربية مع إيموجي مناسب
2. محتوى مفصّل: 10-15 سطراً بالعربية
3. أسلوب طبيعي ومحفز (ليس رسمياً ممل)
4. شرح الفوائد والمميزات بالتفصيل
5. إضافة قيمة حقيقية للقارئ
6. دعوة واضحة للتفاعل في النهاية
7. 6-10 هاشتاغات (عربي + إنجليزي)

❌ تجنب:
- الكتابة بالإنجليزية
- المحتوى القصير
- الأسلوب الممل
- كلمات: "بالطبع"، "يُرجى"

المنشور العربي الاحترافي:"""
        
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {current_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.8,
                    "max_tokens": 2000
                },
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()['choices'][0]['message']['content'].strip()
                
                # تحقق من أن المحتوى بالعربية
                arabic_chars = sum(1 for c in result if '\u0600' <= c <= '\u06FF')
                total_chars = len([c for c in result if c.isalpha()])
                
                if total_chars > 0:
                    arabic_ratio = arabic_chars / total_chars
                    
                    if arabic_ratio > 0.6 and len(result) > 300:
                        logger.info(f"✅ تم توليد المنشور العربي ({len(result)} حرف، {arabic_ratio*100:.1f}% عربي)")
                        return result
                    else:
                        logger.warning(f"⚠️ المحتوى غير مناسب (عربي: {arabic_ratio*100:.1f}%, طول: {len(result)})")
                        if attempt < max_retries:
                            await asyncio.sleep(3)
                            continue
                
            elif response.status_code == 429:
                logger.error(f"🚫 خطأ 429 - المفتاح {key_preview}")
                mark_key_as_blocked(current_key)
                await asyncio.sleep(2)
                continue
                
            else:
                logger.error(f"❌ خطأ: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ خطأ في التوليد: {str(e)}")
        
        if attempt < max_retries:
            await asyncio.sleep(5)
    
    logger.error("❌ فشل توليد المنشور العربي")
    return None

# ====== AI CONTENT GENERATION - ENGLISH TWITTER ======
async def generate_english_twitter_thread(text: str, max_retries: int = 3) -> Optional[List[str]]:
    """توليد سلسلة تغريدات إنجليزية لتويتر"""
    
    for attempt in range(1, max_retries + 1):
        current_key = get_next_available_key()
        if not current_key:
            logger.error("❌ لا توجد مفاتيح API متاحة!")
            return None
        
        key_preview = current_key[:8] + "..." + current_key[-4:]
        logger.info(f"🐦 توليد سلسلة التغريدات - محاولة {attempt}/{max_retries}")
        logger.info(f"🔑 استخدام المفتاح: {key_preview}")
        
        system_message = """You are a professional Twitter/X content strategist.
You MUST write ENTIRELY IN ENGLISH - NO Arabic characters allowed.
If the input is in Arabic or another language, you MUST translate it to English first.
Create engaging, viral-worthy Twitter threads in perfect English."""

        user_prompt = f"""Create a professional English Twitter/X thread (6-10 tweets) from this content.

⚠️ CRITICAL: Write ONLY in ENGLISH! If the content below is in Arabic or another language, TRANSLATE IT TO ENGLISH FIRST!

📋 Original Content:
{text}

✅ STRICT Requirements:
1. **100% ENGLISH ONLY** - Zero Arabic characters!
2. If content is Arabic → Translate to English first
3. Hook tweet (Tweet 1): 220-260 chars, compelling opening with emoji
4. Body tweets: 240-270 chars each, one powerful idea per tweet
5. Final tweet: Strong CTA + 2-3 hashtags
6. Each tweet MUST be under 280 characters
7. Format EXACTLY: "TWEET 1: [content]", "TWEET 2: [content]", etc.

✅ Content Strategy:
- Start with a hook that creates curiosity
- Provide actionable insights and value
- Use storytelling elements
- End with clear call-to-action

❌ ABSOLUTELY FORBIDDEN:
- ANY Arabic text or characters (أ، ب، ت، etc.)
- ANY non-English language
- Generic corporate speak
- Tweets over 280 characters

REMEMBER: Every single word must be in ENGLISH!

The Twitter Thread in ENGLISH:"""
        
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {current_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.7,  # أقل قليلاً للحصول على نتائج أكثر دقة
                    "max_tokens": 2000
                },
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()['choices'][0]['message']['content'].strip()
                
                # استخراج التغريدات
                tweets = []
                for line in result.split('\n'):
                    line = line.strip()
                    if line.startswith('TWEET '):
                        # استخراج المحتوى بعد "TWEET N:"
                        if ':' in line:
                            tweet_content = line.split(':', 1)[1].strip()
                        else:
                            continue
                        
                        # تحقق صارم من عدم وجود أي أحرف عربية
                        arabic_chars = sum(1 for c in tweet_content if '\u0600' <= c <= '\u06FF')
                        
                        if arabic_chars > 0:  # حتى حرف عربي واحد = رفض
                            logger.warning(f"⚠️ رفض تغريدة تحتوي على {arabic_chars} حرف عربي")
                            logger.warning(f"   المحتوى المرفوض: {tweet_content[:100]}...")
                            continue
                        
                        # تحقق من الطول
                        if len(tweet_content) > 280:
                            logger.warning(f"⚠️ تغريدة طويلة ({len(tweet_content)} حرف)، اقتصاص...")
                            tweet_content = tweet_content[:277] + "..."
                        
                        if tweet_content and len(tweet_content) > 10:  # تأكد أنها ليست فارغة
                            tweets.append(tweet_content)
                
                # تحقق نهائي شامل
                if len(tweets) >= 3:
                    # فحص جميع التغريدات معاً
                    all_tweets_text = ' '.join(tweets)
                    total_arabic = sum(1 for c in all_tweets_text if '\u0600' <= c <= '\u06FF')
                    total_chars = len(all_tweets_text)
                    
                    if total_arabic > 0:
                        arabic_percentage = (total_arabic / total_chars * 100) if total_chars > 0 else 0
                        logger.error(f"❌ السلسلة تحتوي على {total_arabic} حرف عربي ({arabic_percentage:.1f}%)")
                        logger.error("   إعادة المحاولة...")
                        
                        if attempt < max_retries:
                            await asyncio.sleep(4)
                            continue
                        else:
                            # في المحاولة الأخيرة، استخدم خطة بديلة
                            logger.warning("⚠️ استخدام خطة بديلة للتغريدات")
                            return None
                    
                    logger.info(f"✅ تم توليد {len(tweets)} تغريدة إنجليزية نظيفة 100%")
                    
                    # طباعة معاينة للتأكد
                    for i, tweet in enumerate(tweets[:3], 1):
                        logger.info(f"   Tweet {i}: {tweet[:80]}...")
                    
                    return tweets
                else:
                    logger.warning(f"⚠️ عدد التغريدات قليل ({len(tweets)})")
                    if attempt < max_retries:
                        await asyncio.sleep(4)
                        continue
                
            elif response.status_code == 429:
                logger.error(f"🚫 خطأ 429 - المفتاح {key_preview}")
                mark_key_as_blocked(current_key)
                await asyncio.sleep(2)
                continue
                
            else:
                logger.error(f"❌ خطأ: {response.status_code}")
                try:
                    error_detail = response.json()
                    logger.error(f"   التفاصيل: {error_detail}")
                except:
                    pass
                
        except Exception as e:
            logger.error(f"❌ خطأ في التوليد: {str(e)}")
        
        if attempt < max_retries:
            wait_time = 5
            logger.info(f"⏳ انتظار {wait_time} ثانية قبل إعادة المحاولة...")
            await asyncio.sleep(wait_time)
    
    logger.error("❌ فشل توليد سلسلة التغريدات بعد جميع المحاولات")
    return None

# ====== FORMAT TWITTER THREAD ======
def format_twitter_thread(tweets: List[str]) -> str:
    """تنسيق سلسلة التغريدات"""
    if not tweets:
        return ""
    
    formatted = "🐦 TWITTER/X THREAD - Copy & Paste Each Tweet\n"
    formatted += "=" * 60 + "\n\n"
    
    for i, tweet in enumerate(tweets, 1):
        char_count = len(tweet)
        status = "✅" if char_count <= 280 else "❌"
        formatted += f"📝 TWEET {i}/{len(tweets)} ({char_count} chars) {status}\n"
        formatted += f"{tweet}\n"
        formatted += "-" * 60 + "\n\n"
    
    formatted += "💡 How to Post:\n"
    formatted += "1. Copy Tweet 1 → Post on Twitter/X\n"
    formatted += "2. Reply with Tweet 2\n"
    formatted += "3. Continue replying to build the thread\n"
    
    return formatted

# ====== TELEGRAM SENDER ======
async def send_to_telegram(message: str, media_path: Optional[str] = None, label: str = "Post") -> bool:
    """نشر على قناة تيليغرام"""
    try:
        logger.info(f"📤 جاري النشر على تيليغرام ({label})...")
        
        if media_path and os.path.exists(media_path):
            await client.send_file(TARGET_CHANNEL, media_path, caption=message)
        else:
            await client.send_message(TARGET_CHANNEL, message)
        
        logger.info(f"✅ تم النشر ({label}) بنجاح!")
        return True
    except Exception as e:
        logger.error(f"❌ فشل النشر ({label}): {str(e)}")
        return False

# ====== MAIN EXECUTION ======
async def main():
    """البرنامج الرئيسي"""
    logger.info("=" * 70)
    logger.info("🤖 بوت النشر التلقائي - عربي + إنجليزي")
    logger.info(f"📅 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info(f"📢 القناة: {TARGET_CHANNEL}")
    logger.info(f"📡 المصادر: {', '.join(SOURCE_CHANNELS)}")
    logger.info(f"🔑 المفاتيح: {len(OPENAI_API_KEYS)}")
    logger.info("=" * 70)
    
    try:
        # الاتصال بـ Telegram
        await client.start()
        logger.info("✅ تم الاتصال بتيليغرام")
        
        # 1️⃣ جلب المحتوى من القنوات
        logger.info("\n" + "=" * 70)
        logger.info("📥 الخطوة 1: جلب المحتوى من القنوات المصدر")
        logger.info("=" * 70)
        
        post = await get_content_from_sources()
        if not post:
            logger.error("❌ لم يتم العثور على محتوى")
            await client.disconnect()
            return False
        
        original_text = post.text.strip()
        logger.info(f"✅ تم جلب المحتوى ({len(original_text)} حرف)")
        logger.info(f"📝 معاينة: {original_text[:150]}...")
        
        # 2️⃣ كشف اللغة والترجمة إذا لزم
        logger.info("\n" + "=" * 70)
        logger.info("🔍 الخطوة 2: كشف اللغة والترجمة")
        logger.info("=" * 70)
        
        detected_lang = detect_language(original_text)
        logger.info(f"🌐 اللغة المكتشفة: {detected_lang}")
        
        # المحتوى العربي (مترجم أو أصلي)
        arabic_text = original_text
        
        if detected_lang != "arabic":
            logger.info("🔄 المحتوى بلغة أخرى، جاري الترجمة للعربية...")
            translated = await translate_to_arabic(original_text)
            
            if translated:
                arabic_text = translated
                logger.info(f"✅ تمت الترجمة ({len(arabic_text)} حرف)")
                logger.info(f"📝 معاينة الترجمة: {arabic_text[:150]}...")
            else:
                logger.warning("⚠️ فشلت الترجمة، سنستخدم النص الأصلي")
            
            await asyncio.sleep(3)
        else:
            logger.info("✅ المحتوى بالعربية أصلاً")
        
        # تحميل الوسائط
        media_path = None
        if post.photo or post.video:
            try:
                logger.info("📥 تحميل الوسائط...")
                media_path = await post.download_media()
                logger.info(f"✅ تم تحميل الوسائط")
            except Exception as e:
                logger.warning(f"⚠️ فشل تحميل الوسائط: {str(e)}")
        
        # 3️⃣ توليد المنشور العربي
        logger.info("\n" + "=" * 70)
        logger.info("🇸🇦 الخطوة 3: توليد المنشور العربي (فيسبوك/إنستغرام)")
        logger.info("=" * 70)
        
        arabic_post = await generate_arabic_post(arabic_text)
        
        if not arabic_post or len(arabic_post) < 100:
            logger.warning("⚠️ فشل AI أو المحتوى قصير، استخدام النص المعالج مباشرة")
            
            # التحقق من سبب الفشل
            if len(BLOCKED_KEYS) >= len(OPENAI_API_KEYS):
                logger.error("")
                logger.error("=" * 70)
                logger.error("⛔ تنبيه: جميع مفاتيح OpenAI وصلت للحد الأقصى!")
                logger.error("=" * 70)
                logger.error("")
                logger.error("سيتم استخدام المحتوى الأصلي بدون معالجة AI.")
                logger.error("للحصول على أفضل النتائج:")
                logger.error("  • أضف مفاتيح OpenAI إضافية (حتى 5 مفاتيح)")
                logger.error("  • انتظر 60 دقيقة قبل التشغيل مرة أخرى")
                logger.error("")
            
            # استخدام النص العربي (المترجم أو الأصلي) مع تحسين بسيط
            arabic_post = f"""📢 {arabic_text}

💡 تابعنا للمزيد من المحتوى التقني القيم!

#تقنية #تكنولوجيا #ابتكار #ذكاء_اصطناعي #AI #Tech #Innovation #TechNews"""
        
        # التأكد من وجود محتوى عربي
        arabic_chars_in_post = sum(1 for c in arabic_post if '\u0600' <= c <= '\u06FF')
        if arabic_chars_in_post < 50:
            logger.error("❌ المنشور العربي لا يحتوي على عربي كافٍ!")
            # خطة طوارئ: استخدام الترجمة أو النص الأصلي
            if arabic_text and any('\u0600' <= c <= '\u06FF' for c in arabic_text):
                arabic_post = f"""📢 {arabic_text}

💡 تابعنا للمزيد!

#تقنية #AI #Tech"""
            else:
                logger.error("❌ لا يوجد محتوى عربي!")
                await client.disconnect()
                return False
        
        # إضافة التوقيت
        timestamp = f"\n\n🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        arabic_final = arabic_post + timestamp
        
        logger.info(f"✅ المنشور العربي جاهز ({len(arabic_final)} حرف)")
        logger.info(f"📝 معاينة:\n{arabic_final[:300]}...\n")
        
        # 4️⃣ توليد سلسلة التغريدات الإنجليزية
        logger.info("\n" + "=" * 70)
        logger.info("🐦 الخطوة 4: توليد سلسلة التغريدات (تويتر/X)")
        logger.info("=" * 70)
        
        await asyncio.sleep(5)  # تأخير بين الطلبين
        
        # تعريف المتغير أولاً
        twitter_tweets = None
        
        try:
            twitter_tweets = await generate_english_twitter_thread(original_text)
        except Exception as e:
            logger.error(f"❌ خطأ في توليد التغريدات: {str(e)}")
            twitter_tweets = None
        
        # 4️⃣ توليد سلسلة التغريدات الإنجليزية
        logger.info("\n" + "=" * 70)
        logger.info("🐦 الخطوة 4: توليد سلسلة التغريدات (تويتر/X)")
        logger.info("=" * 70)
        
        await asyncio.sleep(5)  # تأخير بين الطلبين
        
        if not twitter_tweets:
            logger.warning("⚠️ فشل AI للتغريدات، محاولة أخيرة بترجمة مباشرة...")
            
            # محاولة أخيرة: طلب ترجمة بسيطة للإنجليزية
            translated_english = await translate_to_english(original_text)
            
            if translated_english:
                # استخدام الترجمة الإنجليزية
                twitter_tweets = [
                    "🧵 Tech news alert!",
                    translated_english[:270] if len(translated_english) <= 270 else translated_english[:267] + "...",
                    "Follow for more updates! #Tech #AI #Innovation"
                ]
                logger.info("✅ تم استخدام ترجمة إنجليزية بسيطة")
            else:
                # خطة طوارئ نهائية
                twitter_tweets = [
                    "🧵 Breaking tech news!",
                    "Exciting developments happening in the tech world today. This could reshape how we think about innovation.",
                    "Major implications for the industry. Stay tuned for more details and analysis!",
                    "Follow for daily tech insights! #Tech #AI #Innovation"
                ]
                logger.warning("⚠️ استخدام تغريدات عامة كخطة طوارئ")
        
        twitter_formatted = format_twitter_thread(twitter_tweets)
        
        logger.info(f"✅ سلسلة التغريدات جاهزة ({len(twitter_tweets)} تغريدة)")
        logger.info(f"📝 معاينة:\n{twitter_formatted[:400]}...\n")
        
        # 5️⃣ النشر على تيليغرام
        logger.info("\n" + "=" * 70)
        logger.info("📤 الخطوة 5: النشر على تيليغرام")
        logger.info("=" * 70)
        
        # التحقق النهائي قبل النشر
        if not arabic_final or len(arabic_final) < 50:
            logger.error("❌ المنشور العربي فارغ أو قصير جداً!")
            await client.disconnect()
            return False
        
        if not twitter_formatted or len(twitter_formatted) < 50:
            logger.error("❌ سلسلة التغريدات فارغة!")
            await client.disconnect()
            return False
        
        logger.info("✅ كلا المنشورين جاهزان للنشر")
        logger.info(f"   📝 المنشور العربي: {len(arabic_final)} حرف")
        logger.info(f"   📝 سلسلة التغريدات: {len(twitter_formatted)} حرف")
        logger.info("")
        
        # نشر المنشور العربي (مع الوسائط)
        logger.info("📤 نشر المنشور العربي (1/2)...")
        success_ar = await send_to_telegram(arabic_final, media_path, "🇸🇦 عربي - فيسبوك/إنستغرام")
        
        if not success_ar:
            logger.error("❌ فشل نشر المنشور العربي!")
        
        await asyncio.sleep(5)
        
        # نشر سلسلة التغريدات الإنجليزية (بدون وسائط)
        logger.info("📤 نشر سلسلة التغريدات الإنجليزية (2/2)...")
        success_en = await send_to_telegram(twitter_formatted, None, "🐦 إنجليزي - تويتر/X")
        
        # تنظيف الملفات المؤقتة
        if media_path and os.path.exists(media_path):
            try:
                os.remove(media_path)
                logger.info("🗑️ تم حذف الملف المؤقت")
            except:
                pass
        
        await client.disconnect()
        
        # 6️⃣ النتيجة النهائية
        logger.info("\n" + "=" * 70)
        logger.info("📊 النتيجة النهائية")
        logger.info("=" * 70)
        
        if success_ar and success_en:
            logger.info("✨ نجح! تم النشر بنجاح على تيليغرام!")
            logger.info("")
            logger.info("📱 المنشورات المُرسلة:")
            logger.info("  1️⃣ المنشور العربي → فيسبوك / إنستغرام ✅")
            logger.info("  2️⃣ سلسلة التغريدات الإنجليزية → تويتر / X ✅")
            logger.info("")
            logger.info("🔑 إحصائيات:")
            logger.info(f"  • المفاتيح المستخدمة: {len(OPENAI_API_KEYS) - len(BLOCKED_KEYS)}/{len(OPENAI_API_KEYS)}")
            logger.info(f"  • اللغة الأصلية: {detected_lang}")
            logger.info(f"  • تمت الترجمة: {'نعم' if detected_lang != 'arabic' else 'لا'}")
            logger.info("")
            logger.info("💡 الخطوات التالية:")
            logger.info("  ✅ افتح قناة تيليغرام الخاصة بك")
            logger.info("  ✅ انسخ المنشور الأول (العربي) → انشره على فيسبوك وإنستغرام")
            logger.info("  ✅ انسخ المنشور الثاني (الإنجليزي) → انشره على تويتر/X")
            logger.info("")
        elif success_ar or success_en:
            logger.warning("⚠️ نجح جزئياً!")
            logger.info(f"  🇸🇦 المنشور العربي: {'✅ نجح' if success_ar else '❌ فشل'}")
            logger.info(f"  🐦 سلسلة التغريدات: {'✅ نجح' if success_en else '❌ فشل'}")
        else:
            logger.error("❌ فشل النشر بالكامل!")
            logger.error("  تحقق من الأخطاء أعلاه وحاول مرة أخرى")
        
        logger.info("=" * 70)
        
        return success_ar and success_en
        
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
        logger.info("")
        logger.info("╔" + "=" * 68 + "╗")
        logger.info("║" + " " * 15 + "🤖 بوت النشر التلقائي المتعدد اللغات" + " " * 15 + "║")
        logger.info("╚" + "=" * 68 + "╝")
        logger.info("")
        logger.info("📋 الخطة:")
        logger.info("  1️⃣  جلب المحتوى من القنوات المصدر (أي لغة)")
        logger.info("  2️⃣  كشف اللغة + ترجمة للعربية (إذا لزم)")
        logger.info("  3️⃣  توليد منشور عربي احترافي → فيسبوك/إنستغرام")
        logger.info("  4️⃣  توليد سلسلة تغريدات إنجليزية → تويتر/X")
        logger.info("  5️⃣  إرسال المنشورين إلى قناة تيليغرام")
        logger.info("")
        logger.info("⚙️  الإعدادات:")
        logger.info(f"  • عدد مفاتيح OpenAI: {len(OPENAI_API_KEYS)}")
        logger.info(f"  • القنوات المصدر: {len(SOURCE_CHANNELS)}")
        logger.info(f"  • الحد الأدنى للمحتوى: {MIN_CONTENT_LENGTH} حرف")
        logger.info("")
        logger.info("🚀 بدء التشغيل...")
        logger.info("=" * 70)
        logger.info("")
        
        result = asyncio.run(main())
        
        logger.info("")
        if result:
            logger.info("🎉 انتهى البرنامج بنجاح!")
            sys.exit(0)
        else:
            logger.info("⚠️  انتهى البرنامج مع وجود أخطاء")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("\n⚠️  تم الإيقاف بواسطة المستخدم")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ خطأ فادح: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
