"""
AI chat via OpenRouter. The connection is tested once in cog_load (after
the bot has an event loop) instead of a blocking call at import time —
that used to add a real API round-trip to every single startup.
"""
import asyncio

import discord
from discord.ext import commands

from config import logger, OPENROUTER_API_KEY, AI_MODEL, VISION_MODEL, BOT_NAME, BOT_CREATOR

try:
    from openai import OpenAI
    OPENAI_PACKAGE_AVAILABLE = True
except ImportError:
    OPENAI_PACKAGE_AVAILABLE = False
    logger.error("openai package not installed. Run: pip install openai")

CREATOR_KEYWORDS = ['who made you', 'who created you', 'who developed you', 'your creator', 'your developer']
NAME_KEYWORDS = ['what is your name', 'who are you', 'what are you called', 'your name']


class AI(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.available = False
        self.client = None
        self.conversation_history: dict[int, list] = {}
        if OPENAI_PACKAGE_AVAILABLE and OPENROUTER_API_KEY:
            self.client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
        elif not OPENROUTER_API_KEY:
            logger.info("AI disabled - OPENROUTER_API_KEY not set")

    async def cog_load(self):
        if self.client:
            await self._verify_connection()

    async def _verify_connection(self):
        try:
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=AI_MODEL, messages=[{"role": "user", "content": "Hello"}], max_tokens=10)
            self.available = bool(response.choices)
            logger.info(f"AI initialized successfully with OpenRouter ({AI_MODEL})" if self.available
                        else "OpenRouter API test failed: No response")
        except Exception as e:
            self.available = False
            logger.error(f"OpenRouter initialization error: {e}")

    async def chat_with_ai(self, prompt: str, user_id: int, use_reasoning: bool = False):
        if not self.available or not self.client:
            return None, None
        try:
            system_prompt = {
                "role": "system",
                "content": (f"You are {BOT_NAME}, a friendly and helpful Discord bot AI assistant created by "
                             f"{BOT_CREATOR}. You assist users with their questions, provide helpful information, "
                             f"and engage in friendly conversations. Always identify yourself as {BOT_NAME} when "
                             f"asked about your name or identity.")
            }
            history = self.conversation_history.setdefault(user_id, [])
            messages = [system_prompt] + history[-8:] + [{"role": "user", "content": prompt}]

            api_params = {"model": AI_MODEL, "messages": messages, "max_tokens": 2000}
            if use_reasoning:
                api_params["extra_body"] = {"reasoning": {"enabled": True}}

            response = await asyncio.to_thread(self.client.chat.completions.create, **api_params)
            if not response.choices:
                return None, None

            assistant_message = response.choices[0].message
            ai_response = assistant_message.content

            history.append({"role": "user", "content": prompt})
            history.append({"role": "assistant", "content": ai_response})
            del history[:-10]

            reasoning_content = None
            if use_reasoning and hasattr(assistant_message, 'reasoning_details'):
                details = assistant_message.reasoning_details
                if details:
                    reasoning_content = str(getattr(details, '__dict__', details))

            return ai_response, reasoning_content
        except Exception as e:
            logger.error(f"AI chat error: {e}")
            return None, None

    async def analyze_image(self, image_url: str, prompt: str):
        if not self.available or not self.client:
            return None
        try:
            messages = [
                {"role": "system", "content": f"You are {BOT_NAME}, a helpful Discord bot AI assistant created by "
                                                f"{BOT_CREATOR}. You analyze images and provide detailed, accurate descriptions."},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}}
                ]}
            ]
            response = await asyncio.to_thread(
                self.client.chat.completions.create, model=VISION_MODEL, messages=messages, max_tokens=2000)
            return response.choices[0].message.content if response.choices else None
        except Exception as e:
            logger.error(f"Image analysis error: {e}")
            return None

    # ---------------------------------------------------------- commands --
    @commands.command()
    async def testai(self, ctx):
        embed = discord.Embed(title="🔍 AI Diagnostics", color=discord.Color.blue())
        embed.add_field(name="OpenAI Package", value="✅ Installed" if OPENAI_PACKAGE_AVAILABLE else "❌ Not Installed", inline=True)
        embed.add_field(name="API Key", value="✅ Set" if OPENROUTER_API_KEY else "❌ Missing", inline=True)
        embed.add_field(name="AI Status", value="✅ Operational" if self.available else "❌ Disabled", inline=True)

        if self.client:
            embed.add_field(name="Model", value=AI_MODEL, inline=False)
            async with ctx.typing():
                try:
                    response = await asyncio.to_thread(
                        self.client.chat.completions.create, model=AI_MODEL,
                        messages=[{"role": "user", "content": "Say 'Hello from OpenRouter!'"}], max_tokens=50)
                    if response.choices:
                        embed.add_field(name="✅ Test Response", value=response.choices[0].message.content, inline=False)
                        embed.color = discord.Color.green()
                        self.available = True
                except Exception as e:
                    embed.add_field(name="❌ Test Failed", value=str(e)[:1024], inline=False)
                    embed.color = discord.Color.red()
                    self.available = False
        else:
            embed.add_field(name="⚠️ Setup Instructions",
                             value="1. Install: `pip install openai`\n2. Set OPENROUTER_API_KEY in .env\n3. Restart bot",
                             inline=False)
            embed.color = discord.Color.orange()
        await ctx.send(embed=embed)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def chat(self, ctx, *, prompt: str):
        prompt_lower = prompt.lower()
        if any(k in prompt_lower for k in CREATOR_KEYWORDS):
            embed = discord.Embed(title="👨‍💻 About My Creator",
                                   description=f"I was created by **{BOT_CREATOR}**! 🎉\n\n{BOT_CREATOR} designed and "
                                                "programmed me to help manage Discord servers with AI capabilities "
                                                "powered by OpenRouter.",
                                   color=discord.Color.blue())
            await ctx.send(embed=embed)
            return

        if any(k in prompt_lower for k in NAME_KEYWORDS):
            embed = discord.Embed(title="🤖 About Me",
                                   description=f"I'm **{BOT_NAME}**, your friendly Discord bot AI assistant! I was "
                                                f"created by **{BOT_CREATOR}**.",
                                   color=discord.Color.blue())
            await ctx.send(embed=embed)
            return

        if not self.available:
            await ctx.send('❌ AI is currently unavailable. Use `-testai` to diagnose.')
            return

        async with ctx.typing():
            response, _ = await self.chat_with_ai(prompt, ctx.author.id)
            if not response:
                await ctx.send('❌ Failed to get AI response. Use `-testai` to check connection.')
                return
            if len(response) > 1900:
                chunks = [response[i:i + 1900] for i in range(0, len(response), 1900)]
                for i, chunk in enumerate(chunks):
                    await ctx.send(f"**Response (Part {i + 1}/{len(chunks)}):**\n{chunk}" if i == 0 else chunk)
            else:
                await ctx.send(response)

    @commands.command(aliases=['ask'])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def question(self, ctx, *, question: str):
        await ctx.invoke(ctx.bot.get_command('chat'), prompt=question)

    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def think(self, ctx, *, question: str):
        if not self.available:
            await ctx.send('❌ AI is currently unavailable.')
            return
        async with ctx.typing():
            response, reasoning = await self.chat_with_ai(question, ctx.author.id, use_reasoning=True)
            if not response:
                await ctx.send('❌ Failed to process question.')
                return
            embed = discord.Embed(title="🧠 AI Deep Thinking", description=response[:4000], color=discord.Color.purple())
            if reasoning:
                embed.add_field(name="💭 Reasoning Process", value=reasoning[:1024], inline=False)
            embed.set_footer(text=f"Asked by {ctx.author.display_name}")
            await ctx.send(embed=embed)

    @commands.command(name='clear-history')
    async def clear_history(self, ctx):
        self.conversation_history[ctx.author.id] = []
        embed = discord.Embed(title="✅ History Cleared", description="Your conversation history has been reset.",
                               color=discord.Color.green())
        await ctx.send(embed=embed)

    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def image(self, ctx, *, prompt: str = "Describe this image in detail"):
        if not self.available:
            await ctx.send('❌ AI is currently unavailable.')
            return
        if not ctx.message.attachments:
            await ctx.send('❌ Please attach an image to analyze.')
            return
        attachment = ctx.message.attachments[0]
        if not attachment.content_type or not attachment.content_type.startswith('image'):
            await ctx.send('❌ Please attach a valid image file.')
            return
        async with ctx.typing():
            response = await self.analyze_image(attachment.url, prompt)
            if not response:
                await ctx.send('❌ Failed to analyze image.')
                return
            embed = discord.Embed(title="🖼️ Image Analysis", description=response[:4096], color=discord.Color.blue())
            embed.set_thumbnail(url=attachment.url)
            embed.set_footer(text=f"Analyzed by {ctx.author.display_name}")
            await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AI(bot))