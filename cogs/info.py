"""Info/utility commands: ping, server & user info, leveling, and help.
Also owns passive XP awarding, called from bot.py's on_message."""
from datetime import datetime

import discord
from discord.ext import commands

from config import BOT_CREATOR, AI_MODEL


class Info(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------- XP --
    def add_xp(self, guild_id: int, user_id: int, amount: int):
        key = (guild_id, user_id)
        self.bot.data.user_xp[key] = self.bot.data.user_xp.get(key, 0) + amount

    async def maybe_award_xp(self, message: discord.Message):
        now = datetime.utcnow()
        key = (message.guild.id, message.author.id)
        prev = self.bot.data.last_award.get(key)
        if prev and (now - prev).total_seconds() < 60:
            return
        self.bot.data.last_award[key] = now
        old_level = self.bot.data.user_xp.get(key, 0) // 100 + 1
        self.add_xp(key[0], key[1], 5)
        new_level = self.bot.data.user_xp[key] // 100 + 1
        if new_level > old_level:
            await message.channel.send(f'🎉 {message.author.mention} leveled up to **Level {new_level}**!',
                                        delete_after=10)

    # -------------------------------------------------------- commands --
    @commands.command()
    async def ping(self, ctx):
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(title="🏓 Pong!", description=f"**Latency:** {latency}ms",
                               color=discord.Color.green() if latency < 100 else discord.Color.orange())
        await ctx.send(embed=embed)

    @commands.command()
    @commands.guild_only()
    async def serverinfo(self, ctx):
        guild = ctx.guild
        embed = discord.Embed(title=f"📊 {guild.name}", color=discord.Color.blue())
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="👑 Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="👥 Members", value=guild.member_count, inline=True)
        embed.add_field(name="📅 Created", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="💬 Channels", value=len(guild.channels), inline=True)
        embed.add_field(name="🎭 Roles", value=len(guild.roles), inline=True)
        embed.add_field(name="😀 Emojis", value=len(guild.emojis), inline=True)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.guild_only()
    async def userinfo(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(title=f"👤 {member.name}", color=member.color)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="🆔 ID", value=member.id, inline=True)
        embed.add_field(name="📅 Joined Server",
                         value=member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "Unknown", inline=True)
        embed.add_field(name="📅 Account Created", value=member.created_at.strftime("%Y-%m-%d"), inline=True)

        key = (ctx.guild.id, member.id)
        xp = self.bot.data.user_xp.get(key, 0)
        embed.add_field(name="⭐ Level", value=xp // 100 + 1, inline=True)
        embed.add_field(name="✨ XP", value=xp, inline=True)

        roles = [role.mention for role in member.roles if role.name != "@everyone"]
        if roles:
            embed.add_field(name="🎭 Roles", value=" ".join(roles[:10]), inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    async def botinfo(self, ctx):
        ai_cog = self.bot.get_cog('AI')
        music_cog = self.bot.get_cog('Music')
        embed = discord.Embed(title="🤖 Bot Information",
                               description="A powerful Discord bot with AI and music capabilities",
                               color=discord.Color.blue())
        embed.add_field(name="👨‍💻 Creator", value=BOT_CREATOR, inline=True)
        embed.add_field(name="📊 Servers", value=len(self.bot.guilds), inline=True)
        embed.add_field(name="👥 Users", value=len(self.bot.users), inline=True)
        embed.add_field(name="🧠 AI Status", value="✅ Enabled" if ai_cog and ai_cog.available else "❌ Disabled", inline=True)
        embed.add_field(name="🎵 Music Status", value="✅ Enabled" if music_cog and music_cog.available else "❌ Disabled", inline=True)
        embed.add_field(name="🏓 Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        if ai_cog and ai_cog.available:
            embed.add_field(name="🤖 AI Model", value=AI_MODEL, inline=False)
        embed.set_footer(text="Bot Version 4.0 (cogs) | Use -help for commands")
        await ctx.send(embed=embed)

    @commands.command()
    @commands.guild_only()
    async def level(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        key = (ctx.guild.id, member.id)
        xp = self.bot.data.user_xp.get(key, 0)
        lvl = xp // 100 + 1
        embed = discord.Embed(title="⭐ Level Information", color=member.color)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User", value=member.mention, inline=True)
        embed.add_field(name="Level", value=f"**{lvl}**", inline=True)
        embed.add_field(name="XP", value=f"{xp}/{lvl * 100}", inline=True)
        embed.add_field(name="Next Level", value=f"{(lvl * 100) - xp} XP needed", inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.guild_only()
    async def leaderboard(self, ctx, limit: int = 10):
        limit = max(1, min(limit, 25))
        guild_users = {k: v for k, v in self.bot.data.user_xp.items() if k[0] == ctx.guild.id}
        sorted_users = sorted(guild_users.items(), key=lambda x: x[1], reverse=True)[:limit]
        if not sorted_users:
            await ctx.send("📊 No users with XP yet!")
            return
        embed = discord.Embed(title=f"🏆 Top {limit} - {ctx.guild.name}", color=discord.Color.gold())
        description = ""
        for i, ((guild_id, user_id), xp) in enumerate(sorted_users, 1):
            member = ctx.guild.get_member(user_id)
            if member:
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**{i}.**"
                description += f"{medal} {member.mention} - Level {xp // 100 + 1} ({xp} XP)\n"
        embed.description = description or "No members with XP are currently in this server."
        await ctx.send(embed=embed)

    @commands.command(name='help')
    async def help_custom(self, ctx, category: str = None):
        categories = {
            'ai': ("🤖 AI Commands", discord.Color.blue(), [
                ("-chat <message>", "Chat with the AI assistant"),
                ("-ask <question>", "Ask AI a question"),
                ("-think <question>", "AI thinks deeply about a question"),
                ("-image <prompt>", "Analyze an attached image"),
                ("-clear-history", "Clear your chat history"),
                ("-testai", "Test the AI connection"),
            ]),
            'music': ("🎵 Music Commands", discord.Color.blue(), [
                ("-play <song/url>", "Play or queue a song, shows the controller"),
                ("-skip / -previous", "Skip or go back a track"),
                ("-pause / -resume", "Pause or resume playback"),
                ("-volume <0-200>", "Set playback volume %"),
                ("-queue / -shuffle / -loop", "Manage the queue"),
                ("-nowplaying", "Show the controller again"),
                ("-stop / -leave", "Stop and leave voice"),
                ("-testmusic", "Diagnose FFmpeg/Opus/yt-dlp setup"),
            ]),
            'moderation': ("🛡️ Moderation Commands", discord.Color.red(), [
                ("-ban / -unban / -kick / -timeout", "Member moderation (needs permission)"),
                ("-warn", "Manually warn a member (3 = auto-timeout)"),
                ("-clear <amount>", "Bulk-delete messages"),
                ("-slowmode <seconds>", "Set channel slowmode"),
                ("-lock / -unlock", "Toggle @everyone send permission"),
                ("-createchannel / -deletechannel", "Manage channels"),
                ("-setnickname", "Change a member's nickname"),
                ("-banlist", "List recent bans"),
            ]),
            'games': ("🎮 Games", discord.Color.green(), [
                ("-tictactoe @user", "Play Tic-Tac-Toe"),
                ("-rps @user", "Play Rock-Paper-Scissors"),
                ("-trivia", "Answer a trivia question for bonus XP"),
                ("-8ball / -roll / -flip", "Quick randomizers"),
            ]),
            'admin': ("⚙️ Server Configuration", discord.Color.orange(), [
                ("-setprefix", "Change the command prefix"),
                ("-setwelcome / -setgreeting", "Configure welcome messages"),
                ("-setautorole", "Role auto-given on join"),
                ("-setmodlog", "Channel for moderation logs"),
                ("-addword / -removeword / -listwords", "Manage the banned-word filter"),
                ("-addcommand / -removecommand / -listcommands", "Custom text commands"),
                ("-reactionrole", "React on a message to grant a role"),
            ]),
        }

        if category and category.lower() in categories:
            title, color, fields = categories[category.lower()]
            embed = discord.Embed(title=title, color=color)
            for name, value in fields:
                embed.add_field(name=name, value=value, inline=False)
            await ctx.send(embed=embed)
            return

        embed = discord.Embed(title="🤖 Bot Command Menu",
                               description="Use `-help <category>` — categories: " + ", ".join(f"`{c}`" for c in categories),
                               color=discord.Color.blue())
        embed.add_field(name="🛡️ Moderation", value="`-ban` `-kick` `-timeout` `-clear` `-lock` `-slowmode`", inline=False)
        embed.add_field(name="🎮 Fun & Games", value="`-meme` `-joke` `-tictactoe` `-rps` `-trivia`", inline=False)
        embed.add_field(name="🎵 Music", value="`-play` `-pause` `-skip` `-queue`", inline=False)
        embed.add_field(name="🤖 AI", value="`-chat` `-ask` `-think` `-image`", inline=False)
        embed.add_field(name="ℹ️ Info", value="`-ping` `-serverinfo` `-userinfo` `-level` `-leaderboard`", inline=False)
        embed.set_footer(text=f"Created by {BOT_CREATOR}")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))