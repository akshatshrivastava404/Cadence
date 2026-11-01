"""
Persistent bot data. Stored as JSON with an atomic write (temp file +
os.replace) so a crash or kill mid-save can't corrupt the file.
"""
import json
import os
from collections import defaultdict

from config import logger


class BotData:
    def __init__(self):
        self.greeting_channels: dict[str, str] = {}
        self.user_xp: dict[tuple[int, int], int] = {}
        self.last_award: dict[tuple[int, int], object] = {}
        self.spam_history: dict[tuple[int, int], list] = defaultdict(list)
        self.banned_words: dict[str, set[str]] = defaultdict(set)            # guild_id(str) -> words
        self.welcome_messages: dict[str, str] = {}
        self.auto_role: dict[str, str] = {}
        self.warning_count: dict[str, int] = defaultdict(int)                # "guildid_userid" -> count
        self.custom_commands: dict[str, dict[str, str]] = defaultdict(dict)  # guild_id(str) -> {trigger: response}
        self.reaction_roles: dict[str, str] = {}
        self.prefixes: dict[str, str] = {}
        self.mod_log_channels: dict[str, str] = {}

    def save_data(self):
        try:
            data_dict = {
                'greeting_channels': self.greeting_channels,
                'user_xp': {f"{k[0]}_{k[1]}": v for k, v in self.user_xp.items()},
                'banned_words': {gid: list(words) for gid, words in self.banned_words.items()},
                'welcome_messages': self.welcome_messages,
                'auto_role': self.auto_role,
                'warning_count': dict(self.warning_count),
                'custom_commands': {gid: dict(cmds) for gid, cmds in self.custom_commands.items()},
                'reaction_roles': self.reaction_roles,
                'prefixes': self.prefixes,
                'mod_log_channels': self.mod_log_channels,
            }
            tmp_path = 'bot_data.json.tmp'
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data_dict, f, indent=2)
            os.replace(tmp_path, 'bot_data.json')  # atomic on POSIX and Windows
        except Exception as e:
            logger.error(f"Failed to save data: {e}")

    def load_data(self):
        try:
            with open('bot_data.json', 'r', encoding='utf-8') as f:
                data_dict = json.load(f)

            self.greeting_channels = data_dict.get('greeting_channels', {})
            self.user_xp = {tuple(map(int, k.split('_'))): v for k, v in data_dict.get('user_xp', {}).items()}

            raw_banned = data_dict.get('banned_words', {})
            if isinstance(raw_banned, list):
                logger.warning(
                    "banned_words was saved in the old bot-wide format and can't be split "
                    "between servers automatically — re-add words per server with -addword.")
                raw_banned = {}
            self.banned_words = defaultdict(set, {gid: set(words) for gid, words in raw_banned.items()})

            self.welcome_messages = data_dict.get('welcome_messages', {})
            self.auto_role = data_dict.get('auto_role', {})
            self.warning_count = defaultdict(int, data_dict.get('warning_count', {}))

            raw_commands = data_dict.get('custom_commands', {})
            if raw_commands and isinstance(next(iter(raw_commands.values())), str):
                logger.warning(
                    "custom_commands was saved in the old bot-wide format and can't be split "
                    "between servers automatically — re-add them per server with -addcommand.")
                raw_commands = {}
            self.custom_commands = defaultdict(dict, {gid: dict(cmds) for gid, cmds in raw_commands.items()})

            self.reaction_roles = data_dict.get('reaction_roles', {})
            self.prefixes = data_dict.get('prefixes', {})
            self.mod_log_channels = data_dict.get('mod_log_channels', {})
            logger.info("Data loaded successfully")
        except FileNotFoundError:
            logger.info("No saved data found — starting fresh")
        except Exception as e:
            logger.error(f"Failed to load data: {e}")