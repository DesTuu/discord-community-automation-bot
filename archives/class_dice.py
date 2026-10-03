from discord.ext import commands
import settings
import random


class DiceStrings:
    def __init__(self, digit, dice_roll):
        self.correct_guess = f"Brawo! Udało Ci się! Twój typ: {digit}. Wyszło: {self.dice_roll}."
        self.wrong_guess = f"Niestety, nie udało Ci się... Twój typ: {digit}. Wyszło: {self.dice_roll}."
        self.incorrect_message = f"Wpisałeś niepoprawną wartość! Wpisz wartość tylko od 1 do 6 włącznie!"


class DiceObj(DiceStrings):
    def __init__(self, digit):
        self.result_range = range(1, 7)
        self.dice_roll = self.roll_the_dice()
        super().__init__(digit, self.dice_roll)

    def roll_the_dice(self):
        result = random.choice(self.result_range)
        return result


@commands.hybrid_command(
    brief=f"{settings.PREFIX}dice - rzuć kostką i zgadnij cyfrę",
)
async def dice(ctx: commands.Context, digit: int) -> None:
    dice_obj = DiceObj(digit)
    if 1 <= digit <= 6:
        if int(digit) == int(dice_obj.dice_roll):
            await ctx.send(dice_obj.correct_guess)
        else:
            await ctx.send(dice_obj.wrong_guess)
    else:
        await ctx.send(dice_obj.incorrect_message)


async def setup(bot: commands.Bot):
    bot.add_command(dice)
