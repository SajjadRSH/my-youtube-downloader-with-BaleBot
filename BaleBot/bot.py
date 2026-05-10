#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Multi-Platform Bot for YouTube Downloader
Supports Telegram and Telegram-compatible APIs (Eitaa, Bale, etc.)
Triggers GitHub Actions workflow and receives downloaded videos
"""

import os
import sys
import logging
import requests
from typing import Optional, Dict, Any
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from telegram.request import HTTPXRequest
from dotenv import load_dotenv

# ================== Configuration ==================

load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')

# API Base URL (change this for different platforms)
# Telegram: https://api.telegram.org
# Eitaa: https://eitaayar.ir
# Bale: https://tapi.bale.ai
# Rubika: (not officially supported)
API_BASE_URL = os.getenv('API_BASE_URL', 'https://tapi.bale.ai')

# Platform name (for logging and messages)
PLATFORM_NAME = os.getenv('PLATFORM_NAME', 'Bale')

# GitHub Configuration
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_REPO = os.getenv('GITHUB_REPO')
WORKFLOW_FILE = '02-yt-dl.yml'
GITHUB_BRANCH = 'master'  # or 'main'

# Allowed Users (optional - leave empty to allow all)
ALLOWED_USER_IDS = []  # e.g., [123456789, 987654321]

# File size limits (in MB) - adjust based on platform
# Telegram: 2048 MB (2GB)
# Eitaa: 2048 MB (2GB)
# Bale: 50 MB
MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', '2048'))

# Request timeout settings
REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '300'))  # 5 minutes
UPLOAD_TIMEOUT = int(os.getenv('UPLOAD_TIMEOUT', '1800'))  # 30 minutes

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== Helper Functions ==================

def validate_config() -> bool:
    """Validate configuration before starting bot"""
    if BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        logger.error("❌ BOT_TOKEN not configured!")
        return False
    
    if GITHUB_TOKEN == 'YOUR_GITHUB_TOKEN_HERE':
        logger.error("❌ GITHUB_TOKEN not configured!")
        return False
    
    if GITHUB_REPO == 'username/repo-name':
        logger.error("❌ GITHUB_REPO not configured!")
        return False
    
    # Validate API base URL
    if not API_BASE_URL.startswith('http'):
        logger.error("❌ Invalid API_BASE_URL!")
        return False
    
    return True


def get_platform_info() -> Dict[str, Any]:
    """Get platform-specific information"""
    platforms = {
        'api.telegram.org': {
            'name': 'Telegram',
            'max_file_size': 2048,
            'emoji': '✈️',
            'supports_streaming': True
        },
        'eitaayar.ir': {
            'name': 'Eitaa',
            'max_file_size': 2048,
            'emoji': '🇮🇷',
            'supports_streaming': False
        },
        'tapi.bale.ai': {
            'name': 'Bale',
            'max_file_size': 50,
            'emoji': '📱',
            'supports_streaming': False
        }
    }
    
    # Extract domain from API_BASE_URL
    domain = API_BASE_URL.replace('https://', '').replace('http://', '').split('/')[0]
    
    # Return platform info or default
    return platforms.get(domain, {
        'name': PLATFORM_NAME,
        'max_file_size': MAX_FILE_SIZE_MB,
        'emoji': '🤖',
        'supports_streaming': False
    })


def is_user_allowed(user_id: int) -> bool:
    """Check if user is allowed to use the bot"""
    if not ALLOWED_USER_IDS:
        return True
    return user_id in ALLOWED_USER_IDS


def is_valid_youtube_url(url: str) -> bool:
    """Validate YouTube URL"""
    url = url.strip().lower()
    valid_domains = [
        'youtube.com',
        'youtu.be',
        'www.youtube.com',
        'm.youtube.com'
    ]
    return any(domain in url for domain in valid_domains)


def trigger_github_workflow(
    youtube_url: str,
    user_id: int,
    quality: str = 'best',
    download_subtitles: bool = False
) -> tuple[bool, str]:
    """
    Trigger GitHub Actions workflow
    
    Returns:
        (success: bool, message: str)
    """
    api_url = f'https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches'
    
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'ref': GITHUB_BRANCH,
        'inputs': {
            'youtube_urls': youtube_url,
            'quality': quality,
            'download_subtitles': str(download_subtitles).lower(),
            'user_id': str(user_id),
            'api_base_url': API_BASE_URL,  # Pass API base URL to workflow
            'bot_token': BOT_TOKEN  # Pass bot token to workflow
        }
    }
    
    try:
        logger.info(f"Triggering workflow for user {user_id}: {youtube_url}")
        response = requests.post(api_url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 204:
            logger.info(f"✅ Workflow triggered successfully for user {user_id}")
            return True, "✅ درخواست شما ثبت شد. پس از دانلود، ویدیو ارسال خواهد شد."
        
        elif response.status_code == 404:
            logger.error(f"❌ Workflow not found: {WORKFLOW_FILE}")
            return False, "❌ خطا: Workflow یافت نشد. لطفاً تنظیمات را بررسی کنید."
        
        elif response.status_code == 401:
            logger.error("❌ GitHub authentication failed")
            return False, "❌ خطا: احراز هویت GitHub ناموفق بود."
        
        else:
            logger.error(f"❌ Workflow trigger failed: {response.status_code} - {response.text}")
            return False, f"❌ خطا در ارسال درخواست (کد {response.status_code})"
    
    except requests.exceptions.Timeout:
        logger.error("❌ Request timeout")
        return False, "❌ خطا: زمان درخواست به پایان رسید."
    
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Request failed: {e}")
        return False, f"❌ خطا در ارتباط با GitHub: {str(e)}"


# ================== Bot Handlers ==================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    user_id = user.id
    platform_info = get_platform_info()
    
    logger.info(f"User {user_id} ({user.username}) started the bot on {platform_info['name']}")
    
    if not is_user_allowed(user_id):
        await update.message.reply_text("❌ شما مجاز به استفاده از این بات نیستید.")
        return
    
    welcome_message = f"""
{platform_info['emoji']} سلام {user.first_name}!

من یک ربات دانلود ویدیو از یوتیوب هستم که روی **{platform_info['name']}** فعال است.

📝 **نحوه استفاده:**
فقط لینک ویدیوی یوتیوب را برای من ارسال کنید.

⚙️ **دستورات:**
/start - شروع
/help - راهنما
/quality - تنظیم کیفیت (پیش‌فرض: بهترین)
/status - وضعیت بات
/platform - اطلاعات پلتفرم

🎬 **کیفیت‌های پشتیبانی شده:**
• best - بهترین کیفیت
• 2160 - 4K
• 1440 - 2K
• 1080 - Full HD
• 720 - HD
• 480 - SD
• audio - فقط صدا

⚠️ **محدودیت‌ها:**
• حداکثر حجم فایل: {platform_info['max_file_size']} MB
• زمان دانلود: حداکثر 3 ساعت
"""
    
    await update.message.reply_text(welcome_message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """
📖 **راهنمای استفاده:**

1️⃣ لینک ویدیوی یوتیوب را کپی کنید
2️⃣ لینک را در چت ارسال کنید
3️⃣ منتظر بمانید تا دانلود و آپلود انجام شود

💡 **نکات:**
• می‌توانید چند لینک را با Enter جدا کنید
• برای تغییر کیفیت از /quality استفاده کنید
• ویدیوهای خصوصی پشتیبانی نمی‌شوند

❓ **مشکل دارید؟**
از /status برای بررسی وضعیت بات استفاده کنید.
"""
    await update.message.reply_text(help_text)


async def quality_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /quality command"""
    user_id = update.effective_user.id
    
    if not context.args:
        current_quality = context.user_data.get('quality', 'best')
        await update.message.reply_text(
            f"🎬 کیفیت فعلی: **{current_quality}**\n\n"
            "برای تغییر کیفیت:\n"
            "`/quality best` - بهترین\n"
            "`/quality 1080` - Full HD\n"
            "`/quality 720` - HD\n"
            "`/quality audio` - فقط صدا",
            parse_mode='Markdown'
        )
        return
    
    quality = context.args[0].lower()
    valid_qualities = ['best', '2160', '1440', '1080', '720', '480', 'audio']
    
    if quality not in valid_qualities:
        await update.message.reply_text(
            f"❌ کیفیت نامعتبر!\n\n"
            f"کیفیت‌های معتبر: {', '.join(valid_qualities)}"
        )
        return
    
    context.user_data['quality'] = quality
    await update.message.reply_text(f"✅ کیفیت به **{quality}** تغییر یافت.", parse_mode='Markdown')
    logger.info(f"User {user_id} changed quality to {quality}")


async def platform_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /platform command - show platform information"""
    platform_info = get_platform_info()
    
    platform_message = f"""
{platform_info['emoji']} **اطلاعات پلتفرم:**

📱 نام: {platform_info['name']}
🌐 API Base URL: `{API_BASE_URL}`
📦 حداکثر حجم فایل: {platform_info['max_file_size']} MB
🎥 پشتیبانی از Streaming: {'✅ بله' if platform_info['supports_streaming'] else '❌ خیر'}

⚙️ **تنظیمات:**
• Request Timeout: {REQUEST_TIMEOUT}s
• Upload Timeout: {UPLOAD_TIMEOUT}s
"""
    
    await update.message.reply_text(platform_message, parse_mode='Markdown')


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    user_id = update.effective_user.id
    quality = context.user_data.get('quality', 'best')
    platform_info = get_platform_info()
    
    # Check GitHub API connectivity
    try:
        response = requests.get(
            f'https://api.github.com/repos/{GITHUB_REPO}',
            headers={'Authorization': f'token {GITHUB_TOKEN}'},
            timeout=5
        )
        github_status = "✅ متصل" if response.status_code == 200 else "❌ قطع"
    except:
        github_status = "❌ قطع"
    
    # Check Bot API connectivity
    try:
        response = requests.get(
            f'{API_BASE_URL}/bot{BOT_TOKEN}/getMe',
            timeout=5
        )
        bot_status = "✅ فعال" if response.status_code == 200 else "❌ غیرفعال"
    except:
        bot_status = "❌ غیرفعال"
    
    status_message = f"""
📊 **وضعیت بات:**

🤖 ربات: {bot_status}
{platform_info['emoji']} پلتفرم: {platform_info['name']}
🔗 GitHub: {github_status}
🎬 کیفیت: {quality}
👤 User ID: `{user_id}`

📦 Repository: `{GITHUB_REPO}`
🌐 API: `{API_BASE_URL}`
"""
    
    await update.message.reply_text(status_message, parse_mode='Markdown')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages (YouTube URLs)"""
    user = update.effective_user
    user_id = user.id
    message_text = update.message.text.strip()
    
    # Check if user is allowed
    if not is_user_allowed(user_id):
        await update.message.reply_text("❌ شما مجاز به استفاده از این بات نیستید.")
        return
    
    # Validate YouTube URL
    if not is_valid_youtube_url(message_text):
        await update.message.reply_text(
            "❌ لطفاً یک لینک معتبر یوتیوب ارسال کنید.\n\n"
            "مثال:\n"
            "`https://www.youtube.com/watch?v=dQw4w9WgXcQ`\n"
            "`https://youtu.be/dQw4w9WgXcQ`",
            parse_mode='Markdown'
        )
        return
    
    # Get user preferences
    quality = context.user_data.get('quality', 'best')
    download_subtitles = context.user_data.get('subtitles', False)
    
    # Send processing message
    processing_msg = await update.message.reply_text(
        "⏳ در حال پردازش درخواست...\n"
        f"🎬 کیفیت: {quality}"
    )
    
    # Trigger GitHub workflow
    success, message = trigger_github_workflow(
        youtube_url=message_text,
        user_id=user_id,
        quality=quality,
        download_subtitles=download_subtitles
    )
    
    # Update message
    await processing_msg.edit_text(message)
    
    if success:
        await update.message.reply_text(
            "⏰ زمان تقریبی: 5-30 دقیقه\n"
            "📥 ویدیو به صورت خودکار ارسال خواهد شد."
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Exception while handling an update: {context.error}")
    
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "❌ خطایی رخ داد. لطفاً دوباره تلاش کنید."
        )


# ================== Main ==================

def main():
    """Start the bot"""
    
    # Validate configuration
    if not validate_config():
        logger.error("❌ Configuration validation failed. Please check your settings.")
        sys.exit(1)
    
    platform_info = get_platform_info()
    
    logger.info(f"🚀 Starting Bot on {platform_info['name']}...")
    logger.info(f"🌐 API Base URL: {API_BASE_URL}")
    logger.info(f"📦 GitHub Repository: {GITHUB_REPO}")
    logger.info(f"📄 Workflow File: {WORKFLOW_FILE}")
    logger.info(f"📊 Max File Size: {platform_info['max_file_size']} MB")
    
    # Create custom request with base URL
    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=REQUEST_TIMEOUT,
        read_timeout=REQUEST_TIMEOUT,
    )
    
    # Create application with custom base URL
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .base_url(f"{API_BASE_URL}/bot")
        .base_file_url(f"{API_BASE_URL}/file/bot")
        .request(request)
        .build()
    )
    
    # Add handlers
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('quality', quality_command))
    application.add_handler(CommandHandler('status', status_command))
    application.add_handler(CommandHandler('platform', platform_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start bot
    logger.info(f"✅ Bot started successfully on {platform_info['name']}!")
    logger.info("Press Ctrl+C to stop")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
