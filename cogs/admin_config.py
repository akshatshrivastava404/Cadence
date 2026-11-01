"""
Bot configuration: prefix, welcome message, auto-role, banned words,
custom text commands, reaction roles, and the mod-log channel. All
per-server.
"""
import discord
from discord.ext import commands

from config import logger


class AdminConfig(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage("This command only works in a server.")
        return True

    # ------------------------------------------------------- on_message --
    async def maybe_run_custom_command(self, message: discord.Message):
        guild_commands = self.bot.data.custom_commands.get(str(message.guild.id))
        if not guild_commands:
            return
        response = guild_commands.get(message.content.lower())
        if response:
            await message.channel.send(response)

    # --------------------------------------------------------- listeners --
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        gid = str(member.guild.id)
        channel_id = self.bot.data.greeting_channels.get(gid)
        channel = member.guild.get_channel(int(channel_id)) if channel_id else discord.utils.get(
            member.guild.text_channels, name='general')

        if channel:
            msg = self.bot.data.welcome_messages.get(
                gid, f'Welcome to **{member.guild.name}**, {member.mention}! 🎉')
            try:
                embed = discord.Embed(
                    title="👋 Welcome!",
                    description=msg.format(member=member.mention, server=member.guild.name,
                                            count=member.guild.member_count),
                    color=discord.Color.green())
                embed.set_thumbnail(url=member.display_avatar.url)
                await channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Welcome message failed: {e}")

        auto_role_id = self.bot.data.auto_role.get(gid)
        if auto_role_id:
            role = member.guild.get_role(int(auto_role_id))
            if role:
                try:
                    await member.add_roles(role, reason="Auto-role on join")
                except Exception as e:
                    logger.error(f"Auto-role failed: {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member is None or payload.member.bot:
            return
        key = f"{payload.message_id}_{payload.emoji}"
        role_id = self.bot.data.reaction_roles.get(key)
        if not role_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        role = guild.get_role(int(role_id))
        if role:
            try:
                await payload.member.add_roles(role, reason="Reaction role")
            except Exception as e:
                logger.error(f"Reaction role failed: {e}")

    # ---------------------------------------------------------- commands --
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setprefix(self, ctx, prefix: str):
        if len(prefix) > 5:
            await ctx.send("❌ Prefix must be 5 characters or less")
            return
        self.bot.data.prefixes[str(ctx.guild.id)] = prefix
        self.bot.data.save_data()
        embed = discord.Embed(title="✅ Prefix Updated",
                               description=f"New prefix: `{prefix}`\nExample: `{prefix}help`",
                               color=discord.Color.green())
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setwelcome(self, ctx, *, message: str):
        self.bot.data.welcome_messages[str(ctx.guild.id)] = message
        self.bot.data.save_data()
        embed = discord.Embed(title="✅ Welcome Message Set", description=message, color=discord.Color.green())
        embed.set_footer(text="Use {member}, {server}, {count} as placeholders")
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setgreeting(self, ctx, channel: discord.TextChannel):
        self.bot.data.greeting_channels[str(ctx.guild.id)] = str(channel.id)
        self.bot.data.save_data()
        await ctx.send(f"✅ Welcome messages will now be sent to {channel.mention}")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setautorole(self, ctx, role: discord.Role):
        self.bot.data.auto_role[str(ctx.guild.id)] = str(role.id)
        self.bot.data.save_data()
        await ctx.send(f"✅ New members will automatically receive the {role.mention} role")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setmodlog(self, ctx, channel: discord.TextChannel):
        self.bot.data.mod_log_channels[str(ctx.guild.id)] = str(channel.id)
        self.bot.data.save_data()
        await ctx.send(f"✅ Moderation actions will now be logged to {channel.mention}")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def addword(self, ctx, *, word: str):
        gid = str(ctx.guild.id)
        self.bot.data.banned_words[gid].add(word.lower())
        self.bot.data.save_data()
        moderation = self.bot.get_cog('Moderation')
        if moderation:
            moderation.invalidate_word_cache(ctx.guild.id)
        await ctx.send(f"✅ Added `{word}` to this server's banned words list")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def removeword(self, ctx, *, word: str):
        gid = str(ctx.guild.id)
        word_lower = word.lower()
        if word_lower in self.bot.data.banned_words.get(gid, set()):
            self.bot.data.banned_words[gid].discard(word_lower)
            self.bot.data.save_data()
            moderation = self.bot.get_cog('Moderation')
            if moderation:
                moderation.invalidate_word_cache(ctx.guild.id)
            await ctx.send(f"✅ Removed `{word}` from this server's banned words list")
        else:
            await ctx.send(f"❌ `{word}` is not in this server's banned words list")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def listwords(self, ctx):
        words = self.bot.data.banned_words.get(str(ctx.guild.id))
        if not words:
            await ctx.send("📋 No banned words configured for this server")
            return
        text = ", ".join(f"`{w}`" for w in sorted(words))
        embed = discord.Embed(title="🚫 Banned Words List", description=text[:4096], color=discord.Color.red())
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def addcommand(self, ctx, trigger: str, *, response: str):
        gid = str(ctx.guild.id)
        self.bot.data.custom_commands[gid][trigger.lower()] = response
        self.bot.data.save_data()
        await ctx.send(f"✅ Custom command `{trigger.lower()}` added")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def removecommand(self, ctx, trigger: str):
        gid = str(ctx.guild.id)
        trigger = trigger.lower()
        if trigger in self.bot.data.custom_commands.get(gid, {}):
            del self.bot.data.custom_commands[gid][trigger]
            self.bot.data.save_data()
            await ctx.send(f"✅ Custom command `{trigger}` removed")
        else:
            await ctx.send(f"❌ `{trigger}` is not a registered custom command")

    @commands.command()
    async def listcommands(self, ctx):
        commands_map = self.bot.data.custom_commands.get(str(ctx.guild.id))
        if not commands_map:
            await ctx.send("📋 No custom commands configured for this server")
            return
        text = ", ".join(f"`{t}`" for t in sorted(commands_map))
        embed = discord.Embed(title="💬 Custom Commands", description=text[:4096], color=discord.Color.blue())
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(add_reactions=True, manage_roles=True)
    async def reactionrole(self, ctx, message_id: int, emoji: str, role: discord.Role):
        try:
            message = await ctx.channel.fetch_message(message_id)
        except discord.NotFound:
            await ctx.send("❌ Couldn't find that message in this channel.")
            return
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            await ctx.send("❌ That doesn't look like an emoji I can react with.")
            return
        key = f"{message_id}_{emoji}"
        self.bot.data.reaction_roles[key] = str(role.id)
        self.bot.data.save_data()
        await ctx.send(f"✅ Reacting {emoji} on that message now grants {role.mention}")


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminConfig(bot))