"""
Entry point. Builds the bot, loads every cog, and owns the handful of
events that need to stay centralized rather than living in a cog.

on_message specifically: the original bot's moderation -> custom-command ->
XP pipeline relies on an early return (a deleted message shouldn't also
award XP or trigger a custom command). If that were split across
independent @commands.Cog.listener() handlers, discord.py would dispatch
them all regardless of what any one of them decided, breaking that
ordering. So on_message is kept here and just calls into cogs for the
actual logic.
"""
import asyncio
import sys

import discord
from discord.ext import commands, tasks

from config import TOKEN, intents, get_prefix, logger
from storage import BotData

INITIAL_EXTENSIONS = [
    'cogs.moderation',
    'cogs.admin_config',
    'cogs.ai',
    'cogs.music',
    'cogs.fun',
    'cogs.games',
    'cogs.info',
]



class CadenceBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=get_prefix, intents=intents, help_command=None)
        self.data = BotData()

    async def setup_hook(self):
        self.data.load_data()
        for extension in INITIAL_EXTENSIONS:
            try:
                await self.load_extension(extension)
                logger.info(f"Loaded extension: {extension}")
            except Exception:
                logger.exception(f"Failed to load extension: {extension}")
        if not save_data_loop.is_running():
            save_data_loop.start()

    async def on_ready(self):
        logger.info(f'Logged in as {self.user}')
        print(f'Bot ready! Serving {len(self.guilds)} servers')
        ai_cog = self.get_cog('AI')
        music_cog = self.get_cog('Music')
        print(f'AI: {"ENABLED" if ai_cog and ai_cog.available else "DISABLED"}')
        print(f'Music: {"ENABLED" if music_cog and music_cog.available else "DISABLED"}')
        await self.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching, name=f"{len(self.guilds)} servers | -help"))

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f'❌ Missing argument: `{error.param.name}`')
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f'❌ {error}')
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send(f"❌ You need these permissions to do that: `{', '.join(error.missing_permissions)}`")
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send(f"❌ I'm missing permissions to do that: `{', '.join(error.missing_permissions)}`")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏳ Slow down — try again in {error.retry_after:.1f}s.")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("❌ That command only works in a server.")
        else:
            original = getattr(error, 'original', error)
            logger.error(f"Command error in '{ctx.command}': {original}", exc_info=original)
            try:
                await ctx.send(f'❌ `{ctx.command}` hit an unexpected error: `{original}`')
            except Exception:
                pass

    async def on_disconnect(self):
        logger.info("Bot disconnected, saving data...")
        self.data.save_data()

    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        moderation = self.get_cog('Moderation')
        if moderation and await moderation.scan_message(message):
            return  # deleted for a banned word — stop here, like the original did

        admin_config = self.get_cog('AdminConfig')
        if admin_config:
            await admin_config.maybe_run_custom_command(message)

        info = self.get_cog('Info')
        if info:
            await info.maybe_award_xp(message)

        await self.process_commands(message)


bot = CadenceBot()


@tasks.loop(minutes=5)
async def save_data_loop():
    await asyncio.to_thread(bot.data.save_data)
    logger.info("Data auto-saved")


@save_data_loop.before_loop
async def before_save_data_loop():
    await bot.wait_until_ready()


def main():
    if not TOKEN:
        print('❌ ERROR: DISCORD_TOKEN not found in .env file')
        print('📝 Create a .env file with: DISCORD_TOKEN=your_token_here')
        sys.exit(1)

    print("\n" + "=" * 50)
    print("🤖 Discord Bot Starting...")
    print("=" * 50)

    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print('❌ ERROR: Invalid Discord token')
        sys.exit(1)
    except Exception as e:
        print(f'❌ ERROR: Bot failed to start: {e}')
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()