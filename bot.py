#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram Auto-Post Bot with OpenAI
Enhanced version with error handling, logging, and retry logic
"""

import os
import sys
import time
import logging
import requests
from datetime import datetime
from typing import Optional

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

# Validation
if not all([TELEGRAM_TOKEN, TELEGRAM_CHANNEL, OPENAI_API_KEY]):
    logger.error("❌ Missing required environment variables!")
    logger.error("Required: TELEGRAM_TOKEN, TELEGRAM_CHANNEL, OPENAI_API_KEY")
    sys.exit(1)

# ====== AI PROCESSING ======
def ai_translate_and_summarize(text: str, max_retries: int = 3) -> Optional[str]:
    """
    Process text with OpenAI API
    
    Args:
        text: Input text to process
        max_retries: Maximum number of retry attempts
    
    Returns:
        Processed text or None if failed
    """
    prompt = f"""
    لخص النص التالي وترجمه إلى العربية إن لزم الأمر.
    اكتب بأسلوب احترافي وجذاب للقراء.
    يجب أن يتضمن:
    - عنوان قصير مع إيموجي مناسب
    - ملخص في 3-5 أسطر فقط
    - أسلوب واضح ومباشر
    
    النص:
    {text}
    """
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🤖 Processing with OpenAI (attempt {attempt}/{max_retries})...")
            
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.4,
                    "max_tokens": 500
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
        except requests.exceptions.RequestException as e:
            logger.warning(f"⚠️ Network error: {str(e)}")
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
    """
    Send message to Telegram channel
    
    Args:
        message: Message to send
        max_retries: Maximum number of retry attempts
    
    Returns:
        True if successful, False otherwise
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"📤 Sending to Telegram (attempt {attempt}/{max_retries})...")
            
            response = requests.post(
                url,
                json={
                    "chat_id": TELEGRAM_CHANNEL,
                    "text": message,
                    "parse_mode": "HTML",
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
                
        except requests.exceptions.Timeout:
            logger.warning(f"⏱️ Request timeout (attempt {attempt}/{max_retries})")
        except requests.exceptions.RequestException as e:
            logger.warning(f"⚠️ Network error: {str(e)}")
        except Exception as e:
            logger.error(f"❌ Unexpected error: {str(e)}")
        
        if attempt < max_retries:
            wait_time = attempt * 2
            logger.info(f"⏳ Waiting {wait_time}s before retry...")
            time.sleep(wait_time)
    
    logger.error("❌ Failed to send message after all retries")
    return False

# ====== CONTENT FETCHER ======
def fetch_content() -> Optional[str]:
    """
    Fetch content from external sources
    You can customize this to fetch from RSS, APIs, websites, etc.
    
    Returns:
        Fetched content or None
    """
    # Example: Static content (replace with your source)
    sample_content = """
    OpenAI announced a major breakthrough in artificial intelligence research.
    The new GPT-5 model demonstrates unprecedented reasoning capabilities
    and can solve complex problems across multiple domains.
    """
    
    # Example: Fetch from RSS feed
    # try:
    #     response = requests.get("https://example.com/rss", timeout=10)
    #     # Parse RSS and extract content
    #     return parsed_content
    # except Exception as e:
    #     logger.error(f"Failed to fetch content: {e}")
    #     return None
    
    return sample_content.strip()

# ====== MAIN EXECUTION ======
def main():
    """Main execution flow"""
    logger.info("=" * 60)
    logger.info("🚀 Telegram Auto-Post Bot Started")
    logger.info(f"📅 Timestamp: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info("=" * 60)
    
    # Step 1: Fetch content
    logger.info("📥 Fetching content...")
    raw_content = fetch_content()
    
    if not raw_content:
        logger.error("❌ No content available. Exiting.")
        sys.exit(1)
    
    logger.info(f"✅ Content fetched: {len(raw_content)} characters")
    
    # Step 2: Process with AI
    processed_content = ai_translate_and_summarize(raw_content)
    
    if not processed_content:
        logger.error("❌ AI processing failed. Exiting.")
        sys.exit(1)
    
    # Step 3: Add footer
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
        logger.info("✨ Mission accomplished! Bot execution completed successfully.")
        logger.info("=" * 60)
        sys.exit(0)
    else:
        logger.error("=" * 60)
        logger.error("💔 Mission failed. Please check the logs.")
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
