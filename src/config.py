import os
from dotenv import load_dotenv

load_dotenv()

# Multi-key support: comma-separated in DEEPSEEK_API_KEYS, or single DEEPSEEK_API_KEY
_raw_keys = os.environ.get("DEEPSEEK_API_KEYS", "")
if _raw_keys:
    DEEPSEEK_API_KEYS = [k.strip() for k in _raw_keys.split(",") if k.strip()]
else:
    single = os.environ.get("DEEPSEEK_API_KEY", "")
    DEEPSEEK_API_KEYS = [single] if single else []

DEEPSEEK_BASE_URL = "https://api.deepseek.com"

AVAILABLE_MODELS = {
    "deepseek-v4-pro": "DeepSeek V4 Pro (推荐)",
    "deepseek-chat": "DeepSeek V3",
    "deepseek-reasoner": "DeepSeek R1",
}

DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
if DEEPSEEK_MODEL not in AVAILABLE_MODELS:
    DEEPSEEK_MODEL = "deepseek-v4-pro"

NOTES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "notes")

# Concurrency: default to 3x number of keys
DEEPSEEK_CONCURRENCY = int(os.environ.get(
    "DEEPSEEK_CONCURRENCY",
    str(max(len(DEEPSEEK_API_KEYS) * 3, 3))
))

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

WECHAT_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 12; SM-G9910) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Version/4.0 Chrome/107.0.5304.141 Mobile Safari/537.36 "
    "MicroMessenger/8.0.47.2560(0x28002F5B) WeChat/arm64 Weixin"
)
