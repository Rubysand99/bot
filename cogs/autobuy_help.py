"""
cogs/autobuy_help.py — Giao diện `.help autobuy`: 7 trang hướng dẫn, chuyển trang bằng menu chọn + nút ◀ ▶.
Nội dung ở core/autobuy_help_data.py (thuần dữ liệu, có test giới hạn độ dài). Chỉ người gõ lệnh bấm được, hết hạn sau 10 phút.
Module trợ giúp (không phải cog) — được cogs/admin.py import khi gõ `.help autobuy`.
"""
import discord

from core.autobuy_help_data import PAGE_ALIASES, PAGE_ORDER, PAGES

COLOR_HELP = 0x00FFAA
TIMEOUT = 600


def build_embed(key: str, version: str) -> discord.Embed:
    p = PAGES[key]
    e = discord.Embed(title=f"{p['emoji']}  {p['title']}", description=p["description"], color=COLOR_HELP)
    for name, value in p["fields"]:
        e.add_field(name=name, value=value, inline=False)
    e.set_footer(text=f"TuyTam Store  •  v{version}  •  Trang {PAGE_ORDER.index(key) + 1}/{len(PAGE_ORDER)}  •  .help để về trang chính")
    return e


class AutoBuyHelpView(discord.ui.View):
    def __init__(self, author_id: int, version: str, key: str = "tongquan"):
        super().__init__(timeout=TIMEOUT)
        self.author_id, self.version, self.key = author_id, version, key
        self.message: discord.Message | None = None
        self.select = discord.ui.Select(placeholder="Chọn trang hướng dẫn Auto Buy…", min_values=1, max_values=1,
                                        options=self._options())
        self.select.callback = self._on_select
        self.add_item(self.select)

    def _options(self) -> list[discord.SelectOption]:
        return [discord.SelectOption(label=f"{i}. {PAGES[k]['label']}", value=k, emoji=PAGES[k]["emoji"], default=(k == self.key))
                for i, k in enumerate(PAGE_ORDER, 1)]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Chỉ người gõ lệnh mới đổi trang được — hãy tự gõ `.help autobuy`.", ephemeral=True)
            return False
        return True

    async def _show(self, interaction: discord.Interaction, key: str) -> None:
        self.key = key
        self.select.options = self._options()
        await interaction.response.edit_message(embed=build_embed(key, self.version), view=self)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        await self._show(interaction, interaction.data["values"][0])

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, row=1)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._show(interaction, PAGE_ORDER[(PAGE_ORDER.index(self.key) - 1) % len(PAGE_ORDER)])

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, row=1)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._show(interaction, PAGE_ORDER[(PAGE_ORDER.index(self.key) + 1) % len(PAGE_ORDER)])

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(view=None)     # bỏ menu khi hết hạn, giữ nguyên nội dung đang xem
            except discord.HTTPException:
                pass


async def send_autobuy_help(ctx, page_arg: str | None, version: str) -> None:
    """`.help autobuy [trang]` — page_arg: setup/ban/mua/thanhtoan/quanly/loi (hoặc số 1-7); None = tổng quan."""
    key = "tongquan"
    if page_arg:
        key = PAGE_ALIASES.get(page_arg.lower().strip())
        if not key:
            pages = " | ".join(f"`{k}`" for k in PAGE_ORDER)
            return await ctx.reply(f"❌ Không có trang `{page_arg}`.\nCác trang Auto Buy: {pages}\nVí dụ: `.help autobuy setup`")
    view = AutoBuyHelpView(ctx.author.id, version, key)
    view.message = await ctx.reply(embed=build_embed(key, version), view=view)
