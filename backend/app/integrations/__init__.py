"""External integrations — all mock-aware.

Each client checks ``settings`` to decide live vs. MOCK. In MOCK mode it
returns a plausible synthetic result and logs the intent, so the full demo
runs before any API key is provisioned. This is the graceful-degradation
contract the rest of the system relies on.
"""
from .elevenlabs_voice import VoiceIntent, arm_voice
from .openweather import OpenWeatherClient
from .telegram import TelegramClient

__all__ = ["OpenWeatherClient", "TelegramClient", "VoiceIntent", "arm_voice"]
