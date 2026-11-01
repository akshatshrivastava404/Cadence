"""
Music system: search/queue/playback via yt-dlp + ffmpeg, with an
interactive button controller. This preserves the hard-won handling
around YouTube's signed-URL 403s and Discord's mandatory DAVE voice
encryption from the original bot — don't strip the diagnostics below,
they're doing real work.
"""
import asyncio
import os
import random
import shutil
import time

import aiohttp
import discord
from discord.ext import commands

from config import logger, YT_COOKIES_FILE

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False
    logger.warning("yt-dlp not installed. Music commands will be disabled.")

FFMPEG_PATH = shutil.which('ffmpeg')
if not FFMPEG_PATH:
    logger.warning(
        "ffmpeg was not found on PATH. Music playback will fail. Install it from "
        "https://ffmpeg.org/download.html and make sure the 'ffmpeg' command works in a normal terminal.")

DENO_PATH = shutil.which('deno')
NODE_PATH = shutil.which('node')
if not (DENO_PATH or NODE_PATH):
    logger.warning(
        "No JS runtime (deno/node) found on PATH. YouTube playback will very likely fail with HTTP 403 "
        "on the media URL even though yt-dlp reports success. Install Deno "
        "(https://docs.deno.com/runtime/getting_started/installation/), make sure the 'deno' command "
        "works in a normal terminal, restart the bot, and check with -testmusic.")

try:
    import nacl  # noqa: F401
    NACL_AVAILABLE = True
except ImportError:
    NACL_AVAILABLE = False
    logger.warning("PyNaCl not installed. Voice connections will fail immediately. Run: pip install PyNaCl")

try:
    import davey  # noqa: F401
    DAVEY_AVAILABLE = True
except ImportError:
    DAVEY_AVAILABLE = False
    logger.warning(
        "'davey' not installed. Discord has required DAVE E2EE support for bot voice connections since "
        "March 2026, and connections will be rejected (close code 4017) without it. Run: "
        "pip install -U \"discord.py[voice]\" davey")

OPUS_AVAILABLE = discord.opus.is_loaded()
if not OPUS_AVAILABLE:
    for _opus_name in ('opus', 'libopus.so.0', 'libopus-0.dll'):
        try:
            discord.opus.load_opus(_opus_name)
            OPUS_AVAILABLE = discord.opus.is_loaded()
            if OPUS_AVAILABLE:
                break
        except OSError:
            continue
if not OPUS_AVAILABLE:
    logger.warning(
        "Opus codec library is not loaded. The bot can still join voice channels, but playback will "
        "fail silently or raise OpusNotLoaded. On Linux: sudo apt-get install -y libopus0. On "
        "Windows/macOS, reinstall voice support: pip install -U \"discord.py[voice]\"")


FFMPEG_BEFORE_OPTS = (
    '-reconnect 1 '
    '-reconnect_streamed 1 '
    '-reconnect_at_eof 1 '
    '-reconnect_on_network_error 1 '
    '-reconnect_delay_max 5 '
    '-nostdin'
)
FFMPEG_OPTS = '-vn'


class YTDLPLogger:
    """Routes yt-dlp's own warnings/errors into our normal logger. yt-dlp
    doesn't hard-fail when it can't fully solve YouTube's signature
    challenge — it logs a WARNING and quietly returns a URL that then
    403s the moment ffmpeg fetches it, so that warning needs to reach
    discord.log or the failure has zero explanation anywhere."""
    def debug(self, msg):
        if not msg.startswith('[debug] '):
            logger.debug(f"[yt-dlp] {msg}")

    def warning(self, msg):
        logger.warning(f"[yt-dlp] {msg}")

    def error(self, msg):
        logger.error(f"[yt-dlp] {msg}")


YDL_OPTS = {
    'format': 'bestaudio[protocol^=m3u8]/bestaudio/best',
    'quiet': True,
    'no_warnings': False,
    'logger': YTDLPLogger(),
    'noplaylist': True,
    'default_search': 'ytsearch1',
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'source_address': '0.0.0.0',
    'extractor_args': {
        'youtube': {
            # Several clients, not one: YouTube blocks specific clients outright and
            # unpredictably, so trying multiple is more resilient than betting on one.
            'player_client': ['android', 'web', 'ios', 'mweb'],
        },
    },
}
if YT_COOKIES_FILE and os.path.isfile(YT_COOKIES_FILE):
    YDL_OPTS['cookiefile'] = YT_COOKIES_FILE
    logger.info(f"Using YouTube cookies file: {YT_COOKIES_FILE}")


class Track:
    def __init__(self, title, url, stream_url, duration, thumbnail, requester, webpage_url, http_headers=None):
        self.title = title
        self.url = url
        self.stream_url = stream_url
        self.http_headers = http_headers or {}
        self.duration = duration
        self.thumbnail = thumbnail
        self.requester = requester
        self.webpage_url = webpage_url

    def duration_str(self):
        if not self.duration:
            return "Live/Unknown"
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


class GuildMusicState:
    def __init__(self, guild_id):
        self.guild_id = guild_id
        self.queue: list[Track] = []
        self.history: list[Track] = []
        self.current: Track | None = None
        self.volume: float = 0.5
        self.voice_client: discord.VoiceClient | None = None
        self.text_channel: discord.TextChannel | None = None
        self.loop_current: bool = False
        self.now_playing_message: discord.Message | None = None
        self.skip_flag = False
        self.empty_since_task: asyncio.Task | None = None  # auto-leave timer


music_states: dict[int, GuildMusicState] = {}


def get_state(guild_id: int) -> GuildMusicState:
    if guild_id not in music_states:
        music_states[guild_id] = GuildMusicState(guild_id)
    return music_states[guild_id]


async def extract_track(query: str, requester: discord.Member) -> Track | None:
    def _extract():
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(query, download=False)
            if info is None:
                return None
            if 'entries' in info:
                entries = [e for e in info['entries'] if e]
                if not entries:
                    return None
                info = entries[0]
            return info

    try:
        info = await asyncio.to_thread(_extract)
    except Exception:
        logger.exception(f"yt-dlp extraction failed for '{query}'")
        return None

    if not info:
        return None

    stream_url = info.get('url')
    if not stream_url:
        logger.error(f"yt-dlp returned no playable stream URL for '{query}'")
        return None

    return Track(
        title=info.get('title', 'Unknown title'),
        url=query,
        stream_url=stream_url,
        duration=info.get('duration'),
        thumbnail=info.get('thumbnail'),
        requester=requester,
        webpage_url=info.get('webpage_url', query),
        http_headers=info.get('http_headers') or {},
    )


async def refresh_track_stream(track: Track) -> bool:
    query = track.webpage_url or track.url

    def _extract_fresh():
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(query, download=False)
            if info is None:
                return None
            if 'entries' in info:
                entries = [e for e in info['entries'] if e]
                if not entries:
                    return None
                info = entries[0]
            return info

    try:
        info = await asyncio.to_thread(_extract_fresh)
        if not info:
            logger.error(f"Could not refresh stream URL for '{track.title}'")
            return False
        stream_url = info.get('url')
        if not stream_url:
            logger.error(f"yt-dlp returned no fresh stream URL for '{track.title}'")
            return False
        track.stream_url = stream_url
        track.http_headers = info.get('http_headers') or {}
        return True
    except Exception as e:
        logger.exception(f"Failed to refresh stream URL for '{track.title}': {e}")
        return False


def build_now_playing_embed(state: GuildMusicState) -> discord.Embed:
    track = state.current
    embed = discord.Embed(
        title="🎵 Now Playing",
        description=f"**[{track.title}]({track.webpage_url})**",
        color=discord.Color.blurple()
    )
    if track.thumbnail:
        embed.set_thumbnail(url=track.thumbnail)
    embed.add_field(name="Requested by", value=track.requester.mention, inline=True)
    embed.add_field(name="Duration", value=track.duration_str(), inline=True)
    embed.add_field(name="Volume", value=f"{int(state.volume * 100)}%", inline=True)
    embed.add_field(name="Up next", value=f"{len(state.queue)} song(s) in queue", inline=True)
    embed.add_field(name="Loop", value="On" if state.loop_current else "Off", inline=True)
    embed.set_footer(text="Use the buttons below to control playback")
    return embed


def play_track_in_voice(bot: commands.Bot, state: GuildMusicState, track: Track) -> bool:
    """Starts ffmpeg playback of `track`. Returns True if playback started."""
    if not state.voice_client or not state.voice_client.is_connected():
        logger.error("play_track_in_voice called with no connected voice client")
        if state.text_channel:
            asyncio.create_task(state.text_channel.send(
                "❌ Lost the voice connection before playback could start."))
        return False

    try:
        if not FFMPEG_PATH:
            raise RuntimeError(
                'FFmpeg was not found on PATH. Install FFmpeg and make sure '
                'the ffmpeg executable is available to the bot process.')
        if not track.stream_url:
            raise RuntimeError('The track has no playable stream URL.')

        before_options = FFMPEG_BEFORE_OPTS
        if track.http_headers:
            header_lines = []
            for key, value in track.http_headers.items():
                if key.lower() in {'content-length', 'range'}:
                    continue
                header_lines.append(f"{key}: {value}")
            if header_lines:
                header_block = '\r\n'.join(header_lines) + '\r\n'
                header_block = header_block.replace('"', '\\"')
                before_options += f' -headers "{header_block}"'

        source = discord.FFmpegPCMAudio(
            track.stream_url, executable=FFMPEG_PATH, before_options=before_options, options=FFMPEG_OPTS)
        source = discord.PCMVolumeTransformer(source, volume=state.volume)
    except Exception as e:
        logger.exception(f"Failed to create audio source for '{track.title}'")
        if state.text_channel:
            asyncio.create_task(state.text_channel.send(
                f"❌ Couldn't play **{track.title}**: `{e}`\nIs FFmpeg installed and on PATH?"))
        return False

    start_time = time.monotonic()

    def _after_playback(error):
        elapsed = time.monotonic() - start_time
        was_deliberate = state.skip_flag
        if error:
            logger.error(f"Playback error for '{track.title}': {error}")
            if state.text_channel:
                asyncio.run_coroutine_threadsafe(
                    state.text_channel.send(f"❌ Playback error for **{track.title}**: `{error}`"), bot.loop)
        elif elapsed < 2.5 and not was_deliberate and state.text_channel:
            logger.warning(f"'{track.title}' stopped after only {elapsed:.1f}s — likely a dead/blocked stream URL")
            asyncio.run_coroutine_threadsafe(
                state.text_channel.send(
                    f"⚠️ **{track.title}** stopped after only {elapsed:.1f}s with no audio. "
                    "That's almost always YouTube returning HTTP 403 on the media URL. Run "
                    "`-testmusic` for a precise diagnosis."),
                bot.loop)
        fut = asyncio.run_coroutine_threadsafe(advance_queue(bot, state), bot.loop)
        try:
            fut.result()
        except Exception as e:
            logger.error(f"advance_queue error: {e}")

    try:
        state.voice_client.play(source, after=_after_playback)
    except discord.ClientException as e:
        logger.error(f"voice_client.play failed: {e}")
        if state.text_channel:
            asyncio.create_task(state.text_channel.send(f"❌ Couldn't start playback: `{e}`"))
        return False
    except Exception as e:
        logger.exception(f"Unexpected error starting playback of '{track.title}'")
        if state.text_channel:
            hint = ""
            if isinstance(e, discord.opus.OpusNotLoaded):
                hint = ("\nThe Opus codec library isn't loaded — on Linux run "
                        "`sudo apt-get install -y libopus0` and restart the bot.")
            asyncio.create_task(state.text_channel.send(f"❌ Couldn't start playback: `{e}`{hint}"))
        return False

    return True


async def advance_queue(bot: commands.Bot, state: GuildMusicState):
    if state.current and not state.loop_current:
        state.history.append(state.current)
        if len(state.history) > 25:
            state.history.pop(0)

    if state.loop_current and state.current and not state.skip_flag:
        next_track = state.current
    elif state.queue:
        next_track = state.queue.pop(0)
    else:
        state.current = None
        if state.text_channel:
            try:
                await state.text_channel.send("📭 Queue finished — nothing left to play.")
            except Exception:
                pass
        return

    state.skip_flag = False
    state.current = next_track

    if not state.voice_client or not state.voice_client.is_connected():
        return

    if not await refresh_track_stream(next_track):
        if state.text_channel:
            try:
                await state.text_channel.send(f"❌ Couldn't refresh **{next_track.title}** for playback. Skipping it.")
            except Exception:
                pass
        return

    started = play_track_in_voice(bot, state, next_track)
    if not started:
        return

    if state.text_channel:
        try:
            view = MusicControlView(state.guild_id)
            msg = await state.text_channel.send(embed=build_now_playing_embed(state), view=view)
            state.now_playing_message = msg
        except Exception as e:
            logger.error(f"Failed to send now-playing message: {e}")


async def ensure_voice(ctx) -> GuildMusicState | None:
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send('❌ You must be in a voice channel first!')
        return None

    state = get_state(ctx.guild.id)
    state.text_channel = ctx.channel

    if not ctx.voice_client:
        try:
            state.voice_client = await ctx.author.voice.channel.connect(timeout=20, self_deaf=True)
        except discord.errors.ConnectionClosed as e:
            if getattr(e, 'code', None) == 4017:
                logger.error("Voice connect rejected with 4017 - DAVE E2EE support missing (need 'davey' package)")
                await ctx.send(
                    "❌ Discord rejected the voice connection because it requires E2EE (DAVE protocol) "
                    "support, which this bot doesn't have yet. Run "
                    "`pip install -U \"discord.py[voice]\" davey`, restart the bot, and try again.")
            else:
                logger.error(f"Voice connect ConnectionClosed: code={getattr(e, 'code', None)}")
                await ctx.send(f"❌ Voice connection was closed unexpectedly (code {getattr(e, 'code', 'unknown')}).")
            return None
        except asyncio.TimeoutError:
            logger.error("Voice connect timed out - likely UDP/firewall issue at the hosting environment")
            await ctx.send(
                "❌ Timed out connecting to voice. This almost always means the network the bot "
                "runs on is blocking the UDP traffic Discord voice needs — common on some free "
                "hosts (e.g. Replit) or restrictive firewalls/VPNs. Try running the bot from a "
                "different network/host, or check your firewall settings.")
            return None
        except discord.ClientException as e:
            logger.error(f"Voice connect ClientException: {e}")
            msg = f"❌ Could not connect to voice: `{e}`"
            if "PyNaCl" in str(e):
                msg += "\nRun `pip install PyNaCl` and restart the bot."
            await ctx.send(msg)
            return None
        except Exception as e:
            logger.exception("Unexpected error connecting to voice")
            await ctx.send(f"❌ Unexpected error connecting to voice: `{e}`")
            return None
    else:
        state.voice_client = ctx.voice_client

    return state


class MusicControlView(discord.ui.View):
    """Interactive now-playing controller: shuffle, previous, pause/resume, skip, queue, volume."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    def _state(self) -> GuildMusicState:
        return get_state(self.guild_id)

    async def _check_voice(self, interaction: discord.Interaction) -> bool:
        state = self._state()
        if not state.voice_client or not state.voice_client.is_connected():
            await interaction.response.send_message("❌ Not connected to a voice channel.", ephemeral=True)
            return False
        member = interaction.user
        if not member.voice or member.voice.channel != state.voice_client.channel:
            await interaction.response.send_message("❌ Join the same voice channel to control playback.", ephemeral=True)
            return False
        return True

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary, row=0)
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_voice(interaction):
            return
        state = self._state()
        if len(state.queue) < 2:
            await interaction.response.send_message("❌ Not enough songs in queue to shuffle.", ephemeral=True)
            return
        random.shuffle(state.queue)
        await interaction.response.send_message("🔀 Queue shuffled.", ephemeral=True)

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary, row=0)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_voice(interaction):
            return
        state = self._state()
        if not state.history:
            await interaction.response.send_message("❌ No previous track.", ephemeral=True)
            return
        prev_track = state.history.pop()
        if state.current:
            state.queue.insert(0, state.current)
        state.queue.insert(0, prev_track)
        state.skip_flag = True
        state.voice_client.stop()
        await interaction.response.send_message("⏮️ Playing previous track.", ephemeral=True)

    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.primary, row=0)
    async def pause_resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_voice(interaction):
            return
        state = self._state()
        if state.voice_client.is_playing():
            state.voice_client.pause()
            button.emoji = "▶️"
            await interaction.response.edit_message(view=self)
        elif state.voice_client.is_paused():
            state.voice_client.resume()
            button.emoji = "⏸️"
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.send_message("❌ Nothing is playing.", ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, row=0)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_voice(interaction):
            return
        state = self._state()
        if not state.voice_client.is_playing() and not state.voice_client.is_paused():
            await interaction.response.send_message("❌ Nothing is playing.", ephemeral=True)
            return
        state.skip_flag = True
        state.voice_client.stop()
        await interaction.response.send_message("⏭️ Skipped.", ephemeral=True)

    @discord.ui.button(emoji="📃", style=discord.ButtonStyle.secondary, row=0)
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self._state()
        if not state.queue:
            await interaction.response.send_message("📭 Queue is empty.", ephemeral=True)
            return
        lines = [f"{i+1}. {t.title} — {t.duration_str()} (req. {t.requester.display_name})"
                 for i, t in enumerate(state.queue[:15])]
        extra = f"\n...and {len(state.queue) - 15} more" if len(state.queue) > 15 else ""
        await interaction.response.send_message(
            f"**Up next ({len(state.queue)}):**\n" + "\n".join(lines) + extra, ephemeral=True)

    @discord.ui.button(label="Vol -", emoji="🔉", style=discord.ButtonStyle.secondary, row=1)
    async def volume_down_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_voice(interaction):
            return
        state = self._state()
        state.volume = max(0.0, round(state.volume - 0.1, 2))
        if isinstance(state.voice_client.source, discord.PCMVolumeTransformer):
            state.voice_client.source.volume = state.volume
        await interaction.response.send_message(f"🔉 Volume: {int(state.volume * 100)}%", ephemeral=True)

    @discord.ui.button(label="Vol +", emoji="🔊", style=discord.ButtonStyle.secondary, row=1)
    async def volume_up_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_voice(interaction):
            return
        state = self._state()
        state.volume = min(2.0, round(state.volume + 0.1, 2))
        if isinstance(state.voice_client.source, discord.PCMVolumeTransformer):
            state.voice_client.source.volume = state.volume
        await interaction.response.send_message(f"🔊 Volume: {int(state.volume * 100)}%", ephemeral=True)

    @discord.ui.button(label="Loop", emoji="🔁", style=discord.ButtonStyle.secondary, row=1)
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_voice(interaction):
            return
        state = self._state()
        state.loop_current = not state.loop_current
        await interaction.response.send_message(f"🔁 Loop {'enabled' if state.loop_current else 'disabled'}.", ephemeral=True)

    @discord.ui.button(label="Stop", emoji="⏹️", style=discord.ButtonStyle.danger, row=1)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_voice(interaction):
            return
        state = self._state()
        state.queue.clear()
        state.history.clear()
        state.current = None
        if state.voice_client:
            state.voice_client.stop()
            await state.voice_client.disconnect()
            state.voice_client = None
        await interaction.response.send_message("⏹️ Stopped and left the voice channel.", ephemeral=True)


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def available(self) -> bool:
        return YT_DLP_AVAILABLE

    async def cog_check(self, ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage("This command only works in a server.")
        return True

    # ------------------------------------------------- auto-leave-when-alone --
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        state = music_states.get(member.guild.id)
        if not state or not state.voice_client or not state.voice_client.channel:
            return
        channel = state.voice_client.channel
        if before.channel != channel and after.channel != channel:
            return

        humans = [m for m in channel.members if not m.bot]
        if humans:
            if state.empty_since_task and not state.empty_since_task.done():
                state.empty_since_task.cancel()
                state.empty_since_task = None
            return

        if state.empty_since_task and not state.empty_since_task.done():
            return
        state.empty_since_task = asyncio.create_task(self._leave_if_still_empty(member.guild.id))

    async def _leave_if_still_empty(self, guild_id: int, delay: int = 120):
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        state = music_states.get(guild_id)
        if not state or not state.voice_client or not state.voice_client.channel:
            return
        if any(not m.bot for m in state.voice_client.channel.members):
            return
        channel_name = state.voice_client.channel.name
        state.queue.clear()
        state.history.clear()
        state.current = None
        await state.voice_client.disconnect()
        state.voice_client = None
        if state.text_channel:
            try:
                await state.text_channel.send(f"👋 Left **{channel_name}** — everyone left the channel.")
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------- commands --
    @commands.command()
    async def play(self, ctx, *, query: str):
        """Play or queue a song by name or URL"""
        if not YT_DLP_AVAILABLE:
            await ctx.send('❌ Music feature not available (yt-dlp not installed)')
            return

        state = await ensure_voice(ctx)
        if not state:
            return

        async with ctx.typing():
            track = await extract_track(query, ctx.author)
            if not track:
                await ctx.send(
                    '❌ Could not find or load that song. Run `-testmusic` to see exactly why — '
                    'this is almost always yt-dlp/YouTube, not the bot itself.')
                return

            if state.voice_client.is_playing() or state.voice_client.is_paused():
                state.queue.append(track)
                embed = discord.Embed(title="➕ Added to Queue",
                                       description=f"**[{track.title}]({track.webpage_url})**",
                                       color=discord.Color.green())
                embed.add_field(name="Position in queue", value=str(len(state.queue)))
                embed.add_field(name="Duration", value=track.duration_str())
                if track.thumbnail:
                    embed.set_thumbnail(url=track.thumbnail)
                await ctx.send(embed=embed)
            else:
                state.current = track
                started = play_track_in_voice(self.bot, state, track)
                if not started:
                    state.current = None
                    return
                view = MusicControlView(ctx.guild.id)
                msg = await ctx.send(embed=build_now_playing_embed(state), view=view)
                state.now_playing_message = msg

    @commands.command(name='testmusic')
    async def testmusic(self, ctx):
        """Diagnose the music pipeline: FFmpeg, Opus, JS runtime, and yt-dlp/YouTube extraction"""
        embed = discord.Embed(title="🔍 Music Diagnostics", color=discord.Color.blue())
        embed.add_field(name="yt-dlp", value="✅ Installed" if YT_DLP_AVAILABLE else "❌ Not installed", inline=True)
        embed.add_field(name="FFmpeg", value="✅ Found" if FFMPEG_PATH else "❌ Not on PATH", inline=True)
        embed.add_field(name="PyNaCl", value="✅ Installed" if NACL_AVAILABLE else "❌ Not installed", inline=True)
        embed.add_field(name="Opus codec", value="✅ Loaded" if discord.opus.is_loaded() else "❌ Not loaded", inline=True)
        embed.add_field(name="DAVE (davey)", value="✅ Installed" if DAVEY_AVAILABLE else "❌ Not installed", inline=True)
        embed.add_field(
            name="JS runtime",
            value=("✅ " + ("deno" if DENO_PATH else "node")) if (DENO_PATH or NODE_PATH) else "❌ None found",
            inline=True)

        if not YT_DLP_AVAILABLE:
            embed.color = discord.Color.red()
            await ctx.send(embed=embed)
            return

        async with ctx.typing():
            try:
                test_track = await extract_track("ytsearch1:test", ctx.author)
            except Exception as e:
                test_track = None
                embed.add_field(name="yt-dlp extraction", value=f"❌ `{str(e)[:400]}`", inline=False)
                embed.color = discord.Color.red()
            else:
                if not test_track or not test_track.stream_url:
                    embed.add_field(
                        name="yt-dlp extraction",
                        value="❌ No playable stream returned. Check the console/log right now for a "
                              "yt-dlp warning — often 'No supported JavaScript runtime could be found'.",
                        inline=False)
                    embed.color = discord.Color.red()
                else:
                    embed.add_field(name="yt-dlp extraction", value=f"✅ Resolved: {test_track.title[:150]}", inline=False)
                    try:
                        timeout_cfg = aiohttp.ClientTimeout(total=10)
                        async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
                            async with session.get(test_track.stream_url, headers=test_track.http_headers or {}) as resp:
                                if resp.status < 400:
                                    embed.add_field(name="Stream URL fetch test",
                                                     value=f"✅ HTTP {resp.status} — the resolved URL is actually playable",
                                                     inline=False)
                                    embed.color = discord.Color.green()
                                else:
                                    embed.add_field(
                                        name="Stream URL fetch test",
                                        value=f"❌ HTTP {resp.status} from googlevideo — **this is the bug**. "
                                              "yt-dlp resolved *a* URL but YouTube is rejecting it (bad/expired "
                                              "signature). Update yt-dlp (`pip install -U \"yt-dlp[default]\"`), "
                                              "make sure a JS runtime is installed, and keep player_client "
                                              "pointed at more than one client.",
                                        inline=False)
                                    embed.color = discord.Color.orange()
                    except Exception as e:
                        embed.add_field(name="Stream URL fetch test", value=f"❌ `{str(e)[:300]}`", inline=False)
                        embed.color = discord.Color.orange()

        embed.set_footer(text="Run this again after making changes to confirm the fix worked")
        await ctx.send(embed=embed)

    @commands.command()
    async def skip(self, ctx):
        state = get_state(ctx.guild.id)
        if not state.voice_client or not (state.voice_client.is_playing() or state.voice_client.is_paused()):
            await ctx.send('❌ Nothing is playing.')
            return
        state.skip_flag = True
        state.voice_client.stop()
        await ctx.send('⏭️ Skipped.')

    @commands.command(name='previous', aliases=['prev'])
    async def previous(self, ctx):
        state = get_state(ctx.guild.id)
        if not state.voice_client:
            await ctx.send('❌ Not connected to a voice channel.')
            return
        if not state.history:
            await ctx.send('❌ No previous track.')
            return
        prev_track = state.history.pop()
        if state.current:
            state.queue.insert(0, state.current)
        state.queue.insert(0, prev_track)
        state.skip_flag = True
        state.voice_client.stop()
        await ctx.send('⏮️ Playing previous track.')

    @commands.command()
    async def pause(self, ctx):
        state = get_state(ctx.guild.id)
        if state.voice_client and state.voice_client.is_playing():
            state.voice_client.pause()
            await ctx.send('⏸️ Paused.')
        else:
            await ctx.send('❌ Nothing is playing.')

    @commands.command()
    async def resume(self, ctx):
        state = get_state(ctx.guild.id)
        if state.voice_client and state.voice_client.is_paused():
            state.voice_client.resume()
            await ctx.send('▶️ Resumed.')
        else:
            await ctx.send('❌ Nothing is paused.')

    @commands.command()
    async def volume(self, ctx, level: int = None):
        state = get_state(ctx.guild.id)
        if level is None:
            await ctx.send(f'🔊 Current volume: {int(state.volume * 100)}%')
            return
        if level < 0 or level > 200:
            await ctx.send('❌ Volume must be between 0 and 200')
            return
        state.volume = level / 100
        if state.voice_client and isinstance(state.voice_client.source, discord.PCMVolumeTransformer):
            state.voice_client.source.volume = state.volume
        await ctx.send(f'🔊 Volume set to {level}%')

    @commands.command(name='queue', aliases=['q'])
    async def queue_cmd(self, ctx):
        state = get_state(ctx.guild.id)
        embed = discord.Embed(title="📃 Music Queue", color=discord.Color.blue())
        if state.current:
            embed.add_field(name="Now Playing", value=f"{state.current.title} ({state.current.duration_str()})", inline=False)
        if not state.queue:
            embed.add_field(name="Up Next", value="Queue is empty.", inline=False)
        else:
            lines = [f"{i+1}. {t.title} — {t.duration_str()}" for i, t in enumerate(state.queue[:15])]
            if len(state.queue) > 15:
                lines.append(f"...and {len(state.queue) - 15} more")
            embed.add_field(name="Up Next", value="\n".join(lines), inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    async def shuffle(self, ctx):
        state = get_state(ctx.guild.id)
        if len(state.queue) < 2:
            await ctx.send('❌ Not enough songs in queue to shuffle.')
            return
        random.shuffle(state.queue)
        await ctx.send('🔀 Queue shuffled.')

    @commands.command()
    async def loop(self, ctx):
        state = get_state(ctx.guild.id)
        state.loop_current = not state.loop_current
        await ctx.send(f"🔁 Loop {'enabled' if state.loop_current else 'disabled'}.")

    @commands.command(name='nowplaying', aliases=['np'])
    async def nowplaying(self, ctx):
        state = get_state(ctx.guild.id)
        if not state.current:
            await ctx.send('❌ Nothing is playing.')
            return
        view = MusicControlView(ctx.guild.id)
        await ctx.send(embed=build_now_playing_embed(state), view=view)

    @commands.command()
    async def stop(self, ctx):
        state = get_state(ctx.guild.id)
        state.queue.clear()
        state.history.clear()
        state.current = None
        if state.voice_client:
            state.voice_client.stop()
        await ctx.send('⏹️ Stopped and cleared the queue.')

    @commands.command()
    async def leave(self, ctx):
        state = get_state(ctx.guild.id)
        if state.voice_client:
            state.queue.clear()
            state.history.clear()
            state.current = None
            await state.voice_client.disconnect()
            state.voice_client = None
            await ctx.send('👋 Left voice channel')
        else:
            await ctx.send('❌ Not in a voice channel')


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))