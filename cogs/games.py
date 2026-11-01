"""New: interactive games — Tic-Tac-Toe, Rock-Paper-Scissors, and Trivia."""
import html
import random

import aiohttp
import discord
from discord.ext import commands


# --------------------------------------------------------- Tic-Tac-Toe --
class TicTacToeButton(discord.ui.Button):
    def __init__(self, x: int, y: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=y)
        self.x = x
        self.y = y

    async def callback(self, interaction: discord.Interaction):
        view: TicTacToeView = self.view
        if interaction.user.id != view.current_player.id:
            await interaction.response.send_message("It's not your turn.", ephemeral=True)
            return

        mark = 1 if view.current_player == view.player_x else 2
        view.board[self.y][self.x] = mark
        self.label = "❌" if mark == 1 else "⭕"
        self.style = discord.ButtonStyle.danger if mark == 1 else discord.ButtonStyle.success
        self.disabled = True

        winner = view.check_winner()
        if winner is not None:
            for child in view.children:
                child.disabled = True
            if winner == "draw":
                content = "🤝 It's a draw!"
            else:
                winning_player = view.player_x if winner == 1 else view.player_o
                content = f"🎉 {winning_player.mention} wins!"
            await interaction.response.edit_message(content=content, view=view)
            view.stop()
            return

        view.current_player = view.player_o if view.current_player == view.player_x else view.player_x
        await interaction.response.edit_message(
            content=f"❌ {view.player_x.mention} vs ⭕ {view.player_o.mention} — {view.current_player.mention}'s turn",
            view=view)


class TicTacToeView(discord.ui.View):
    def __init__(self, player_x: discord.Member, player_o: discord.Member):
        super().__init__(timeout=180)
        self.player_x = player_x
        self.player_o = player_o
        self.current_player = player_x
        self.board = [[0] * 3 for _ in range(3)]
        self.message: discord.Message | None = None
        for y in range(3):
            for x in range(3):
                self.add_item(TicTacToeButton(x, y))

    def check_winner(self):
        b = self.board
        lines = list(b)
        lines += [[b[r][c] for r in range(3)] for c in range(3)]
        lines.append([b[i][i] for i in range(3)])
        lines.append([b[i][2 - i] for i in range(3)])
        for line in lines:
            if line[0] != 0 and line[0] == line[1] == line[2]:
                return line[0]
        if all(cell != 0 for row in b for cell in row):
            return "draw"
        return None

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(content="⌛ Game timed out.", view=self)
            except discord.HTTPException:
                pass


# ----------------------------------------------------- Rock Paper Scissors --
class RPSButton(discord.ui.Button):
    def __init__(self, name: str, emoji: str):
        super().__init__(style=discord.ButtonStyle.secondary, label=name.capitalize(), emoji=emoji)
        self.name = name

    async def callback(self, interaction: discord.Interaction):
        await self.view.register_choice(interaction, self.name)


class RPSView(discord.ui.View):
    CHOICES = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
    BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}

    def __init__(self, player1: discord.Member, player2: discord.Member):
        super().__init__(timeout=60)
        self.player1 = player1
        self.player2 = player2
        self.choices: dict[int, str] = {}
        self.message: discord.Message | None = None
        for name, emoji in self.CHOICES.items():
            self.add_item(RPSButton(name, emoji))

    async def register_choice(self, interaction: discord.Interaction, choice: str):
        if interaction.user.id not in (self.player1.id, self.player2.id):
            await interaction.response.send_message("This isn't your game.", ephemeral=True)
            return
        if interaction.user.id in self.choices:
            await interaction.response.send_message("You've already chosen.", ephemeral=True)
            return
        self.choices[interaction.user.id] = choice
        await interaction.response.send_message(f"You chose {self.CHOICES[choice]} {choice}.", ephemeral=True)

        if len(self.choices) < 2:
            return

        for child in self.children:
            child.disabled = True
        c1, c2 = self.choices[self.player1.id], self.choices[self.player2.id]
        if c1 == c2:
            result = "🤝 It's a tie!"
        elif self.BEATS[c1] == c2:
            result = f"🎉 {self.player1.mention} wins!"
        else:
            result = f"🎉 {self.player2.mention} wins!"
        content = (f"**Rock Paper Scissors**\n{self.player1.mention}: {self.CHOICES[c1]}   vs   "
                   f"{self.player2.mention}: {self.CHOICES[c2]}\n{result}")
        if self.message:
            try:
                await self.message.edit(content=content, view=self)
            except discord.HTTPException:
                pass
        self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(content="⌛ Game timed out — not everyone chose in time.", view=self)
            except discord.HTTPException:
                pass


# ------------------------------------------------------------------ Trivia --
class TriviaButton(discord.ui.Button):
    def __init__(self, label: str, is_correct: bool):
        super().__init__(style=discord.ButtonStyle.secondary, label=label[:80])
        self.is_correct = is_correct

    async def callback(self, interaction: discord.Interaction):
        view: TriviaView = self.view
        if interaction.user.id != view.asker.id:
            await interaction.response.send_message("Start your own game with `-trivia`!", ephemeral=True)
            return
        if view.answered:
            return
        view.answered = True

        for child in view.children:
            child.disabled = True
            if isinstance(child, TriviaButton) and child.is_correct:
                child.style = discord.ButtonStyle.success
        if not self.is_correct:
            self.style = discord.ButtonStyle.danger

        if self.is_correct:
            text = "✅ Correct!"
            info_cog = interaction.client.get_cog('Info')
            if info_cog and interaction.guild:
                info_cog.add_xp(interaction.guild.id, interaction.user.id, 15)
        else:
            text = f"❌ Not quite — the answer was **{view.correct_answer}**."
        await interaction.response.edit_message(content=text, view=view)
        view.stop()


class TriviaView(discord.ui.View):
    def __init__(self, correct_answer: str, asker: discord.Member):
        super().__init__(timeout=30)
        self.correct_answer = correct_answer
        self.asker = asker
        self.answered = False
        self.message: discord.Message | None = None

    async def on_timeout(self):
        if self.answered:
            return
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(content=f"⌛ Time's up! The answer was **{self.correct_answer}**.", view=self)
            except discord.HTTPException:
                pass


class Games(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command()
    async def tictactoe(self, ctx, opponent: discord.Member):
        if opponent.bot:
            await ctx.send("❌ You can't play against a bot.")
            return
        if opponent == ctx.author:
            await ctx.send("❌ You can't play against yourself.")
            return
        view = TicTacToeView(ctx.author, opponent)
        msg = await ctx.send(
            f"❌ {ctx.author.mention} vs ⭕ {opponent.mention} — {ctx.author.mention}'s turn", view=view)
        view.message = msg

    @commands.command()
    async def rps(self, ctx, opponent: discord.Member):
        if opponent.bot or opponent == ctx.author:
            await ctx.send("❌ Choose another server member to play against.")
            return
        view = RPSView(ctx.author, opponent)
        msg = await ctx.send(
            f"🪨📄✂️ {ctx.author.mention} vs {opponent.mention} — pick your move! "
            "(choices stay secret until both have picked)", view=view)
        view.message = msg

    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def trivia(self, ctx):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://opentdb.com/api.php?amount=1&type=multiple') as resp:
                    payload = await resp.json()
        except Exception:
            await ctx.send("❌ Couldn't reach the trivia service, try again in a bit.")
            return

        results = payload.get('results') if payload else None
        if not results:
            await ctx.send("❌ Couldn't fetch a trivia question, try again.")
            return

        q = results[0]
        question = html.unescape(q['question'])
        correct = html.unescape(q['correct_answer'])
        options = [html.unescape(a) for a in q['incorrect_answers']] + [correct]
        random.shuffle(options)

        view = TriviaView(correct, ctx.author)
        for opt in options:
            view.add_item(TriviaButton(opt, opt == correct))

        embed = discord.Embed(title=f"🧠 Trivia — {html.unescape(q['category'])}",
                               description=question, color=discord.Color.blurple())
        embed.set_footer(text=f"Difficulty: {q['difficulty'].capitalize()} | 30 seconds | +15 XP if correct")
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg


async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))