from discord.ext import commands
import settings


@commands.hybrid_command(
    brief=f"{settings.PREFIX}answer treśćwiadomości - odpowiedz na pytanie",
)
async def answer(ctx: commands.Context, message: str) -> None:
    answer_channel = ctx.bot.get_channel(1481382571207168155)
    await answer_channel.send(f"### {ctx.author.mention}: {message}")
    await ctx.send("Odpowiedź wysłana!", ephemeral=True)


async def setup(bot: commands.Bot):
    bot.add_command(answer)
