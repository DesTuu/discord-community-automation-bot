import asyncio

import discord
from discord.ext import commands

REQUEST_CHANNEL_ID = 1502586028135809125

active_requests = {}


# =========================
# 🔧 HELPERS
# =========================


def get_manage_channel_users(channel: discord.VoiceChannel):
    return [m for m in channel.members if channel.permissions_for(m).manage_channels]


# =========================
# 🔧 CLEANER
# =========================


async def request_cleaner(bot: commands.Bot):
    await bot.wait_until_ready()

    while not bot.is_closed():
        to_remove = []

        for rid, data in active_requests.items():
            if data.get("done"):
                to_remove.append(rid)

        for rid in to_remove:
            active_requests.pop(rid, None)

        await asyncio.sleep(60)


# =========================
# 🔧 MAIN PANEL
# =========================


class RequestMainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Przenieś mnie", style=discord.ButtonStyle.primary, custom_id="req_move"
    )
    async def move_me(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(
            "Wybierz kanał voice:", view=MoveSelectView(), ephemeral=True
        )

    @discord.ui.button(
        label="Daj mi dostęp", style=discord.ButtonStyle.success, custom_id="req_access"
    )
    async def access_me(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(
            "Wybierz kanał voice:", view=AccessSelectView(), ephemeral=True
        )


# =========================
# 🔧 MOVE SYSTEM (SAFE - NO channel_select)
# =========================


class MoveSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

        self.add_item(
            discord.ui.ChannelSelect(
                placeholder="Wybierz kanał voice",
                channel_types=[discord.ChannelType.voice],
                custom_id="move_select",
            )
        )

    @discord.ui.select(custom_id="move_select")
    async def callback(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ):

        user = interaction.user
        channel = select.values[0]

        if not isinstance(channel, discord.VoiceChannel):
            return await interaction.response.send_message(
                "Błąd kanału.", ephemeral=True
            )

        if not user.voice or not user.voice.channel:
            return await interaction.response.send_message(
                "Nie jesteś na voice.", ephemeral=True
            )

        try:
            await user.move_to(channel)
        except discord.Forbidden:
            return await interaction.response.send_message(
                "Brak permisji do przenoszenia.", ephemeral=True
            )

        managers = get_manage_channel_users(channel)
        ping = " ".join(m.mention for m in managers) if managers else "Brak moderatorów"

        await interaction.response.send_message(
            f"Przeniesiono do {channel.mention}\nPing: {ping}", ephemeral=True
        )


# =========================
# 🔧 ACCESS SYSTEM (SAFE)
# =========================


class AccessSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

        self.add_item(
            discord.ui.ChannelSelect(
                placeholder="Wybierz kanał voice",
                channel_types=[discord.ChannelType.voice],
                custom_id="access_select",
            )
        )

    @discord.ui.select(custom_id="access_select")
    async def callback(
        self, interaction: discord.Interaction, select: discord.ui.ChannelSelect
    ):

        guild = interaction.guild
        user = interaction.user
        channel = select.values[0]

        if not isinstance(channel, discord.VoiceChannel):
            return await interaction.response.send_message(
                "Błąd kanału.", ephemeral=True
            )

        owners = get_manage_channel_users(channel)

        if not owners:
            return await interaction.response.send_message(
                "Brak osób z Manage Channels.", ephemeral=True
            )

        request_id = len(active_requests) + 1

        view = AccessDecisionView(user.id, channel.id, request_id)

        request_channel = guild.get_channel(REQUEST_CHANNEL_ID)

        msg = await request_channel.send(
            f"🔔 PROŚBA O DOSTĘP\n"
            f"User: {user.mention}\n"
            f"Channel: {channel.mention}\n\n"
            f"Decydują: {', '.join(o.mention for o in owners)}",
            view=view,
        )

        active_requests[request_id] = {
            "user_id": user.id,
            "channel_id": channel.id,
            "done": False,
        }

        await interaction.response.send_message("Wysłano request.", ephemeral=True)


# =========================
# 🔧 ACCEPT / REJECT
# =========================


class AccessDecisionView(discord.ui.View):
    def __init__(self, user_id: int, channel_id: int, request_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.channel_id = channel_id
        self.request_id = request_id

    @discord.ui.button(label="Akceptuj", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):

        channel = interaction.guild.get_channel(self.channel_id)
        user = interaction.guild.get_member(self.user_id)

        if channel and user:
            overwrite = channel.overwrites_for(user)
            overwrite.connect = True
            await channel.set_permissions(user, overwrite=overwrite)

        await interaction.message.edit(content="✅ Prośba zaakceptowana", view=None)

        if self.request_id in active_requests:
            active_requests[self.request_id]["done"] = True

        await interaction.response.send_message("OK", ephemeral=True)

    @discord.ui.button(label="Odrzuć", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.message.edit(content="❌ Prośba odrzucona", view=None)

        if self.request_id in active_requests:
            active_requests[self.request_id]["done"] = True

        await interaction.response.send_message("OK", ephemeral=True)


# =========================
# 🔧 COMMAND
# =========================


@commands.hybrid_command()
async def button_lobby(ctx: commands.Context):
    await ctx.defer()

    channel = ctx.bot.get_channel(REQUEST_CHANNEL_ID)

    await channel.send("# Requests Panel", view=RequestMainView())

    await ctx.send("Panel utworzony", ephemeral=True)


# =========================
# 🔧 SETUP
# =========================


async def setup(bot: commands.Bot):
    bot.add_command(button_lobby)
    bot.add_view(RequestMainView())

    asyncio.create_task(request_cleaner(bot))
