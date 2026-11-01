"""
Central configuration: environment variables, logging, intents, and small
constants shared across cogs. Runtime/dependency checks for voice and AI
live next to the code that needs them (cogs/music.py, cogs/ai.py) instead
of here, so a missing dependency only disables that one feature.
"""
import logging
import os
import sys

import discord
from discord.ext import commands
from dotenv import load_dotenv

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')  # never hardcode a fallback key here
YT_COOKIES_FILE = os.getenv('YT_COOKIES_FILE')

BOT_NAME = "Cadence"
BOT_CREATOR = "BASH"
AI_MODEL = "meta-llama/llama-3.2-3b-instruct:free"
VISION_MODEL = "qwen/qwen-2.5-vl-7b-instruct:free"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('discord.log', encoding='utf-8', mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('discord_bot')

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.guilds = True


async def get_prefix(bot: commands.Bot, message: discord.Message):
    if message.guild:
        custom = bot.data.prefixes.get(str(message.guild.id))
        if custom:
            return commands.when_mentioned_or(custom)(bot, message)
    return commands.when_mentioned_or('-')(bot, message)