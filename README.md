# Cadence
Discord bot 


# 🤖 Phonky: All-in-One Discord Bot

> Moderation, music, AI chat, games and leveling in one bot, configurable per server.

Built with [discord.py]. 

## ✨ Features

- 🛡️ **Moderation**: ban, unban, kick, timeout, warn, bulk-delete, slowmode, lock/unlock, create/delete channels, change nicknames. Includes role-hierarchy checks, DMs the affected member, and an optional mod-log channel.
- 🚫 **Auto-moderation**: per-server banned-word filter (whole-word matching) and spam detection with automatic timeouts.
- 🎵 **Music**: play from YouTube by name or URL, with queue, previous/skip, shuffle, loop, volume and an interactive button controller. Leaves automatically when left alone in a voice channel.
- 🧠 **AI assistant**: chat, deep-thinking mode and image analysis through an OpenAI-compatible API (Groq by default, which has a free tier).
- 🎮 **Games & fun**: Tic-Tac-Toe and Rock-Paper-Scissors against other members, trivia for bonus XP, memes, jokes, 8-ball, dice and coin flips.
- ⭐ **Leveling**: members earn XP for chatting, with level cards and a server leaderboard.
- ⚙️ **Per-server settings**: custom prefix, welcome message and channel, auto-role, custom text commands, reaction roles.

## 📋 Requirements

- Python **3.10+**
- [FFmpeg](https://ffmpeg.org/download.html) on your `PATH`
- [Deno](https://docs.deno.com/runtime/getting_started/installation/) on your `PATH` (yt-dlp needs it to solve YouTube's JavaScript challenges)
- libopus (Linux only; Windows/macOS get it with `discord.py[voice]`)
- A Discord bot token
- *(Optional)* a free [Groq API key](https://console.groq.com/keys). Without it, everything works except the AI commands.

## 🚀 Quick Start

### 1. Create the bot in Discord

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**.
2. Open the **Bot** tab → **Reset Token** → copy the token (you'll need it in step 4).
3. On the same tab, under **Privileged Gateway Intents**, turn on **Message Content Intent** and **Server Members Intent**. The bot won't connect without them.

### 2. Install the project

Get the project folder (clone the repo or download it), open a terminal inside it, then:

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Install FFmpeg, Deno and Opus

```bash
# Linux (Debian/Ubuntu)
sudo apt-get install -y ffmpeg libopus0

# macOS (Homebrew)
brew install ffmpeg
```

On Windows, download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html) and add its `bin` folder to your `PATH`.

Deno:

```bash
# macOS / Linux
curl -fsSL https://deno.land/install.sh | sh
```

```powershell
# Windows (PowerShell)
irm https://deno.land/install.ps1 | iex
```

Open a **new** terminal and check that `ffmpeg -version` and `deno --version` both work.

### 4. Configure your secrets

Create a file named `.env` next to `bot.py`:

```env
DISCORD_TOKEN=your_discord_bot_token
GROQ_API_KEY=your_groq_api_key

# Optional, last resort for YouTube playback problems: path to a cookies.txt
# (Netscape format). Use a throwaway account, not your main one.
YT_COOKIES_FILE=
```

No quotes and no spaces around `=`.

### 5. Run it

```bash
python bot.py
```

In Discord, try `-help`, then `-testmusic` and `-testai` to confirm voice and AI are working.

## 🔗 Inviting the Bot

Developer Portal → **OAuth2 → URL Generator** → scope **`bot`**, with these permissions:

| Area | Permissions |
|---|---|
| General | View Channels |
| Text | Send Messages, Embed Links, Read Message History, Add Reactions, Manage Messages |
| Moderation | Kick Members, Ban Members, Moderate Members, Manage Nicknames, Manage Channels, Manage Roles |
| Voice | Connect, Speak |

> **Important:** in *Server Settings → Roles*, drag the bot's role **above** any role it should moderate. Discord blocks bots from acting on members whose top role is equal or higher.

## 🧰 Commands

The default prefix is `-`. Admins can change it per server with `-setprefix`, and you can always use `@Phonky` as a prefix too. Most commands only work inside a server.

### Moderation

| Command | Description | Needs |
|---|---|---|
| `-ban @user [reason]` | Ban a member (they're DMed the reason) | Ban Members |
| `-unban <user_id> [reason]` | Unban by user ID | Ban Members |
| `-banlist [limit]` | List banned users with IDs and reasons | Ban Members |
| `-kick @user [reason]` | Kick a member | Kick Members |
| `-timeout @user [minutes] [reason]` | Time a member out (default 10 min, max 28 days) | Moderate Members |
| `-warn @user [reason]` | Warn a member (3 or more warnings = 10-minute timeout) | Manage Messages |
| `-setnickname @user [nickname]` | Change or reset a nickname | Manage Nicknames |
| `-clear [amount]` | Delete 1-100 recent messages (Discord can't bulk-delete messages older than 14 days) | Manage Messages |
| `-slowmode <seconds>` | Set channel slowmode (`0` disables) | Manage Channels |
| `-lock [#channel]` / `-unlock [#channel]` | Stop or allow @everyone from sending messages | Manage Channels |
| `-createchannel <name> [text/voice]` | Create a channel | Manage Channels |
| `-deletechannel [#channel] [reason]` | Delete a channel (the current one if omitted) | Manage Channels |

### Server settings

All of these need **Administrator** except `-listcommands`.

| Command | Description |
|---|---|
| `-setprefix <prefix>` | Change this server's prefix (max 5 characters) |
| `-setwelcome <message>` | Welcome text. Placeholders: `{member}`, `{server}`, `{count}` |
| `-setgreeting #channel` | Channel for welcome messages (defaults to a channel named `general`) |
| `-setautorole @role` | Role given to every new member |
| `-setmodlog #channel` | Channel where moderation actions are logged |
| `-addword <word>` / `-removeword <word>` / `-listwords` | Manage this server's banned words |
| `-addcommand <trigger> <response>` / `-removecommand <trigger>` | Custom text replies, sent when a message exactly matches the trigger |
| `-listcommands` | List custom commands (anyone) |
| `-reactionrole <message_id> <emoji> @role` | Make reacting to a message grant a role (run it in the same channel as the message) |

### Music

| Command | Description |
|---|---|
| `-play <song or URL>` | Play or queue a song and show the controller |
| `-pause` / `-resume` | Pause or resume |
| `-skip` / `-previous` (`-prev`) | Next or previous track |
| `-volume [0-200]` | Show or set volume in % |
| `-queue` (`-q`) / `-shuffle` / `-loop` | Manage the queue |
| `-nowplaying` (`-np`) | Show the controller again |
| `-stop` | Stop and clear the queue (stays in the channel) |
| `-leave` | Leave the voice channel |
| `-testmusic` | Diagnose FFmpeg, Opus, DAVE, JS runtime and YouTube extraction |

The now-playing message has buttons for shuffle, previous, pause/resume, skip, queue, volume, loop and stop. Using them requires being in the bot's voice channel.

### AI

| Command | Description |
|---|---|
| `-chat <message>` / `-ask <question>` | Chat with the AI (5 s cooldown) |
| `-think <question>` | Reasoning mode (10 s cooldown) |
| `-image [prompt]` | Attach an image and ask about it (10 s cooldown) |
| `-clear-history` | Reset your conversation memory |
| `-testai` | Test the connection and show the exact error if it fails |

### Games & fun

| Command | Description |
|---|---|
| `-tictactoe @user` | Tic-Tac-Toe with buttons |
| `-rps @user` | Rock-Paper-Scissors (choices stay secret until both players pick) |
| `-trivia` | Trivia question, 30 seconds to answer, **+15 XP** if correct |
| `-8ball <question>` / `-flip` / `-roll [sides]` | Magic 8-ball, coin flip, dice (2-100 sides) |
| `-meme` / `-joke` | Random meme or joke |

### Info & levels

| Command | Description |
|---|---|
| `-help [category]` | Command menu. Categories: `ai`, `music`, `moderation`, `games`, `admin` |
| `-ping` / `-botinfo` | Latency and bot status |
| `-serverinfo` / `-userinfo [@user]` | Server and member details |
| `-level [@user]` / `-leaderboard [limit]` | XP, level and the server's top members |

## 🔍 How It Works

- **Auto-moderation:** messages containing a banned word (whole-word, case-insensitive) are deleted and count as a warning. More than 8 messages in 10 seconds earns a 5-minute timeout. Three or more warnings, from `-warn` or the filter, earn a 10-minute timeout. Words are per server.
- **Leveling:** each member gets 5 XP per message, at most once a minute. Level = XP ÷ 100 + 1.
- **Message pipeline** (in `bot.py`): auto-moderation → custom commands → XP → commands. It lives in `bot.py` on purpose, so a deleted message never also awards XP or triggers a custom command.
- **Storage:** settings, XP and warnings are saved to `bot_data.json` every 5 minutes and whenever a setting changes. Writes are atomic, so a crash can't corrupt the file.

## ⚙️ AI Configuration

Defaults live in `config.py`:

| Setting | Default | Used for |
|---|---|---|
| `AI_MODEL` | `openai/gpt-oss-20b` | `-chat`, `-ask`, `-think` |
| `VISION_MODEL` | `qwen/qwen3.6-27b` | `-image` |
| `BOT_NAME` / `BOT_CREATOR` | `Phonky` / `Bluee` | AI persona, `-help`, `-botinfo` |

Groq retires models from time to time. If `-testai` reports a model error, pick a current one from [console.groq.com/docs/models](https://console.groq.com/docs/models).

To use a different OpenAI-compatible provider, change the `base_url` and API-key variable in `cogs/ai.py` and the model names in `config.py`. The `-think` command sends Groq's `reasoning_effort` parameter, which only the gpt-oss models support.

## 🗂️ Project Structure

```
Cadence-bot/
├── bot.py               # entry point: loads cogs, message pipeline, error handling
├── config.py            # env vars, logging, intents, model names, bot name/creator
├── storage.py           # persistent settings / XP / warnings (atomic JSON saves)
├── requirements.txt
├── .env                 # your secrets (never commit this)
├── bot_data.json        # auto-created: per-server settings, XP, warnings
├── discord.log          # auto-created: log file
└── cogs/
    ├── __init__.py
    ├── moderation.py    # mod commands + auto-moderation
    ├── admin_config.py  # per-server settings, welcome/auto-role, reaction roles
    ├── ai.py            # chat / think / image
    ├── music.py         # yt-dlp + FFmpeg player, queue, button controller
    ├── fun.py           # 8ball, dice, coin, memes, jokes
    ├── games.py         # Tic-Tac-Toe, Rock-Paper-Scissors, trivia
    └── info.py          # help, server/user info, leveling
```

### Adding your own feature

Create `cogs/hello.py`:

```python
from discord.ext import commands


class Hello(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def hello(self, ctx):
        await ctx.send(f"Hi {ctx.author.mention}!")


async def setup(bot):
    await bot.add_cog(Hello(bot))
```

Then add `'cogs.hello'` to `INITIAL_EXTENSIONS` in `bot.py` and restart.

## 🛠️ Troubleshooting

| Symptom | Fix |
|---|---|
| Bot is online but ignores commands | **Message Content Intent** is off in the Developer Portal, the prefix was changed with `-setprefix`, or the bot can't read or send in that channel. |
| `PrivilegedIntentsRequired` on startup | Enable **Message Content Intent** and **Server Members Intent** in the Developer Portal → Bot. |
| `❌ AI is currently unavailable` | Run `-testai` to see the exact error. Check that `GROQ_API_KEY` is in `.env` next to `bot.py` (no quotes or spaces), restart the bot, and confirm `pip show openai` works. If the error names the model, switch to a current one. |
| Music stops after 1-2 seconds, or HTTP 403 | Install Deno, update yt-dlp (`pip install -U "yt-dlp[default]"`), restart, then run `-testmusic`. |
| Voice connection closed with code 4017 | Discord requires DAVE encryption for bot voice. Run `pip install -U "discord.py[voice]" davey`. |
| Timed out connecting to voice | Your network or host is blocking the UDP traffic voice needs (common on some free hosts and VPNs). |
| `OpusNotLoaded` or no sound | Install libopus (`sudo apt-get install -y libopus0` on Linux) and make sure FFmpeg is on your `PATH`. |
| `audioop` import error (Python 3.13+) | `pip install audioop-lts` |
| "My highest role needs to be above theirs" | In Server Settings → Roles, drag the bot's role above the roles it should moderate. |
| Banned words / custom commands disappeared after upgrading | They're now per server. Re-add them with `-addword` / `-addcommand`. |

## 🔐 Security & Privacy

- Never commit `.env`. Add a `.gitignore`:

  ```
  .env
  bot_data.json
  bot_data.json.tmp
  discord.log
  .venv/
  __pycache__/
  ```

- If your bot token or an API key is ever exposed (pasted in a chat, shown in a screenshot, pushed to a public repo), regenerate it immediately: **Reset Token** in the Developer Portal, or the key page in your provider's dashboard.
- Only use API keys you created yourself in the provider's dashboard. Keys from "free key" lists or generator tools are usually farmed accounts that get revoked without warning.
- AI conversation memory is kept in RAM only (cleared on restart or with `-clear-history`), but anything sent to the AI commands is forwarded to the AI provider.

## 🙏 Credits

Created by **AKSHAT**. Built with discord.py, yt-dlp, FFmpeg and Groq's OpenAI-compatible API. Memes from meme-api.com, jokes from official-joke-api, trivia from the Open Trivia Database.