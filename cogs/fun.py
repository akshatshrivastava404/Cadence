"""Lightweight fun commands: 8ball, coin flip, dice roll, memes, jokes."""
import random

import aiohttp
import discord
from discord.ext import commands

from config import logger

EIGHT_BALL_RESPONSES = [
    "Yes, definitely!", "No, absolutely not.", "Maybe...",
    "Without a doubt!", "Very doubtful.", "Ask again later.",
    "It is certain.", "Cannot predict now.", "Don't count on it.",
    "My sources say yes.", "Outlook not so good.", "Signs point to yes."
]


class Fun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='8ball')
    async def eight_ball(self, ctx, *, question: str):
        embed = discord.Embed(title="🎱 Magic 8-Ball",
                               description=f"**Question:** {question}\n**Answer:** {random.choice(EIGHT_BALL_RESPONSES)}",
                               color=discord.Color.purple())
        await ctx.send(embed=embed)

    @commands.command()
    async def flip(self, ctx):
        result = random.choice(["Heads", "Tails"])
        embed = discord.Embed(title="🪙 Coin Flip", description=f"**Result:** {result}", color=discord.Color.gold())
        await ctx.send(embed=embed)

    @commands.command()
    async def roll(self, ctx, sides: int = 6):
        if not 2 <= sides <= 100:
            await ctx.send('❌ Dice must have between 2 and 100 sides')
            return
        result = random.randint(1, sides)
        embed = discord.Embed(title="🎲 Dice Roll",
                               description=f"Rolled a **{sides}-sided** die\n**Result:** {result}",
                               color=discord.Color.blue())
        await ctx.send(embed=embed)

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def meme(self, ctx):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://meme-api.com/gimme') as resp:
                    if resp.status != 200:
                        await ctx.send('❌ Failed to fetch meme')
                        return
                    payload = await resp.json()
        except Exception as e:
            await ctx.send('❌ Error fetching meme')
            logger.error(f"Meme command error: {e}")
            return
        embed = discord.Embed(title=payload['title'], color=discord.Color.random())
        embed.set_image(url=payload['url'])
        embed.set_footer(text=f"👍 {payload.get('ups', 0)} | r/{payload.get('subreddit', 'unknown')}")
        await ctx.send(embed=embed)

    @commands.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def joke(self, ctx):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://official-joke-api.appspot.com/random_joke') as resp:
                    if resp.status != 200:
                        await ctx.send('❌ Failed to fetch joke')
                        return
                    payload = await resp.json()
        except Exception as e:
            await ctx.send('❌ Error fetching joke')
            logger.error(f"Joke command error: {e}")
            return
        embed = discord.Embed(title="😂 Random Joke",
                               description=f"**{payload['setup']}**\n\n||{payload['punchline']}||",
                               color=discord.Color.blue())
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))