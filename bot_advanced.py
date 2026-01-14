#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram & Twitter Content Aggregator Bot - IMPROVED VERSION
يجلب المحتوى من قنوات تيليغرام ويعيد نشره بشكل احترافي
✨ NEW: Anti-duplicate system + Russian filter + Quality scoring
"""

import os
import sys
import asyncio
import logging
import requests
import random
import base64
import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
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

for i in range(2, 6):
    key = os.getenv(f"OPENAI_API_KEY_{i}")
    if key:
        OPENAI_API_KEYS.append(key)

BLOCKED_KEYS = set()

# Settings
POSTS_LIMIT = int(os.getenv("POSTS_LIMIT", "20"))  # زيادة العدد للفلترة
MIN_CONTENT_LENGTH = int(os.getenv("MIN_CONTENT_LENGTH", "150"))  # زيادة الحد الأدنى
MAX_CONTENT_AGE_HOURS = int(os.getenv("MAX_CONTENT_AGE_HOURS", "48"))  # محتوى حديث فقط

# ====== NEW: DUPLICATE TRACKING ======
POSTED_HISTORY_FILE = "posted_history.json"
POSTED_HASHES = set()
MAX_HISTORY_SIZE = 500  # حفظ آخر 500 منشور

def load_posted_history():
    """تحميل سجل المنشورات المنشورة سابقاً"""
    global POSTED_HASHES
    try:
        if os.path.exists(POSTED_HISTORY_FILE):
            with open(POSTED_HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                POSTED_HASHES = set(data.get('hashes', []))
                logger.info(f"✅ تم تحميل {len(POSTED_HASHES)} منشور من السجل")
    except Exception as e:
        logger.warning(f"⚠️ فشل تحميل السجل: {e}")
        POSTED_HASHES = set()

def save_posted_history():
    """حفظ سجل المنشورات"""
    try:
        # الاحتفاظ بآخر MAX_HISTORY_SIZE فقط
        hashes_list = list(POSTED_HASHES)
        if len(hashes_list) > MAX_HISTORY_SIZE:
            hashes_list = hashes_list[-MAX_HISTORY_SIZE:]
            POSTED_HASHES.clear()
            POSTED_HASHES.update(hashes_list)
        
        with open(POSTED_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump({'hashes': list(POSTED_HASHES)}, f)
        logger.info(f"💾 تم حفظ السجل ({len(POSTED_HASHES)} منشور)")
    except Exception as e:
        logger.error(f"❌ فشل حفظ السجل: {e}")

def get_content_hash(text: str) -> str:
    """إنشاء hash فريد للمحتوى"""
    # تنظيف النص وإنشاء hash
    clean_text = text.strip().lower()
    clean_text = ''.join(c for c in clean_text if c.isalnum() or c.isspace())
    return hashlib.md5(clean_text.encode()).hexdigest()

def is_duplicate(text: str) -> bool:
    """التحقق من أن المحتوى ليس مكرراً"""
    content_hash = get_content_hash(text)
    if content_hash in POSTED_HASHES:
        logger.warning(f"⚠️ محتوى مكرر تم اكتشافه (Hash: {content_hash[:8]}...)")
        return True
    return False

def mark_as_posted(text: str):
    """وضع علامة على المحتوى كمنشور"""
    content_hash = get_content_hash(text)
    POSTED_HASHES.add(content_hash)
    logger.info(f"✅ تم تسجيل المنشور (Hash: {content_hash[:8]}...)")

# ====== VALIDATION ======
if not all([TARGET_CHANNEL, API_ID, API_HASH, USER_SESSION_BASE64]):
    logger.error("❌ بيانات تيليغرام غير مكتملة")
    sys.exit(1)

if not OPENAI_API_KEYS:
    logger.error("❌ لا يوجد أي مفتاح OpenAI API")
    sys.exit(1)

if not SOURCE_CHANNELS:
    logger.error("❌ قنوات المصدر غير محددة")
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
        logger.error("❌ جميع مفاتيح API محظورة!")
        BLOCKED_KEYS.clear()
        logger.warning("⚠️ إعادة تعيين قائمة المفاتيح...")
        return OPENAI_API_KEYS[0] if OPENAI_API_KEYS else None
    
    return available_keys[0]

def mark_key_as_blocked(api_key: str):
    """وضع علامة على مفتاح كمحظور"""
    if api_key:
        BLOCKED_KEYS.add(api_key)
        key_preview = api_key[:8] + "..." + api_key[-4:]
        logger.warning(f"🚫 تم حظر المفتاح: {key_preview}")
        logger.info(f"📊 المفاتيح المتبقية: {len(OPENAI_API_KEYS) - len(BLOCKED_KEYS)}/{len(OPENAI_API_KEYS)}")

# ====== IMPROVED LANGUAGE DETECTION ======
def detect_language_advanced(text: str) -> Tuple[str, float]:
    """كشف اللغة مع نسبة الدقة"""
    arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
    latin_chars = sum(1 for c in text if c.isalpha() and not ('\u0600' <= c <= '\u06FF') and not ('\u0400' <= c <= '\u04FF'))
    cyrillic_chars = sum(1 for c in text if '\u0400' <= c <= '\u04FF')
    
    total_alpha = arabic_chars + latin_chars + cyrillic_chars
    
    if total_alpha == 0:
        return "unknown", 0.0
    
    arabic_ratio = arabic_chars / total_alpha
    cyrillic_ratio = cyrillic_chars / total_alpha
    latin_ratio = latin_chars / total_alpha
    
    # تحديد اللغة بناءً على أعلى نسبة
    if cyrillic_ratio > 0.3:  # عتبة صارمة للروسية
        return "russian", cyrillic_ratio
    elif arabic_ratio > 0.5:
        return "arabic", arabic_ratio
    elif latin_ratio > 0.5:
        return "english", latin_ratio
    else:
        return "mixed", max(arabic_ratio, latin_ratio, cyrillic_ratio)

# ====== NEW: CONTENT QUALITY SCORING ======
def calculate_content_quality_score(message: Message) -> float:
    """حساب درجة جودة المحتوى (0-100)"""
    score = 50.0  # نقطة البداية
    
    if not message.text:
        return 0.0
    
    text = message.text.strip()
    text_length = len(text)
    
    # 1. طول المحتوى (20 نقطة)
    if text_length > 500:
        score += 20
    elif text_length > 300:
        score += 15
    elif text_length > 200:
        score += 10
    elif text_length < 100:
        score -= 20
    
    # 2. كشف اللغة (25 نقطة)
    lang, confidence = detect_language_advanced(text)
    
    if lang == "russian":
        score -= 50  # عقوبة شديدة للروسية
        logger.warning(f"⚠️ محتوى روسي مكتشف! ({confidence*100:.1f}%)")
    elif lang == "arabic":
        score += 25
    elif lang == "english":
        score += 20
    elif lang == "mixed":
        score += 10
    
    # 3. وجود وسائط (15 نقطة)
    if message.photo:
        score += 15
    elif message.video:
        score += 10
    
    # 4. حداثة المحتوى (15 نقطة)
    if message.date:
        age_hours = (datetime.now(message.date.tzinfo) - message.date).total_seconds() / 3600
        if age_hours < 6:
            score += 15
        elif age_hours < 12:
            score += 10
        elif age_hours < 24:
            score += 5
        elif age_hours > MAX_CONTENT_AGE_HOURS:
            score -= 20
    
    # 5. تنوع المحتوى (10 نقطة)
    unique_words = len(set(text.lower().split()))
    if unique_words > 100:
        score += 10
    elif unique_words > 50:
        score += 5
    
    # 6. التحقق من الكلمات المحظورة (عقوبة)
    spam_keywords = ['spam', 'scam', 'buy now', 'click here', 'free money']
    if any(word in text.lower() for word in spam_keywords):
        score -= 30
    
    # 7. التحقق من التكرار
    if is_duplicate(text):
        score -= 100  # عقوبة قاتلة للمحتوى المكرر
    
    return max(0.0, min(100.0, score))

# ====== TRANSLATION TO ARABIC ======
async def translate_to_arabic(text: str, max_retries: int = 2) -> Optional[str]:
    """ترجمة النص إلى العربية"""
    
    for attempt in range(1, max_retries + 1):
        current_key = get_next_available_key()
        if not current_key:
            logger.error("❌ لا توجد مفاتيح API متاحة!")
            return None
        
        key_preview = current_key[:8] + "..." + current_key[-4:]
        logger.info(f"🔄 ترجمة للعربية - محاولة {attempt}/{max_retries}")
        
        system_message = "أنت مترجم محترف. مهمتك ترجمة أي نص إلى اللغة العربية الفصحى الحديثة."
        
        user_prompt = f"""ترجم هذا النص إلى العربية الفصحى:

النص:
{text}

الترجمة (فقط الترجمة بدون إضافات):"""
        
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
                
                arabic_chars = sum(1 for c in translation if '\u0600' <= c <= '\u06FF')
                total_chars = len([c for c in translation if c.isalpha()])
                
                if total_chars > 0 and (arabic_chars / total_chars) > 0.5:
                    logger.info(f"✅ ترجمة ناجحة ({len(translation)} حرف)")
                    return translation
                    
            elif response.status_code == 429:
                logger.error(f"🚫 خطأ 429 - المفتاح {key_preview}")
                mark_key_as_blocked(current_key)
                await asyncio.sleep(2)
                continue
                
        except Exception as e:
            logger.error(f"❌ خطأ في الترجمة: {str(e)}")
        
        if attempt < max_retries:
            await asyncio.sleep(3)
    
    return None

# ====== TRANSLATION TO ENGLISH ======
async def translate_to_english(text: str, max_retries: int = 2) -> Optional[str]:
    """ترجمة النص إلى الإنجليزية"""
    
    for attempt in range(1, max_retries + 1):
        current_key = get_next_available_key()
        if not current_key:
            return None
        
        logger.info(f"🔄 ترجمة للإنجليزية - محاولة {attempt}/{max_retries}")
        
        system_message = "You are a professional translator. Translate to clear, natural English."
        
        user_prompt = f"""Translate to English:

{text}

English translation (only translation):"""
        
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
                arabic_chars = sum(1 for c in translation if '\u0600' <= c <= '\u06FF')
                
                if arabic_chars == 0 and len(translation) > 20:
                    logger.info(f"✅ ترجمة إنجليزية ناجحة")
                    return translation
                    
            elif response.status_code == 429:
                mark_key_as_blocked(current_key)
                await asyncio.sleep(2)
                continue
                
        except Exception as e:
            logger.error(f"❌ خطأ: {e}")
        
        if attempt < max_retries:
            await asyncio.sleep(3)
    
    return None

# ====== IMPROVED FETCH FROM TELEGRAM ======
async def fetch_recent_posts(channel_username: str, limit: int = 20) -> List[Message]:
    """جلب المنشورات مع تصفية متقدمة"""
    messages = []
    try:
        logger.info(f"📥 جلب من @{channel_username}...")
        async for message in client.iter_messages(channel_username, limit=limit):
            if not message.text:
                continue
            
            text_length = len(message.text.strip())
            if text_length < MIN_CONTENT_LENGTH:
                continue
            
            # تصفية حسب العمر
            if message.date:
                age_hours = (datetime.now(message.date.tzinfo) - message.date).total_seconds() / 3600
                if age_hours > MAX_CONTENT_AGE_HOURS:
                    continue
            
            # تصفية المحتوى الروسي
            lang, confidence = detect_language_advanced(message.text)
            if lang == "russian" and confidence > 0.3:
                logger.warning(f"⚠️ تم رفض منشور روسي ({confidence*100:.1f}%)")
                continue
            
            # تصفية المحتوى المكرر
            if is_duplicate(message.text):
                logger.info(f"⏭️ تخطي محتوى مكرر")
                continue
            
            messages.append(message)
        
        logger.info(f"✅ جلب {len(messages)} منشور مناسب من @{channel_username}")
    except Exception as e:
        logger.error(f"❌ خطأ في جلب المحتوى: {str(e)}")
    
    return messages

async def get_content_from_sources() -> Optional[Message]:
    """جلب أفضل محتوى من المصادر"""
    all_messages = []
    
    for channel in SOURCE_CHANNELS:
        msgs = await fetch_recent_posts(channel, POSTS_LIMIT)
        all_messages.extend(msgs)
    
    if not all_messages:
        logger.warning("⚠️ لم يتم العثور على محتوى مناسب")
        return None
    
    # تقييم جودة كل منشور
    scored_messages = []
    for msg in all_messages:
        score = calculate_content_quality_score(msg)
        if score >= 50:  # عتبة الجودة الدنيا
            scored_messages.append((msg, score))
            logger.info(f"📊 منشور: {score:.1f}/100 - {msg.text[:50]}...")
        else:
            logger.warning(f"⚠️ منشور مرفوض: {score:.1f}/100")
    
    if not scored_messages:
        logger.error("❌ لا توجد منشورات بجودة مقبولة!")
        return None
    
    # ترتيب حسب الجودة
    scored_messages.sort(key=lambda x: x[1], reverse=True)
    
    # اختيار من أفضل 5 منشورات
    top_candidates = scored_messages[:min(5, len(scored_messages))]
    selected_msg, selected_score = random.choice(top_candidates)
    
    source = selected_msg.chat.username or selected_msg.chat.title or 'unknown'
    logger.info(f"✅ تم اختيار منشور من @{source} (جودة: {selected_score:.1f}/100)")
    
    return selected_msg

# ====== AI CONTENT GENERATION - ARABIC ======
async def generate_arabic_post(text: str, max_retries: int = 3) -> Optional[str]:
    """توليد منشور عربي احترافي"""
    
    for attempt in range(1, max_retries + 1):
        current_key = get_next_available_key()
        if not current_key:
            return None
        
        logger.info(f"🤖 توليد منشور عربي - محاولة {attempt}/{max_retries}")
        
        system_message = """أنت خبير تسويق محتوى عربي.
اكتب بالعربية الفصحى الحديثة فقط - ليس بالعامية."""

        user_prompt = f"""أعد كتابة هذا المحتوى بشكل احترافي:

**مهم: العربية الفصحى الحديثة فقط!**

المحتوى:
{text}

المتطلبات:
1. عنوان جذاب مع إيموجي
2. محتوى مفصّل: 10-15 سطر بالعربية الفصحى
3. أسلوب طبيعي ومحفز
4. شرح الفوائد بالتفصيل
5. دعوة للتفاعل
6. 6-10 هاشتاغات

المنشور:"""
        
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
                
                arabic_chars = sum(1 for c in result if '\u0600' <= c <= '\u06FF')
                total_chars = len([c for c in result if c.isalpha()])
                
                if total_chars > 0:
                    arabic_ratio = arabic_chars / total_chars
                    if arabic_ratio > 0.6 and len(result) > 300:
                        logger.info(f"✅ منشور عربي جاهز ({len(result)} حرف)")
                        return result
                        
            elif response.status_code == 429:
                mark_key_as_blocked(current_key)
                await asyncio.sleep(2)
                continue
                
        except Exception as e:
            logger.error(f"❌ خطأ: {e}")
        
        if attempt < max_retries:
            await asyncio.sleep(5)
    
    return None

# ====== AI CONTENT GENERATION - ENGLISH TWITTER ======
async def generate_english_twitter_thread(text: str, max_retries: int = 3) -> Optional[List[str]]:
    """توليد سلسلة تغريدات إنجليزية"""
    
    for attempt in range(1, max_retries + 1):
        current_key = get_next_available_key()
        if not current_key:
            return None
        
        logger.info(f"🐦 توليد تغريدات - محاولة {attempt}/{max_retries}")
        
        system_message = """You are a Twitter/X content strategist.
Write ENTIRELY IN ENGLISH - NO Arabic characters."""

        user_prompt = f"""Create an English Twitter thread (6-10 tweets):

**CRITICAL: 100% ENGLISH ONLY!**

Content:
{text}

Requirements:
1. ENGLISH ONLY - Zero Arabic
2. Translate first if needed
3. Hook tweet: 220-260 chars
4. Body tweets: 240-270 chars each
5. Final tweet: CTA + hashtags
6. Format: "TWEET 1: [content]"

Thread:"""
        
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
                    "temperature": 0.7,
                    "max_tokens": 2000
                },
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()['choices'][0]['message']['content'].strip()
                
                tweets = []
                for line in result.split('\n'):
                    line = line.strip()
                    if line.startswith('TWEET '):
                        if ':' in line:
                            tweet = line.split(':', 1)[1].strip()
                        else:
                            continue
                        
                        # تحقق من عدم وجود عربي
                        arabic_chars = sum(1 for c in tweet if '\u0600' <= c <= '\u06FF')
                        if arabic_chars > 0:
                            continue
                        
                        if len(tweet) > 280:
                            tweet = tweet[:277] + "..."
                        
                        if tweet and len(tweet) > 10:
                            tweets.append(tweet)
                
                if len(tweets) >= 3:
                    all_text = ' '.join(tweets)
                    total_arabic = sum(1 for c in all_text if '\u0600' <= c <= '\u06FF')
                    
                    if total_arabic == 0:
                        logger.info(f"✅ {len(tweets)} تغريدة إنجليزية نظيفة")
                        return tweets
                        
            elif response.status_code == 429:
                mark_key_as_blocked(current_key)
                await asyncio.sleep(2)
                continue
                
        except Exception as e:
            logger.error(f"❌ خطأ: {e}")
        
        if attempt < max_retries:
            await asyncio.sleep(5)
    
    return None

# ====== FORMAT TWITTER THREAD ======
def format_twitter_thread(tweets: List[str]) -> str:
    """تنسيق سلسلة التغريدات"""
    if not tweets:
        return ""
    
    formatted = "🐦 TWITTER/X THREAD\n" + "=" * 60 + "\n\n"
    
    for i, tweet in enumerate(tweets, 1):
        char_count = len(tweet)
        status = "✅" if char_count <= 280 else "❌"
        formatted += f"TWEET {i}/{len(tweets)} ({char_count} chars) {status}\n"
        formatted += f"{tweet}\n" + "-" * 60 + "\n\n"
    
    formatted += "💡 Copy each tweet and post as a thread!\n"
    
    return formatted

# ====== TELEGRAM SENDER ======
async def send_to_telegram(message: str, media_path: Optional[str] = None, label: str = "Post") -> bool:
    """نشر على تيليغرام"""
    try:
        logger.info(f"📤 النشر ({label})...")
        
        MAX_CAPTION = 1024
        MAX_MESSAGE = 4096
        
        if media_path and os.path.exists(media_path):
            if len(message) > MAX_CAPTION:
                await client.send_file(TARGET_CHANNEL, media_path)
                await asyncio.sleep(2)
                
                if len(message) > MAX_MESSAGE:
                    parts = [message[i:i+MAX_MESSAGE-50] for i in range(0, len(message), MAX_MESSAGE-50)]
                    for i, part in enumerate(parts, 1):
                        await client.send_message(TARGET_CHANNEL, f"[{i}/{len(parts)}]\n{part}")
                        if i < len(parts):
                            await asyncio.sleep(1)
                else:
                    await client.send_message(TARGET_CHANNEL, message)
            else:
                await client.send_file(TARGET_CHANNEL, media_path, caption=message)
        else:
            if len(message) > MAX_MESSAGE:
                parts = [message[i:i+MAX_MESSAGE-50] for i in range(0, len(message), MAX_MESSAGE-50)]
                for i, part in enumerate(parts, 1):
                    await client.send_message(TARGET_CHANNEL, f"[{i}/{len(parts)}]\n{part}")
                    if i < len(parts):
                        await asyncio.sleep(1)
            else:
                await client.send_message(TARGET_CHANNEL, message)
        
        logger.info(f"✅ تم النشر ({label})!")
        return True
        
    except Exception as e:
        logger.error(f"❌ فشل النشر ({label}): {e}")
        return False

# ====== MAIN EXECUTION ======
async def main():
    """البرنامج الرئيسي المحسّن"""
    logger.info("=" * 70)
    logger.info("🤖 بوت النشر التلقائي - نسخة محسّنة ✨")
    logger.info(f"📅 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info(f"📢 القناة: {TARGET_CHANNEL}")
    logger.info(f"📡 المصادر: {', '.join(SOURCE_CHANNELS)}")
    logger.info(f"🔑 المفاتيح: {len(OPENAI_API_KEYS)}")
    logger.info("=" * 70)
    
    # تحميل سجل المنشورات
    load_posted_history()
    
    try:
        await client.start()
        logger.info("✅ اتصال بتيليغرام")
        
        # 1️⃣ جلب المحتوى مع الفلترة المتقدمة
        logger.info("\n" + "=" * 70)
        logger.info("📥 الخطوة 1: جلب وفلترة المحتوى")
        logger.info("=" * 70)
        
        post = await get_content_from_sources()
        if not post:
            logger.error("❌ لم يتم العثور على محتوى مناسب")
            await client.disconnect()
            return False
        
        original_text = post.text.strip()
        logger.info(f"✅ محتوى مختار ({len(original_text)} حرف)")
        logger.info(f"📝 معاينة: {original_text[:100]}...")
        
        # 2️⃣ كشف اللغة والتحقق
        logger.info("\n" + "=" * 70)
        logger.info("🔍 الخطوة 2: تحليل اللغة")
        logger.info("=" * 70)
        
        detected_lang, confidence = detect_language_advanced(original_text)
        logger.info(f"🌐 اللغة: {detected_lang} ({confidence*100:.1f}% دقة)")
        
        # رفض المحتوى الروسي نهائياً
        if detected_lang == "russian":
            logger.error("❌ محتوى روسي! تم الرفض.")
            await client.disconnect()
            return False
        
        # الترجمة إذا لزم
        arabic_text = original_text
        
        if detected_lang != "arabic":
            logger.info("🔄 ترجمة للعربية...")
            translated = await translate_to_arabic(original_text)
            
            if translated:
                arabic_text = translated
                logger.info(f"✅ ترجمة ناجحة ({len(arabic_text)} حرف)")
            else:
                logger.warning("⚠️ فشلت الترجمة، استخدام النص الأصلي")
            
            await asyncio.sleep(3)
        else:
            logger.info("✅ المحتوى عربي أصلاً")
        
        # تحميل الوسائط
        media_path = None
        if post.photo or post.video:
            try:
                logger.info("📥 تحميل وسائط...")
                media_path = await post.download_media()
                logger.info(f"✅ تم التحميل")
            except Exception as e:
                logger.warning(f"⚠️ فشل تحميل الوسائط: {e}")
        
        # 3️⃣ توليد المنشور العربي
        logger.info("\n" + "=" * 70)
        logger.info("🇸🇦 الخطوة 3: توليد منشور عربي")
        logger.info("=" * 70)
        
        arabic_post = await generate_arabic_post(arabic_text)
        
        if not arabic_post or len(arabic_post) < 100:
            logger.warning("⚠️ فشل AI، استخدام نص بديل")
            
            if len(BLOCKED_KEYS) >= len(OPENAI_API_KEYS):
                logger.error("⛔ جميع مفاتيح OpenAI مستنفدة!")
            
            # نص بديل
            cleaned_text = arabic_text
            
            # تنظيف العامية
            replacements = {
                'بحطلك': 'سأضع لك',
                'يدورلك': 'يبحث لك',
                'عشان': 'لكي',
                'تبي': 'تريد',
                'هالموقع': 'هذا الموقع',
            }
            
            for old, new in replacements.items():
                cleaned_text = cleaned_text.replace(old, new)
            
            arabic_post = f"""📢 {cleaned_text}

💡 تابعنا للمزيد!

#تقنية #تكنولوجيا #ابتكار #AI #Tech #Innovation"""
        
        # التحقق من المحتوى العربي
        arabic_chars = sum(1 for c in arabic_post if '\u0600' <= c <= '\u06FF')
        if arabic_chars < 50:
            logger.error("❌ المنشور لا يحتوي على عربي كافٍ!")
            
            if len(BLOCKED_KEYS) >= len(OPENAI_API_KEYS):
                logger.error("⛔ السبب: استنفاد مفاتيح API")
                logger.error("💡 أضف مفاتيح إضافية أو انتظر 60 دقيقة")
                await client.disconnect()
                return False
        
        # اقتصاص إذا لزم
        max_length = 1000 if media_path else 4000
        
        if len(arabic_post) > max_length:
            logger.warning(f"⚠️ منشور طويل ({len(arabic_post)} حرف)")
            truncated = arabic_post[:max_length-50]
            
            last_period = truncated.rfind('.')
            last_newline = truncated.rfind('\n')
            cut = max(last_period, last_newline)
            
            if cut > max_length - 200:
                arabic_post = truncated[:cut] + "\n\n..."
            else:
                arabic_post = truncated + "..."
            
            arabic_post += "\n\n#تقنية #Tech"
        
        timestamp = f"\n\n🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        
        if len(arabic_post + timestamp) > max_length:
            available = max_length - len(timestamp) - 20
            arabic_post = arabic_post[:available] + "..."
        
        arabic_final = arabic_post + timestamp
        
        logger.info(f"✅ منشور عربي جاهز ({len(arabic_final)} حرف)")
        logger.info(f"📝 معاينة:\n{arabic_final[:200]}...\n")
        
        # 4️⃣ توليد التغريدات
        logger.info("\n" + "=" * 70)
        logger.info("🐦 الخطوة 4: توليد تغريدات")
        logger.info("=" * 70)
        
        await asyncio.sleep(5)
        
        twitter_tweets = None
        
        try:
            twitter_tweets = await generate_english_twitter_thread(original_text)
        except Exception as e:
            logger.error(f"❌ خطأ: {e}")
        
        if not twitter_tweets:
            logger.warning("⚠️ فشل توليد التغريدات، محاولة ترجمة...")
            
            translated_en = await translate_to_english(original_text)
            
            if translated_en:
                twitter_tweets = [
                    "🧵 Tech news alert!",
                    translated_en[:270] if len(translated_en) <= 270 else translated_en[:267] + "...",
                    "Follow for more! #Tech #AI #Innovation"
                ]
                logger.info("✅ ترجمة بسيطة")
            else:
                twitter_tweets = [
                    "🧵 Breaking tech news!",
                    "Exciting developments in tech today. This could reshape innovation.",
                    "Major implications for the industry. Stay tuned!",
                    "Follow for daily insights! #Tech #AI #Innovation"
                ]
                logger.warning("⚠️ تغريدات عامة")
        
        twitter_formatted = format_twitter_thread(twitter_tweets)
        
        logger.info(f"✅ {len(twitter_tweets)} تغريدة جاهزة")
        logger.info(f"📝 معاينة:\n{twitter_formatted[:300]}...\n")
        
        # 5️⃣ النشر
        logger.info("\n" + "=" * 70)
        logger.info("📤 الخطوة 5: النشر")
        logger.info("=" * 70)
        
        if not arabic_final or len(arabic_final) < 50:
            logger.error("❌ منشور عربي فارغ!")
            await client.disconnect()
            return False
        
        if not twitter_formatted or len(twitter_formatted) < 50:
            logger.error("❌ تغريدات فارغة!")
            await client.disconnect()
            return False
        
        logger.info("✅ المنشوران جاهزان")
        logger.info(f"   📝 عربي: {len(arabic_final)} حرف")
        logger.info(f"   📝 إنجليزي: {len(twitter_formatted)} حرف")
        logger.info("")
        
        # نشر المنشور العربي
        logger.info("📤 نشر عربي (1/2)...")
        success_ar = await send_to_telegram(arabic_final, media_path, "🇸🇦 عربي")
        
        if not success_ar:
            logger.error("❌ فشل النشر العربي!")
        else:
            # تسجيل المحتوى كمنشور
            mark_as_posted(original_text)
            save_posted_history()
        
        await asyncio.sleep(5)
        
        # نشر التغريدات
        logger.info("📤 نشر إنجليزي (2/2)...")
        success_en = await send_to_telegram(twitter_formatted, None, "🐦 إنجليزي")
        
        # تنظيف
        if media_path and os.path.exists(media_path):
            try:
                os.remove(media_path)
                logger.info("🗑️ تم حذف الملف المؤقت")
            except:
                pass
        
        await client.disconnect()
        
        # 6️⃣ النتيجة
        logger.info("\n" + "=" * 70)
        logger.info("📊 النتيجة النهائية")
        logger.info("=" * 70)
        
        if success_ar and success_en:
            logger.info("✨ نجح! تم النشر بنجاح!")
            logger.info("")
            logger.info("📱 المنشورات:")
            logger.info("  1️⃣ عربي → فيسبوك/إنستغرام ✅")
            logger.info("  2️⃣ إنجليزي → تويتر/X ✅")
            logger.info("")
            logger.info("🔑 إحصائيات:")
            logger.info(f"  • المفاتيح المستخدمة: {len(OPENAI_API_KEYS) - len(BLOCKED_KEYS)}/{len(OPENAI_API_KEYS)}")
            logger.info(f"  • اللغة الأصلية: {detected_lang}")
            logger.info(f"  • عدد المنشورات المسجلة: {len(POSTED_HASHES)}")
            logger.info("")
        elif success_ar or success_en:
            logger.warning("⚠️ نجح جزئياً!")
            logger.info(f"  🇸🇦 عربي: {'✅' if success_ar else '❌'}")
            logger.info(f"  🐦 إنجليزي: {'✅' if success_en else '❌'}")
        else:
            logger.error("❌ فشل النشر!")
        
        logger.info("=" * 70)
        
        return success_ar and success_en
        
    except Exception as e:
        logger.error(f"❌ خطأ فادح: {e}")
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
        logger.info("║" + " " * 10 + "🤖 بوت النشر التلقائي - نسخة محسّنة ✨" + " " * 10 + "║")
        logger.info("╚" + "=" * 68 + "╝")
        logger.info("")
        logger.info("✨ الميزات الجديدة:")
        logger.info("  🚫 منع تكرار المنشورات (نظام Hash)")
        logger.info("  🇷🇺 فلترة صارمة للمحتوى الروسي")
        logger.info("  📊 تقييم جودة المحتوى (0-100)")
        logger.info("  ⏰ محتوى حديث فقط (48 ساعة)")
        logger.info("  💾 حفظ سجل المنشورات")
        logger.info("")
        logger.info("📋 الخطة:")
        logger.info("  1️⃣  جلب + فلترة متقدمة")
        logger.info("  2️⃣  كشف اللغة + رفض الروسية")
        logger.info("  3️⃣  توليد منشور عربي")
        logger.info("  4️⃣  توليد تغريدات إنجليزية")
        logger.info("  5️⃣  نشر + تسجيل في السجل")
        logger.info("")
        logger.info("⚙️  الإعدادات:")
        logger.info(f"  • مفاتيح OpenAI: {len(OPENAI_API_KEYS)}")
        logger.info(f"  • القنوات المصدر: {len(SOURCE_CHANNELS)}")
        logger.info(f"  • الحد الأدنى: {MIN_CONTENT_LENGTH} حرف")
        logger.info(f"  • عمر المحتوى الأقصى: {MAX_CONTENT_AGE_HOURS} ساعة")
        logger.info("")
        
        if len(OPENAI_API_KEYS) < 2:
            logger.warning("⚠️  تحذير: مفتاح واحد فقط!")
            logger.warning("   أضف مفاتيح إضافية (OPENAI_API_KEY_2, etc.)")
            logger.info("")
        
        logger.info("🚀 بدء التشغيل...")
        logger.info("=" * 70)
        logger.info("")
        
        result = asyncio.run(main())
        
        logger.info("")
        if result:
            logger.info("🎉 نجح البرنامج!")
            sys.exit(0)
        else:
            logger.info("⚠️  انتهى مع أخطاء")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("\n⚠️  إيقاف بواسطة المستخدم")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ خطأ فادح: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
