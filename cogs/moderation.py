"""
Moderation: manual commands (ban/kick/timeout/...) plus the passive
auto-moderation scan (banned words + spam) that bot.py's on_message calls
into directly.
"""
import asyncio
import re
from datetime import datetime, timedelta

import discord
from discord.ext import commands

from config import logger


def _wkey(guild_id: int, user_id: int) -> str:
    return f"{guild_id}_{user_id}"


def hierarchy_issue(ctx: commands.Context, target: discord.Member) -> str | None:
    """User-facing reason ctx.author shouldn't moderate target, or None if it's fine."""
    guild = ctx.guild
    if target.id == ctx.author.id:
        return "You can't do that to yourself."
    if target.id == ctx.bot.user.id:
        return "I can't do that to myself."
    if target.id == guild.owner_id:
        return "You can't moderate the server owner."
    if ctx.author.id != guild.owner_id and target.top_role >= ctx.author.top_role:
        return "You can't moderate someone with a role equal to or higher than yours."
    if target.top_role >= guild.me.top_role:
        return "My highest role needs to be above theirs — check Server Settings → Roles."
    return None


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._word_patterns: dict[int, tuple[frozenset, re.Pattern]] = {}

    async def cog_check(self, ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage("This command only works in a server.")
        return True

    # ---------------------------------------------------------- automod --
    def invalidate_word_cache(self, guild_id: int):
        self._word_patterns.pop(guild_id, None)

    def _word_pattern(self, guild_id: int, words: set) -> re.Pattern | None:
        cached = self._word_patterns.get(guild_id)
        if cached and cached[0] == frozenset(words):
            return cached[1]
        if not words:
            self._word_patterns.pop(guild_id, None)
            return None
        pattern = re.compile(r'\b(?:' + '|'.join(re.escape(w) for w in words) + r')\b', re.IGNORECASE)
        self._word_patterns[guild_id] = (frozenset(words), pattern)
        return pattern

    async def scan_message(self, message: discord.Message) -> bool:
        """Banned-word filter + spam check. Returns True if the message was
        deleted for a banned word, so bot.py stops processing it further."""
        guild_words = self.bot.data.banned_words.get(str(message.guild.id))
        if guild_words:
            pattern = self._word_pattern(message.guild.id, guild_words)
            if pattern and pattern.search(message.content.lower()):
                try:
                    await message.delete()
                    warning_msg = await message.channel.send(
                        f'⚠️ {message.author.mention}, message removed for prohibited content.')
                    await asyncio.sleep(5)
                    await warning_msg.delete()
                    key = _wkey(message.guild.id, message.author.id)
                    self.bot.data.warning_count[key] += 1
                    if self.bot.data.warning_count[key] >= 3:
                        await message.author.timeout(timedelta(minutes=10), reason="3 auto-warnings (banned words)")
                except Exception as e:
                    logger.error(f"Failed to moderate banned word: {e}")
                return True

        await self._check_spam(message)
        return False

    async def _check_spam(self, message: discord.Message):
        now = datetime.utcnow()
        key = (message.guild.id, message.author.id)
        hist = [t for t in self.bot.data.spam_history[key] if (now - t).total_seconds() <= 10]
        hist.append(now)
        self.bot.data.spam_history[key] = hist
        if len(hist) > 8:
            try:
                await message.author.timeout(timedelta(minutes=5), reason="Spamming")
                await message.channel.send(f'🔇 {message.author.mention} timed out for spamming.')
                self.bot.data.spam_history[key] = []
            except Exception:
                pass

    # ----------------------------------------------------------- helpers --
    async def _notify(self, member: discord.Member, text: str):
        try:
            await member.send(text)
        except (discord.Forbidden, discord.HTTPException):
            pass  # DMs closed / bot blocked — not fatal

    async def log_action(self, guild: discord.Guild, embed: discord.Embed):
        channel_id = self.bot.data.mod_log_channels.get(str(guild.id))
        if not channel_id:
            return
        channel = guild.get_channel(int(channel_id))
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    # ------------------------------------------------------- member mgmt --
    @commands.command()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        issue = hierarchy_issue(ctx, member)
        if issue:
            await ctx.send(f"❌ {issue}")
            return
        await self._notify(member, f"You were banned from **{ctx.guild.name}**.\nReason: {reason}")
        try:
            await member.ban(reason=f"{ctx.author}: {reason}")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to ban that member.")
            return
        except discord.HTTPException as e:
            await ctx.send(f"❌ Discord rejected that: {e}")
            return
        embed = discord.Embed(title="🔨 Member Banned",
                               description=f"{member.mention} has been banned.\n**Reason:** {reason}",
                               color=discord.Color.red())
        embed.set_footer(text=f"By {ctx.author}")
        await ctx.send(embed=embed)
        await self.log_action(ctx.guild, embed)

    @commands.command()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: int, *, reason: str = "No reason provided"):
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user, reason=f"{ctx.author}: {reason}")
        except discord.NotFound:
            await ctx.send("❌ That user isn't banned (or the ID is wrong).")
            return
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to unban.")
            return
        embed = discord.Embed(title="🕊️ Member Unbanned",
                               description=f"**{user}** has been unbanned.\n**Reason:** {reason}",
                               color=discord.Color.green())
        await ctx.send(embed=embed)
        await self.log_action(ctx.guild, embed)

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def banlist(self, ctx, limit: int = 20):
        limit = max(1, min(limit, 50))
        bans = [entry async for entry in ctx.guild.bans(limit=limit)]
        if not bans:
            await ctx.send("📋 No bans on record.")
            return
        lines = [f"`{b.user.id}` — **{b.user}** — {b.reason or 'No reason given'}" for b in bans]
        embed = discord.Embed(title=f"🔨 Banned Users ({len(bans)})", description="\n".join(lines)[:4096],
                               color=discord.Color.red())
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        issue = hierarchy_issue(ctx, member)
        if issue:
            await ctx.send(f"❌ {issue}")
            return
        await self._notify(member, f"You were kicked from **{ctx.guild.name}**.\nReason: {reason}")
        try:
            await member.kick(reason=f"{ctx.author}: {reason}")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to kick that member.")
            return
        except discord.HTTPException as e:
            await ctx.send(f"❌ Discord rejected that: {e}")
            return
        embed = discord.Embed(title="👢 Member Kicked",
                               description=f"{member.mention} has been kicked.\n**Reason:** {reason}",
                               color=discord.Color.orange())
        embed.set_footer(text=f"By {ctx.author}")
        await ctx.send(embed=embed)
        await self.log_action(ctx.guild, embed)

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, minutes: int = 10, *, reason: str = "No reason provided"):
        if minutes < 1 or minutes > 40320:  # Discord's cap is 28 days
            await ctx.send('❌ Minutes must be between 1 and 40320 (28 days)')
            return
        issue = hierarchy_issue(ctx, member)
        if issue:
            await ctx.send(f"❌ {issue}")
            return
        try:
            await member.timeout(timedelta(minutes=minutes), reason=f"{ctx.author}: {reason}")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to time out that member.")
            return
        except discord.HTTPException as e:
            await ctx.send(f"❌ Discord rejected that: {e}")
            return
        await self._notify(member, f"You were timed out in **{ctx.guild.name}** for {minutes} minute(s).\nReason: {reason}")
        embed = discord.Embed(title="🔇 Member Timed Out",
                               description=f"{member.mention} timed out for {minutes} minute(s).\n**Reason:** {reason}",
                               color=discord.Color.orange())
        embed.set_footer(text=f"By {ctx.author}")
        await ctx.send(embed=embed)
        await self.log_action(ctx.guild, embed)

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        issue = hierarchy_issue(ctx, member)
        if issue:
            await ctx.send(f"❌ {issue}")
            return
        key = _wkey(ctx.guild.id, member.id)
        self.bot.data.warning_count[key] += 1
        count = self.bot.data.warning_count[key]
        embed = discord.Embed(title="⚠️ Member Warned",
                               description=f"{member.mention} — Warning {count}/3\n**Reason:** {reason}",
                               color=discord.Color.orange())
        await ctx.send(embed=embed)
        await self.log_action(ctx.guild, embed)
        if count >= 3:
            try:
                await member.timeout(timedelta(minutes=10), reason="Reached 3 warnings")
                await ctx.send(f"🔇 {member.mention} reached 3 warnings and was timed out for 10 minutes.")
            except discord.Forbidden:
                await ctx.send('❌ Reached 3 warnings but I lack permission to time them out.')

    @commands.command()
    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def setnickname(self, ctx, member: discord.Member, *, nickname: str = None):
        try:
            await member.edit(nick=nickname, reason=f"Changed by {ctx.author}")
        except discord.Forbidden:
            await ctx.send("❌ I can't change that member's nickname — check role hierarchy.")
            return
        await ctx.send(f"✅ {member.mention}'s nickname set to **{nickname}**" if nickname
                        else f"✅ {member.mention}'s nickname reset")

    # ------------------------------------------------------ channel mgmt --
    @commands.command()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int = 100):
        if not 1 <= amount <= 100:
            await ctx.send('❌ Amount must be between 1 and 100')
            return
        try:
            deleted = await ctx.channel.purge(limit=amount + 1)
        except discord.HTTPException as e:
            await ctx.send(f"❌ Couldn't delete those messages: `{e}`. Messages older than 14 days can't be bulk-deleted.")
            return
        msg = await ctx.send(f'✅ Deleted {len(deleted) - 1} messages')
        await asyncio.sleep(3)
        await msg.delete()

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int):
        if not 0 <= seconds <= 21600:
            await ctx.send('❌ Slowmode must be 0–21600 seconds (6 hours). Use 0 to disable.')
            return
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.send(f'🐌 Slowmode set to {seconds}s.' if seconds else '🐌 Slowmode disabled.')

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def lock(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Locked by {ctx.author}")
        await ctx.send(f"🔒 {channel.mention} locked — @everyone can no longer send messages.")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unlock(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Unlocked by {ctx.author}")
        await ctx.send(f"🔓 {channel.mention} unlocked.")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def createchannel(self, ctx, name: str, channel_type: str = "text"):
        channel_type = channel_type.lower()
        try:
            if channel_type in ("voice", "vc"):
                channel = await ctx.guild.create_voice_channel(name, reason=f"Created by {ctx.author}")
            else:
                channel = await ctx.guild.create_text_channel(name, reason=f"Created by {ctx.author}")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Couldn't create that channel: `{e}`")
            return
        await ctx.send(f"✅ Created {channel.mention}")

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def deletechannel(self, ctx, channel: discord.abc.GuildChannel = None, *, reason: str = "No reason provided"):
        channel = channel or ctx.channel
        await ctx.send(f"✅ Deleting #{channel.name}...")
        try:
            await channel.delete(reason=f"{ctx.author}: {reason}")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to delete that channel.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))