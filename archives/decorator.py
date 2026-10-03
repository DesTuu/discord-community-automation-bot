from discord.ext import commands
import settings

@commands.hybrid_command(
    brief=f"{settings.PREFIX}decorator",
    hidden=True
)
async def decorator(ctx: commands.Context) -> None:
    def decorator_checker(fun):
        async def inner_function() -> str:
            result = await fun()
            command_invocator = ctx.author.mention
            command_guild = ctx.guild.name
            command_channel = ctx.channel.name
            my_string = (f"{command_invocator} wykonał komendę na serwerze {command_guild}, "
                         f"na kanale {command_channel}\n\nWykonana czynność: {result}")
            return my_string

        return inner_function

    @decorator_checker
    async def first() -> str:
        return "Veni"

    @decorator_checker
    async def second() -> str:
        return "Vidi"

    @decorator_checker
    async def third() -> str:
        return "Vici"

    results = await first(), await second(), await third()
    for i in results:
        await ctx.send(i)


async def setup(bot: commands.Bot):
    bot.add_command(decorator)