from discord.ext import commands, tasks
import discord
import time
import asyncio

# =========================
# CONFIG
# =========================

REQUEST_CHANNEL_ID   = 1496568003565715578   # Kanał z panelem i wiadomościami requestów
VOICE_CATEGORY_ID    = 1261094785779765248
EXCLUDED_CHANNEL_ID  = 1412829208018812938

ALLOWED_USER_ID      = 354712325053218819
LOG_CHANNEL_ID       = 1504504794897973289

PANEL_MESSAGE_ID     = 1504503854870434046   # Wiadomość panelu – nigdy nie jest usuwana
MESSAGE_TTL_MIN      = 10                    # Po ilu minutach znikają wiadomości requestów

request_cooldown: dict[int, float] = {}


# =========================
# HELPERS
# =========================

def is_on_cooldown(user_id: int, cooldown: int = 60) -> tuple[bool, int]:
    now  = time.time()
    last = request_cooldown.get(user_id, 0)
    if now - last < cooldown:
        return True, int(cooldown - (now - last))
    request_cooldown[user_id] = now
    return False, 0


def reset_cooldown(user_id: int) -> None:
    request_cooldown.pop(user_id, None)


def get_channel_owner(channel: discord.VoiceChannel) -> discord.Member | None:
    """Zwraca pierwszego membera z manage_channels na tym kanale (właściciel)."""
    for member in channel.members:
        if channel.permissions_for(member).manage_channels:
            return member
    return None


def has_connect_permission(channel: discord.VoiceChannel, user: discord.Member) -> bool:
    return channel.permissions_for(user).connect


async def send_log(guild: discord.Guild, text: str) -> None:
    log_channel = guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(text)


async def schedule_delete(message: discord.Message, delay_minutes: int) -> None:
    """Usuwa wiadomość po podanej liczbie minut."""
    await asyncio.sleep(delay_minutes * 60)
    try:
        await message.delete()
    except Exception:
        pass


# =========================
# MAIN PANEL
# =========================

class RequestMainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _get_category(self, interaction: discord.Interaction) -> discord.CategoryChannel | None:
        category = interaction.guild.get_channel(VOICE_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message("Brak kategorii głosowej.", ephemeral=True)
            return None
        return category

    @discord.ui.button(
        label="Przenieś mnie",
        style=discord.ButtonStyle.primary,
        custom_id="req_move"
    )
    async def move_me(self, interaction: discord.Interaction, button: discord.ui.Button):
        category = await self._get_category(interaction)
        if not category:
            return
        await interaction.response.send_message(
            "Wybierz kanał docelowy:",
            view=ChannelSelectView("move", category),
            ephemeral=True
        )

    @discord.ui.button(
        label="Daj mi dostęp",
        style=discord.ButtonStyle.success,
        custom_id="req_access"
    )
    async def access_me(self, interaction: discord.Interaction, button: discord.ui.Button):
        category = await self._get_category(interaction)
        if not category:
            return
        await interaction.response.send_message(
            "Wybierz kanał:",
            view=ChannelSelectView("access", category),
            ephemeral=True
        )


# =========================
# SELECT VIEW
# =========================

class ChannelSelectView(discord.ui.View):
    def __init__(self, action: str, category: discord.CategoryChannel):
        super().__init__(timeout=60)

        valid_channels = [
            ch for ch in category.voice_channels
            if ch.id != EXCLUDED_CHANNEL_ID and get_channel_owner(ch) is not None
        ]

        options = (
            [
                discord.SelectOption(label=ch.name[:100], value=str(ch.id))
                for ch in valid_channels[:25]
            ]
            if valid_channels
            else [discord.SelectOption(label="Brak dostępnych kanałów", value="0")]
        )

        self.add_item(ChannelSelect(action, options))


# =========================
# SELECT
# =========================

class ChannelSelect(discord.ui.Select):
    def __init__(self, action: str, options: list):
        self.action = action
        super().__init__(
            placeholder="Wybierz kanał...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "0":
            return await interaction.response.send_message(
                "Brak dostępnych kanałów.", ephemeral=True
            )

        channel = interaction.guild.get_channel(int(self.values[0]))
        if not channel:
            return await interaction.response.send_message(
                "Kanał nie istnieje.", ephemeral=True
            )

        user = interaction.user

        # Wspólne sprawdzenia dla obu akcji
        if has_connect_permission(channel, user):
            return await interaction.response.send_message(
                "Masz już dostęp do tego kanału.", ephemeral=True
            )

        if not user.voice:
            return await interaction.response.send_message(
                "Musisz być na kanale głosowym.", ephemeral=True
            )

        owner = get_channel_owner(channel)
        if not owner:
            return await interaction.response.send_message(
                "Brak właściciela na tym kanale – nie można wysłać prośby.", ephemeral=True
            )

        cd, left = is_on_cooldown(user.id)
        if cd:
            return await interaction.response.send_message(
                f"⏳ Poczekaj jeszcze **{left}s**.", ephemeral=True
            )

        req_channel = interaction.guild.get_channel(REQUEST_CHANNEL_ID)
        if not req_channel:
            reset_cooldown(user.id)
            return await interaction.response.send_message(
                "Kanał requestów nie istnieje.", ephemeral=True
            )

        # Treść prośby zależy od akcji
        if self.action == "move":
            content = (
                f"<@!{user.id}> chce dostać się na kanał **{channel.name}** "
                f"<@!{owner.id}>"
            )
            action_label = "przeniesienia"
        else:
            content = (
                f"<@!{user.id}> chce uprawnienia dostępu na kanał **{channel.name}** "
                f"<@!{owner.id}>"
            )
            action_label = "dostępu"

        view = DecisionView(
            requester_id=user.id,
            owner_id=owner.id,
            channel_id=channel.id,
            action=self.action
        )

        try:
            msg = await req_channel.send(content, view=view)
        except discord.HTTPException:
            reset_cooldown(user.id)
            return await interaction.response.send_message(
                "Nie udało się wysłać prośby.", ephemeral=True
            )

        view.message = msg

        # Zaplanuj usunięcie po MESSAGE_TTL_MIN minutach
        asyncio.create_task(schedule_delete(msg, MESSAGE_TTL_MIN))

        await send_log(
            interaction.guild,
            (
                f"## 📩 Nowa prośba o {action_label}\n"
                f"👤 Użytkownik: {user.mention}\n"
                f"🔊 Kanał: {channel.mention}\n"
                f"👑 Właściciel: {owner.mention}"
            )
        )

        await interaction.response.send_message(
            "Prośba wysłana! ✅", ephemeral=True
        )


# =========================
# DECISION VIEW (Akceptuj / Odrzuć)
# =========================

class DecisionView(discord.ui.View):
    def __init__(self, requester_id: int, owner_id: int, channel_id: int, action: str):
        super().__init__(timeout=None)   # timeout obsługuje schedule_delete, nie view
        self.requester_id = requester_id
        self.owner_id     = owner_id
        self.channel_id   = channel_id
        self.action       = action
        self.message: discord.Message | None = None

    def _is_owner(self, interaction: discord.Interaction) -> bool:
        """Tylko właściciel kanału (manage_channels) może klikać."""
        channel = interaction.guild.get_channel(self.channel_id)
        return bool(
            channel
            and channel.permissions_for(interaction.user).manage_channels
        )

    # ---------- AKCEPTUJ ----------

    @discord.ui.button(label="Akceptuj ✅", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._is_owner(interaction):
            return await interaction.response.send_message(
                "Nie jesteś właścicielem tego kanału.", ephemeral=True
            )

        channel   = interaction.guild.get_channel(self.channel_id)
        requester = interaction.guild.get_member(self.requester_id)

        if not requester:
            await interaction.message.edit(
                content="❌ Użytkownik opuścił serwer.", view=None
            )
            return await interaction.response.send_message(
                "Użytkownik nie jest już na serwerze.", ephemeral=True
            )

        # Wykonaj akcję
        if self.action == "move":
            try:
                await requester.move_to(channel)
            except discord.Forbidden:
                return await interaction.response.send_message(
                    "Bot nie ma uprawnień do przenoszenia.", ephemeral=True
                )
        else:
            overwrite         = channel.overwrites_for(requester)
            overwrite.connect = True
            await channel.set_permissions(requester, overwrite=overwrite)

        result_text = (
            f"<@!{self.owner_id}> zaakceptował prośbę <@!{self.requester_id}>"
        )

        await interaction.message.edit(content=result_text, view=None)

        await send_log(
            interaction.guild,
            (
                f"## ✅ Prośba zaakceptowana\n"
                f"👑 Właściciel: {interaction.user.mention}\n"
                f"👤 Użytkownik: {requester.mention}\n"
                f"🔊 Kanał: {channel.mention}\n"
                f"🔧 Akcja: {'przeniesienie' if self.action == 'move' else 'dostęp'}"
            )
        )

        await interaction.response.send_message("Zaakceptowano. ✅", ephemeral=True)

    # ---------- ODRZUĆ ----------

    @discord.ui.button(label="Odrzuć ❌", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._is_owner(interaction):
            return await interaction.response.send_message(
                "Nie jesteś właścicielem tego kanału.", ephemeral=True
            )

        channel = interaction.guild.get_channel(self.channel_id)

        result_text = (
            f"<@!{self.owner_id}> odrzucił prośbę <@!{self.requester_id}>"
        )

        await interaction.message.edit(content=result_text, view=None)

        await send_log(
            interaction.guild,
            (
                f"## ❌ Prośba odrzucona\n"
                f"👑 Właściciel: {interaction.user.mention}\n"
                f"👤 Użytkownik: <@{self.requester_id}>\n"
                f"🔊 Kanał: {channel.mention}\n"
                f"🔧 Akcja: {'przeniesienie' if self.action == 'move' else 'dostęp'}"
            )
        )

        await interaction.response.send_message("Odrzucono.", ephemeral=True)


# =========================
# COG
# =========================

class RequestsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def cog_unload(self):
        pass


# =========================
# COMMAND
# =========================

@commands.hybrid_command(name="button_requests")
async def button_requests(ctx: commands.Context):
    if ctx.author.id != ALLOWED_USER_ID:
        return await ctx.send("Brak dostępu.", ephemeral=True)

    await ctx.send("# Panel requestów", view=RequestMainView())


# =========================
# SETUP
# =========================

async def setup(bot: commands.Bot):
    await bot.add_cog(RequestsCog(bot))
    bot.add_command(button_requests)
    bot.add_view(RequestMainView())
