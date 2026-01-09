#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram & Twitter Content Aggregator Bot
يجلب المحتوى من قنوات تيليغرام ويعيد نشره بشكل احترافي
Bilingual Edition: Arabic (Telegram) + English Thread (Twitter/X)
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
for i in range(2, 6):  # يدعم حتى 5 مفاتيح (OPENAI_API_KEY_2 إلى OPENAI_API_KEY_5)
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

# عرض عدد المفاتيح المتاحة
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
        # إعادة تعيين القائمة المحظورة لإعطاء فرصة أخرى
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

# ====== LANGUAGE DETECTION & TRANSLATION ======
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
        return "english"  # أو لغة أخرى بأحرف لاتينية

async def translate_to_arabic(text: str, source_lang: str = "auto") -> Optional[str]:
    """ترجمة النص إلى العربية باستخدام OpenAI"""
    
    current_key = get_next_available_key()
    if not current_key:
        logger.error("❌ لا توجد مفاتيح API متاحة للترجمة!")
        return None
    
    key_preview = current_key[:8] + "..." + current_key[-4:]
    logger.info(f"🔄 جاري ترجمة المحتوى من {source_lang} إلى العربية...")
    logger.info(f"🔑 استخدام المفتاح: {key_preview}")
    
    prompt = f"""
أنت مترجم محترف متخصص في ترجمة المحتوى التقني والإخباري.

قم بترجمة النص التالي إلى اللغة العربية الفصحى الحديثة:

✅ متطلبات الترجمة:
1. ترجمة دقيقة واحترافية
2. احتفظ بالمعنى الأصلي كاملاً
3. استخدم مصطلحات تقنية عربية مناسبة
4. اجعل الترجمة طبيعية وسلسة
5. احتفظ بأي روابط URLs كما هي
6. احتفظ بأي أرقام ومعلومات دقيقة

❌ لا تضف:
- أي تعليقات أو ملاحظات
- أي محتوى إضافي
- فقط الترجمة النظيفة

النص المطلوب ترجمته:
{text}

الترجمة العربية:
"""
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {current_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,  # أقل للترجمة الدقيقة
                "max_tokens": 2000
            },
            timeout=45
        )
        
        if response.status_code == 200:
            translation = response.json()['choices'][0]['message']['content'].strip()
            logger.info(f"✅ تمت الترجمة بنجاح! ({len(translation)} حرف)")
            logger.info(f"📝 معاينة: {translation[:100]}...")
            return translation
        
        elif response.status_code == 429:
            logger.error(f"🚫 خطأ 429 في الترجمة - المفتاح {key_preview} وصل للحد")
            mark_key_as_blocked(current_key)
            return None
        
        else:
            logger.error(f"❌ خطأ في الترجمة: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"❌ خطأ في الترجمة: {str(e)}")
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
    """جلب محتوى عشوائي من المصادر مع فلترة ذكية"""
    all_messages = []
    for channel in SOURCE_CHANNELS:
        msgs = await fetch_recent_posts(channel, POSTS_LIMIT)
        all_messages.extend(msgs)
    
    if not all_messages:
        logger.warning("⚠️ لم يتم العثور على محتوى من أي مصدر")
        return None
    
    # فلترة المنشورات: نبقي فقط على المنشورات الطويلة نسبياً
    filtered_messages = [
        msg for msg in all_messages 
        if msg.text and len(msg.text.strip()) >= MIN_CONTENT_LENGTH
    ]
    
    if not filtered_messages:
        logger.warning(f"⚠️ لا توجد منشورات تتجاوز {MIN_CONTENT_LENGTH} حرف")
        logger.info("📊 إحصائيات المنشورات المتاحة:")
        for msg in all_messages[:5]:
            length = len(msg.text) if msg.text else 0
            logger.info(f"  - {length} حرف")
        
        # نجرب تقليل الحد الأدنى مؤقتاً
        min_acceptable = MIN_CONTENT_LENGTH // 2
        filtered_messages = [
            msg for msg in all_messages 
            if msg.text and len(msg.text.strip()) >= min_acceptable
        ]
        
        if not filtered_messages:
            logger.error("❌ لا توجد منشورات مناسبة حتى مع معايير مخففة")
            return None
        else:
            logger.warning(f"⚠️ تم التخفيف: استخدام منشورات أطول من {min_acceptable} حرف")
    
    # ترتيب حسب الطول (نفضل المنشورات الأطول)
    filtered_messages.sort(key=lambda m: len(m.text) if m.text else 0, reverse=True)
    
    # اختيار من أفضل 30% (الأطول)
    top_candidates = filtered_messages[:max(1, len(filtered_messages) // 3)]
    
    selected = random.choice(top_candidates)
    source = selected.chat.username or selected.chat.title or 'unknown'
    text_length = len(selected.text) if selected.text else 0
    
    logger.info(f"✅ تم اختيار منشور من @{source} ({text_length} حرف)")
    return selected

# ====== AI PROCESSING - ARABIC VERSION ======
async def ai_rewrite_arabic(text: str, max_retries: int = 3) -> Optional[str]:
    """إعادة صياغة المحتوى بالعربية للتيليغرام"""
    
    if not text or len(text.strip()) < 50:
        logger.error("❌ المحتوى قصير جداً للمعالجة")
        return None
    
    prompt = f"""
أنت خبير تسويق محتوى عربي على وسائل التواصل الاجتماعي (تيليغرام، فيسبوك، إنستغرام).

IMPORTANT: اكتب المحتوى بالعربية فقط! NOT in English!

أعد صياغة المحتوى التالي بشكل احترافي وجذاب ومطوّل باللغة العربية:

✅ المتطلبات الأساسية (اكتب بالعربية):
1. عنوان قوي جداً وجذاب بالعربية مع إيموجي مميز
2. أعد كتابة المحتوى بـ 8-12 سطراً على الأقل بالعربية (وليس 4-6!)
3. أضف تفاصيل وشرح موسع للفكرة الأساسية بالعربية
4. إذا كان المحتوى بالإنجليزية، ترجمه للعربية بشكل كامل وأضف معلومات إضافية
5. اشرح الفوائد والمميزات بالتفصيل بالعربية
6. أسلوب عربي طبيعي ومحفز وليس ممل
7. أضف دعوة للتفاعل بالعربية في النهاية (مثل: "شارك رأيك"، "جرّبها الآن"، "اشترك لمزيد من المحتوى القيم")
8. أضف 6-10 هاشتاغات متنوعة (بالعربية والإنجليزية معاً)

✅ قواعد المحتوى المطوّل بالعربية:
- إذا كان المحتوى عن أداة: اشرح بالعربية كيف تعمل، من يستفيد منها، لماذا هي مهمة
- إذا كان المحتوى عن خبر: أضف بالعربية السياق، التأثير، التوقعات المستقبلية
- إذا كان المحتوى عن نصيحة: أضف بالعربية أمثلة، خطوات تطبيقية، فوائد واضحة
- اجعل القارئ العربي يشعر أنه تعلّم شيئاً قيماً

✅ أمثلة على الأسلوب المطلوب بالعربية:
- ابدأ بـ: "🎯 اكتشف..."، "💡 تعرف على..."، "🚀 أداة ثورية..."
- استخدم: "✨ المميزات:"، "💪 الفوائد:"، "🔥 لماذا تحتاجها؟"
- اختم بـ: "📢 اشترك الآن..."، "💬 شاركنا تجربتك..."، "👇 جرّبها من هنا..."

❌ تجنب تماماً:
- الكتابة بالإنجليزية! (اكتب بالعربية فقط)
- المحتوى القصير (أقل من 8 أسطر)
- كلمات مثل "بالطبع"، "يُرجى"، "سأكون سعيداً"
- الأسلوب الرسمي الممل
- النسخ الحرفي
- المحتوى السطحي

المحتوى الأصلي (ترجمه للعربية إذا كان بالإنجليزية):
{text}

ملاحظة مهمة جداً: 
- اكتب المحتوى كاملاً بالعربية (باستثناء الهاشتاغات الإنجليزية)
- المحتوى يجب أن يكون طويلاً ومفصلاً وقيماً بالعربية
- إذا كان المحتوى الأصلي بالإنجليزية، ترجمه للعربية بشكل كامل أولاً!
"""
    
    return await _call_openai(prompt, max_retries, "Arabic")

# ====== AI PROCESSING - ENGLISH TWITTER THREAD ======
async def ai_create_twitter_thread(text: str, max_retries: int = 3) -> Optional[List[str]]:
    """إنشاء سلسلة تغريدات احترافية بالإنجليزية لتويتر"""
    
    if not text or len(text.strip()) < 50:
        logger.error("❌ المحتوى قصير جداً للمعالجة")
        return None
    
    prompt = f"""
You are a WORLD-CLASS Twitter/X content strategist specializing in VIRAL threads for international tech-savvy audiences.

CRITICAL: Create content ENTIRELY IN ENGLISH! Do NOT use Arabic!

Create a PROFESSIONAL, ENGAGING TWITTER THREAD (6-10 tweets) from this content:

✅ ABSOLUTE REQUIREMENTS:

1. **LANGUAGE**: 100% ENGLISH ONLY! If the original is in Arabic, TRANSLATE IT FIRST!

2. **HOOK TWEET (Tweet 1)**: 
   - 220-260 characters MAX
   - Mind-blowing hook: provocative question, shocking stat, or bold claim
   - Use power words: "Revolutionary", "Game-changing", "Mind-blowing"
   - Add strategic emoji (1-2 max)
   - Create massive curiosity gap
   - Example: "🚀 AI just changed everything. Here's what 99% of people missed..."

3. **BODY TWEETS (Tweets 2-8)**:
   - Each: 240-270 characters MAX
   - One powerful idea per tweet
   - Use storytelling: Problem → Discovery → Solution → Impact
   - Include concrete examples, stats, or insights
   - Break complex ideas into digestible chunks
   - Use bullet points or numbered lists when helpful
   - Vary sentence structure for engagement

4. **VALUE-PACKED CONTENT**:
   - Teach something valuable
   - Share actionable insights
   - Provide unique perspective
   - Include "how-to" elements if applicable
   - Add context and background
   - Explain WHY it matters

5. **FINAL TWEET**:
   - 200-250 characters MAX
   - Strong CTA: "Like if this helped", "RT to share", "Follow for daily insights"
   - End with 2-3 trending hashtags ONLY
   - Examples: #AI #TechNews #Innovation #Web3 #Startup

6. **FORMATTING**:
   - Use thread indicators: "1/" "2/" etc.
   - Add 🧵 emoji in first tweet
   - Strategic line breaks for readability
   - Bold claims, clear structure

✅ CONTENT EXPANSION RULES:
- If it's about a tool: Explain how it works, who benefits, why it's revolutionary
- If it's news: Add context, implications, future predictions
- If it's a tip: Include examples, step-by-step guidance, clear benefits
- Make readers feel they learned something VALUABLE

❌ STRICTLY AVOID:
- ANY Arabic text whatsoever!
- Generic corporate language
- Tweets over 280 characters
- More than 3 hashtags total
- Boring, predictable openings
- Superficial content

📊 EXACT FORMAT:
TWEET 1: 🧵 [Compelling hook in ENGLISH - max 260 chars]
TWEET 2: [Deep insight in ENGLISH - max 270 chars]
TWEET 3: [Valuable detail in ENGLISH - max 270 chars]
...
TWEET N: [CTA + hashtags in ENGLISH - max 250 chars]

ORIGINAL CONTENT (translate if Arabic):
{text}

REMEMBER: 
- ENGLISH ONLY! 
- Make it VIRAL-worthy!
- Provide REAL VALUE!
- Each tweet must stand alone but flow together!
"""
    
    result = await _call_openai(prompt, max_retries, "Twitter Thread")
    
    if not result:
        return None
    
    # Parse the thread into individual tweets
    tweets = []
    for line in result.split('\n'):
        line = line.strip()
        if line.startswith('TWEET '):
            # Extract tweet content after "TWEET N:"
            tweet_content = line.split(':', 1)[1].strip() if ':' in line else line
            
            # تحقق من عدم وجود نص عربي
            arabic_chars = sum(1 for c in tweet_content if '\u0600' <= c <= '\u06FF')
            if arabic_chars > 5:
                logger.warning(f"⚠️ تخطي تغريدة تحتوي على نص عربي: {tweet_content[:50]}...")
                continue
            
            if tweet_content and len(tweet_content) <= 280:
                tweets.append(tweet_content)
            elif tweet_content and len(tweet_content) > 280:
                logger.warning(f"⚠️ تغريدة طويلة جداً ({len(tweet_content)} حرف)، سيتم اقتصاصها")
                tweets.append(tweet_content[:277] + "...")
    
    if not tweets:
        logger.error("❌ فشل في استخراج التغريدات من النتيجة")
        return None
    
    # تحقق نهائي: على الأقل 50% من المحتوى يجب أن يكون إنجليزي
    total_text = ' '.join(tweets)
    arabic_ratio = sum(1 for c in total_text if '\u0600' <= c <= '\u06FF') / len(total_text) if total_text else 0
    
    if arabic_ratio > 0.3:  # أكثر من 30% عربي
        logger.error(f"❌ نسبة النص العربي مرتفعة جداً ({arabic_ratio*100:.1f}%)!")
        return None
    
    logger.info(f"✅ تم إنشاء سلسلة من {len(tweets)} تغريدة (إنجليزية {(1-arabic_ratio)*100:.1f}%)")
    return tweets

# ====== OPENAI API CALLER WITH MULTI-KEY SUPPORT ======
async def _call_openai(prompt: str, max_retries: int, content_type: str) -> Optional[str]:
    """استدعاء OpenAI API مع دعم مفاتيح متعددة والتبديل التلقائي"""
    
    for attempt in range(1, max_retries + 1):
        # الحصول على المفتاح التالي المتاح
        current_key = get_next_available_key()
        
        if not current_key:
            logger.error("❌ لا توجد مفاتيح API متاحة!")
            return None
        
        key_preview = current_key[:8] + "..." + current_key[-4:] if len(current_key) > 12 else "***"
        logger.info(f"🤖 جاري إنشاء المحتوى ({content_type}) - محاولة {attempt}/{max_retries}")
        logger.info(f"🔑 استخدام المفتاح: {key_preview}")
        
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {current_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.8,
                    "max_tokens": 1500
                },
                timeout=45
            )
            
            if response.status_code == 200:
                result = response.json()['choices'][0]['message']['content'].strip()
                
                # فلترة الردود السيئة
                if content_type == "Arabic":
                    bad_phrases = ["بالطبع", "يُرجى تزويدي", "سأكون سعيد", "عذراً", "آسف"]
                    
                    # تحقق من أن المحتوى بالعربية فعلاً
                    arabic_chars = sum(1 for c in result if '\u0600' <= c <= '\u06FF')
                    total_chars = len([c for c in result if c.isalpha()])
                    arabic_ratio = arabic_chars / total_chars if total_chars > 0 else 0
                    
                    if arabic_ratio < 0.5:  # أقل من 50% عربي
                        logger.warning(f"⚠️ المحتوى العربي ليس بالعربية! ({arabic_ratio*100:.1f}% عربي فقط)، إعادة المحاولة...")
                        if attempt < max_retries:
                            await asyncio.sleep(3)
                            continue
                    
                    # تحقق من طول المحتوى العربي
                    if len(result) < 300:  # المحتوى العربي يجب أن يكون مفصلاً
                        logger.warning(f"⚠️ المحتوى العربي قصير جداً ({len(result)} حرف)، إعادة المحاولة...")
                        if attempt < max_retries:
                            await asyncio.sleep(3)
                            continue
                    
                    logger.info(f"✅ المحتوى العربي جيد: {arabic_ratio*100:.1f}% عربي، {len(result)} حرف")
                    
                elif content_type == "Twitter Thread":
                    bad_phrases = ["of course", "please provide", "i'd be happy", "sorry", "i apologize"]
                    # تحقق من عدم وجود نص عربي في التغريدات
                    arabic_chars = sum(1 for c in result if '\u0600' <= c <= '\u06FF')
                    if arabic_chars > 10:  # إذا كان هناك أكثر من 10 أحرف عربية
                        logger.warning(f"⚠️ التغريدات تحتوي على نص عربي! ({arabic_chars} حرف عربي)، إعادة المحاولة...")
                        if attempt < max_retries:
                            await asyncio.sleep(3)
                            continue
                else:
                    bad_phrases = ["of course", "please provide", "i'd be happy", "sorry", "i apologize"]
                
                if any(phrase.lower() in result[:150].lower() for phrase in bad_phrases):
                    logger.warning(f"⚠️ الذكاء الاصطناعي أعاد رد عام ({content_type})، إعادة المحاولة...")
                    if attempt < max_retries:
                        await asyncio.sleep(3)
                        continue
                
                if len(result) < 100:
                    logger.warning(f"⚠️ المخرج قصير جداً ({content_type})، إعادة المحاولة...")
                    if attempt < max_retries:
                        await asyncio.sleep(3)
                        continue
                
                logger.info(f"✅ تمت المعالجة بنجاح ({content_type}) باستخدام {key_preview}!")
                return result
            
            elif response.status_code == 429:
                # Rate limit exceeded - حظر هذا المفتاح والانتقال للتالي
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', {}).get('message', 'Rate limit exceeded')
                    logger.error(f"🚫 خطأ 429 - المفتاح {key_preview}: {error_msg}")
                except:
                    logger.error(f"🚫 خطأ 429 - المفتاح {key_preview} وصل للحد الأقصى")
                
                # حظر هذا المفتاح
                mark_key_as_blocked(current_key)
                
                # محاولة مع المفتاح التالي فوراً
                logger.info("🔄 التبديل إلى المفتاح التالي...")
                await asyncio.sleep(2)
                continue
            
            elif response.status_code == 401:
                logger.error(f"🔑 خطأ 401 - المفتاح {key_preview} غير صالح!")
                mark_key_as_blocked(current_key)
                logger.info("🔄 التبديل إلى المفتاح التالي...")
                await asyncio.sleep(1)
                continue
            
            elif response.status_code == 403:
                logger.error(f"🚫 خطأ 403 - المفتاح {key_preview} محظور!")
                mark_key_as_blocked(current_key)
                logger.info("🔄 التبديل إلى المفتاح التالي...")
                await asyncio.sleep(1)
                continue
            
            elif response.status_code == 500:
                logger.error(f"⚠️ خطأ 500 - مشكلة في خوادم OpenAI")
                if attempt < max_retries:
                    wait_time = 5
                    logger.info(f"⏳ انتظار {wait_time} ثانية...")
                    await asyncio.sleep(wait_time)
                    continue
            
            else:
                logger.warning(f"⚠️ خطأ من OpenAI: {response.status_code}")
                try:
                    logger.error(f"التفاصيل: {response.text}")
                except:
                    pass
                
        except requests.exceptions.Timeout:
            logger.error(f"⏱️ انتهت مهلة الطلب في المحاولة {attempt}")
        except Exception as e:
            logger.error(f"❌ خطأ في الذكاء الاصطناعي ({content_type}): {str(e)}")
        
        if attempt < max_retries:
            wait_time = 3
            logger.info(f"⏳ انتظار {wait_time} ثانية قبل إعادة المحاولة...")
            await asyncio.sleep(wait_time)
    
    logger.error(f"❌ فشلت المعالجة ({content_type}) بعد جميع المحاولات مع جميع المفاتيح")
    return None

# ====== TELEGRAM SENDER ======
async def send_to_telegram(message: str, media_path: Optional[str] = None, language: str = "AR") -> bool:
    """نشر على قناة تيليغرام"""
    try:
        lang_label = "🇸🇦 Arabic" if language == "AR" else "🇬🇧 English Thread"
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

# ====== FORMAT TWITTER THREAD ======
def create_simple_twitter_thread(text: str) -> List[str]:
    """إنشاء سلسلة تغريدات بسيطة بالإنجليزية كخطة بديلة"""
    tweets = []
    
    # ترجمة بسيطة إذا كان النص بالعربية (نسخة احتياطية)
    if any('\u0600' <= c <= '\u06FF' for c in text):
        # نص عربي - نضع تنويه بسيط
        intro_tweet = "🧵 Sharing insights from Arabic tech content (auto-translated):"
        tweets.append(intro_tweet)
    
    # تقسيم النص إلى أجزاء
    words = text.split()
    current_tweet = ""
    tweet_num = len(tweets) + 1
    
    for word in words:
        # تخطي الكلمات العربية في النسخة الاحتياطية
        if any('\u0600' <= c <= '\u06FF' for c in word):
            continue
            
        if len(current_tweet + word + " ") <= 250:  # ترك مساحة للترقيم
            current_tweet += word + " "
        else:
            if current_tweet.strip():
                tweets.append(f"{tweet_num}/ {current_tweet.strip()}")
                tweet_num += 1
                current_tweet = word + " "
    
    if current_tweet.strip():
        tweets.append(f"{tweet_num}/ {current_tweet.strip()}")
    
    # إذا لم نحصل على تغريدات (كل النص كان عربياً)
    if len(tweets) <= 1:
        tweets = [
            "🧵 Interesting tech content alert!",
            "Just discovered something worth sharing with the community.",
            "Check the original source for full details.",
            "Follow for more tech insights! #AI #Tech #Innovation"
        ]
    else:
        # إضافة تغريدة أخيرة مع هاشتاغات
        tweets.append(f"{len(tweets) + 1}/ Follow for more insights! #AI #Tech #Innovation")
    
    logger.info(f"✅ تم إنشاء سلسلة بسيطة من {len(tweets)} تغريدة (إنجليزية)")
    return tweets[:10]  # حد أقصى 10 تغريدات

def format_twitter_thread(tweets: List[str]) -> str:
    """تنسيق سلسلة التغريدات للعرض"""
    if not tweets:
        return ""
    
    formatted = "🐦 TWITTER/X THREAD (Copy-Paste Ready)\n"
    formatted += "=" * 60 + "\n\n"
    
    for i, tweet in enumerate(tweets, 1):
        char_count = len(tweet)
        status = "✅" if char_count <= 280 else "❌ TOO LONG"
        formatted += f"TWEET {i}/{len(tweets)} ({char_count} chars) {status}\n"
        formatted += f"{tweet}\n"
        formatted += "-" * 60 + "\n\n"
    
    formatted += "💡 INSTRUCTIONS:\n"
    formatted += "1. Copy each tweet individually\n"
    formatted += "2. Post Tweet 1 on Twitter/X\n"
    formatted += "3. Reply to Tweet 1 with Tweet 2\n"
    formatted += "4. Continue replying to create the thread\n"
    formatted += "5. OR use Twitter's thread composer (+ button)\n"
    
    return formatted

# ====== MAIN EXECUTION ======
async def main():
    """البرنامج الرئيسي"""
    logger.info("=" * 70)
    logger.info("🤖 بوت النشر التلقائي (تيليغرام + تويتر) - Multi-API")
    logger.info(f"📅 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info(f"📢 القناة: {TARGET_CHANNEL}")
    logger.info(f"📡 المصادر: {', '.join(SOURCE_CHANNELS)}")
    logger.info(f"🌐 اللغات: العربية (تيليغرام) + الإنجليزية (تويتر)")
    logger.info(f"🔑 المفاتيح المتاحة: {len(OPENAI_API_KEYS)}")
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
        
        original_length = len(text.strip())
        logger.info(f"📄 طول المحتوى الأصلي: {original_length} حرف")
        
        # إذا كان المحتوى قصيراً جداً (أقل من الحد الأدنى)
        if original_length < MIN_CONTENT_LENGTH:
            logger.warning(f"⚠️ المحتوى أقصر من الحد الأدنى ({original_length}/{MIN_CONTENT_LENGTH} حرف)")
            
            # نجرب مع محتوى آخر
            logger.info("🔄 جاري البحث عن محتوى أطول...")
            
            # محاولة ثانية
            post = await get_content_from_sources()
            if not post:
                logger.error("❌ لم يتم العثور على محتوى بديل")
                await client.disconnect()
                return False
            
            text = post.text if post.text else ""
            original_length = len(text.strip())
            logger.info(f"📄 طول المحتوى الجديد: {original_length} حرف")
            
            # إذا فشلت المحاولة الثانية أيضاً
            if original_length < MIN_CONTENT_LENGTH:
                logger.warning(f"⚠️ المحتوى الجديد أيضاً قصير ({original_length} حرف)")
                logger.info("💡 سنحاول المعالجة رغم القصر...")
                # نستمر في المعالجة رغم القصر
        
        logger.info(f"📝 المحتوى الأصلي: {text[:150]}...")
        
        # ==== كشف اللغة والترجمة إذا لزم الأمر ====
        logger.info("\n" + "=" * 70)
        logger.info("🔍 فحص لغة المحتوى...")
        logger.info("=" * 70)
        
        detected_lang = detect_language(text)
        logger.info(f"🌐 اللغة المكتشفة: {detected_lang}")
        
        # المحتوى الذي سيُستخدم للمعالجة
        content_for_processing = text
        
        # إذا لم يكن المحتوى بالعربية، نترجمه أولاً
        if detected_lang != "arabic":
            logger.info(f"🔄 المحتوى بلغة أجنبية ({detected_lang})، جاري الترجمة للعربية...")
            
            translated = await translate_to_arabic(text, detected_lang)
            
            if translated:
                content_for_processing = translated
                logger.info("✅ تمت الترجمة بنجاح!")
                logger.info(f"📝 المحتوى المترجم: {translated[:150]}...")
            else:
                logger.warning("⚠️ فشلت الترجمة، سنستخدم المحتوى الأصلي")
                content_for_processing = text
            
            # تأخير صغير بعد الترجمة
            await asyncio.sleep(3)
        else:
            logger.info("✅ المحتوى بالعربية أصلاً، لا حاجة للترجمة")
            content_for_processing = text
        
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
        logger.info("🇸🇦 توليد المحتوى بالعربية للتيليغرام...")
        logger.info("=" * 70)
        
        # استخدام المحتوى المترجم/الأصلي
        arabic_content = await ai_rewrite_arabic(content_for_processing)
        
        # خطة بديلة: إذا فشل AI، استخدم المحتوى المترجم أو الأصلي
        if not arabic_content:
            logger.warning("⚠️ فشل AI، استخدام المحتوى المعالج مع تحسينات...")
            
            # استخدام المحتوى المترجم إذا كان متاحاً
            if detected_lang != "arabic" and content_for_processing != text:
                # لدينا ترجمة
                arabic_content = f"""📢 {content_for_processing}

💡 اشترك في القناة لمزيد من المحتوى القيم!

#تقنية #تكنولوجيا #ابتكار #Technology #Innovation"""
            else:
                # محتوى عربي أصلاً أو فشلت الترجمة
                arabic_content = f"""📢 {text}

💡 اشترك في القناة لمزيد من المحتوى القيم!

#تقنية #تكنولوجيا #ابتكار #Technology #Innovation"""
        
        # ==== توليد سلسلة التغريدات بالإنجليزية ====
        logger.info("\n" + "=" * 70)
        logger.info("🐦 توليد سلسلة تغريدات احترافية لتويتر/X...")
        logger.info("=" * 70)
        
        # تأخير بين الطلبين لتجنب Rate Limiting
        await asyncio.sleep(5)
        
        # استخدام المحتوى الأصلي للتغريدات (حتى لو كان عربياً، الـ prompt سيترجمه)
        twitter_tweets = await ai_create_twitter_thread(text)
        
        # خطة بديلة للتغريدات
        if not twitter_tweets:
            logger.warning("⚠️ فشل AI للتغريدات، إنشاء نسخة بسيطة...")
            twitter_tweets = create_simple_twitter_thread(text)
        
        # تنسيق سلسلة التغريدات
        twitter_thread_formatted = format_twitter_thread(twitter_tweets)
        
        # إضافة التوقيت للمنشور العربي
        timestamp = f"\n\n🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        arabic_final = arabic_content + timestamp
        
        # معاينة المحتوى
        logger.info("\n" + "=" * 70)
        logger.info("📝 معاينة المحتوى العربي:")
        logger.info("=" * 70)
        logger.info(arabic_final[:300] + "...")
        
        logger.info("\n" + "=" * 70)
        logger.info("📝 معاينة سلسلة التغريدات:")
        logger.info("=" * 70)
        logger.info(twitter_thread_formatted)
        
        # ==== النشر على تيليغرام ====
        logger.info("\n" + "=" * 70)
        logger.info("📤 بدء النشر على تيليغرام...")
        logger.info("=" * 70)
        
        # نشر النسخة العربية (مع الوسائط إن وجدت)
        success_ar = await send_to_telegram(arabic_final, media_path, "AR")
        await asyncio.sleep(3)
        
        # نشر سلسلة التغريدات (بدون وسائط)
        success_en = await send_to_telegram(twitter_thread_formatted, None, "EN")
        
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
            logger.info("🐦 سلسلة التغريدات الإنجليزية: ✅")
            logger.info(f"🔑 المفاتيح المستخدمة: {len(OPENAI_API_KEYS) - len(BLOCKED_KEYS)}/{len(OPENAI_API_KEYS)}")
            logger.info("\n💡 خطوات ما بعد النشر:")
            logger.info("  1. ✅ انسخ المنشور العربي لفيسبوك وإنستغرام")
            logger.info("  2. ✅ انسخ سلسلة التغريدات من تيليغرام وانشرها على تويتر/X")
        elif success_ar or success_en:
            logger.warning("⚠️ نجح جزئياً:")
            logger.info(f"🇸🇦 المنشور العربي: {'✅' if success_ar else '❌'}")
            logger.info(f"🐦 سلسلة التغريدات: {'✅' if success_en else '❌'}")
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
        # عرض معلومات مهمة عند البدء
        logger.info("=" * 70)
        logger.info("⚠️ ملاحظات مهمة:")
        logger.info("1. البوت يدعم حتى 5 مفاتيح OpenAI API")
        logger.info("2. التبديل التلقائي عند نفاد أحد المفاتيح")
        logger.info("3. البوت يعمل كل 30 دقيقة = 48 مرة يومياً")
        logger.info("4. كل تشغيل = 2-3 طلبات API (ترجمة + عربي + إنجليزي)")
        logger.info("5. الترجمة التلقائية من أي لغة للعربية")
        logger.info("6. كشف اللغة: عربي، إنجليزي، روسي، وغيرها")
        logger.info("=" * 70)
        
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
