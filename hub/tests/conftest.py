"""Keep tests offline and quiet: no API keys, no database, no speech.

Set before `server` is imported. load_dotenv() never overrides variables that already
exist, so the real keys in .env are not picked up here.
"""

import os
import sys
from pathlib import Path

os.environ.update({
    "GEMINI_API_KEY": "",
    "ELEVENLABS_API_KEY": "",
    "TIGER_DB_URL": "",
    "VOICE_FALLBACK_SAY": "0",
    "LEAP_MOCK": "0",
})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
