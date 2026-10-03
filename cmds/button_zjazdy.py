"""Extension bez Cog: komenda /button_zjazdy i przycisk tworzenia zjazdu."""

from __future__ import annotations

import discord
from discord.ext import commands


# Tylko ten użytkownik może wysłać panel. Zmień na swoje ID, jeśli potrzeba.
PANEL_ADMIN_ID = 354712325053218819

# Kategoria, w której bot tworzy kanały zjazdów.
ZJAZDY_CATEGORY_ID: int | None = 1550418206240411668

# Nie nadajemy żadnych uprawnień związanych z wątkami.
THREAD_PERMISSIONS = {
    "manage_threads",
    "create_public_threads",
    "create_private_threads",
    "send_messages_in_threads",
}


def clean_date(value: str) -> str | None:
    value = value.strip()
    return value if value and len(value) <= 100 and "\n" not in value and "\r" not in value else None


def channel_name_from_date(date: str) -> str:
    """Kanał ma myślniki, nawet gdy data zostanie wpisana z kropkami."""
    return date.replace(".", "-")


def creator_permissions() -> discord.PermissionOverwrite:
    """Wszystkie możliwe uprawnienia kanałowe, poza uprawnieniami do wątków."""
    overwrite = discord.PermissionOverwrite()
    for permission_name, _ in discord.Permissions.all_channel():
        # False jawnie blokuje wątki, także jeśli rola użytkownika je posiada.
        setattr(overwrite, permission_name, permission_name not in THREAD_PERMISSIONS)
    return overwrite


class CreateZjazdModal(discord.ui.Modal, title="Stwórz zjazd"):
    date = discord.ui.TextInput(label="Data zjazdu", placeholder="np. 12-10-2026", max_length=100)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        date = clean_date(self.date.value)
        if date is None or interaction.guild is None:
            return await interaction.response.send_message("Podaj poprawną datę w jednej linii.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)
        category = interaction.guild.get_channel(ZJAZDY_CATEGORY_ID) if ZJAZDY_CATEGORY_ID else None
        if category is not None and not isinstance(category, discord.CategoryChannel):
            return await interaction.followup.send("Skonfigurowana kategoria nie istnieje.", ephemeral=True)

        try:
            channel = await interaction.guild.create_text_channel(
                name=channel_name_from_date(date),
                category=category,
                overwrites={interaction.user: creator_permissions()},
                reason=f"Zjazd utworzony przez {interaction.user} ({interaction.user.id})",
            )
            await channel.send(f"# {date}")
        except discord.Forbidden:
            return await interaction.followup.send(
                "Bot potrzebuje uprawnień Manage Channels i Send Messages.", ephemeral=True
            )
        except discord.HTTPException:
            return await interaction.followup.send("Nie udało się utworzyć kanału.", ephemeral=True)

        await interaction.followup.send(
            f"Utworzono zjazd: {channel.mention}. Masz na nim wszystkie uprawnienia poza wątkami.",
            ephemeral=True,
        )


class ZjazdyPanelView(discord.ui.View):
    """Persistent view: przycisk dalej działa po restarcie bota."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Stwórz zjazd",
        style=discord.ButtonStyle.success,
        custom_id="zjazdy:create",
    )
    async def create(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(CreateZjazdModal())


@commands.hybrid_command(name="button_zjazdy", description="Wyślij panel tworzenia zjazdów")
async def button_zjazdy(ctx: commands.Context) -> None:
    if ctx.author.id != PANEL_ADMIN_ID:
        return await ctx.send("Brak dostępu do tworzenia panelu.", ephemeral=True)
    await ctx.send("# Panel zjazdów\nKliknij przycisk, aby utworzyć zjazd.", view=ZjazdyPanelView())


async def setup(bot: commands.Bot) -> None:
    bot.add_command(button_zjazdy)
    bot.add_view(ZjazdyPanelView())
