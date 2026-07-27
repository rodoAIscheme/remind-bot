import discord
from discord.ext import commands
from discord import app_commands
import os

LOGO_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'ロゴ')
)
PANEL_CHANNEL = "企画選択"

# ── 企画定義（ロゴ・ロール・色・ボタンID） ────────────────────
# emoji_name: サーバーに登録したカスタム絵文字名
ENTERPRISES = [
    {
        "name":       "うみさんぽ",
        "role":       "うみさんぽ",
        "logo_file":  "うみさんぽ　新ロゴ.jpg",
        "logo_safe":  "logo_umisanpo.jpg",
        "color":      0x1E90FF,
        "cid":        "role:umisanpo",
        "emoji_name": "_umisanpo_",
        "emoji_unicode": "🌊",
    },
    {
        "name":       "REC",
        "role":       "REC",
        "logo_file":  "RECロゴ.png",
        "logo_safe":  "logo_rec.png",
        "color":      0xFF6B35,
        "cid":        "role:rec",
        "emoji_name": "REC",
        "emoji_unicode": "🦩",
    },
    {
        "name":       "やまなび",
        "role":       "やまなび",
        "logo_file":  "やまなびロゴ.png",
        "logo_safe":  "logo_yamanabi.png",
        "color":      0x4CAF50,
        "cid":        "role:yamanabi",
        "emoji_name": "_yamanabi_",
        "emoji_unicode": "🏔️",
    },
    {
        "name":       "Re-Cover",
        "role":       "Re-Cover",
        "logo_file":  "Re-Coverロゴ（Rくん＆Cちゃんver.).jpg",
        "logo_safe":  "logo_recover.jpg",
        "color":      0x9C27B0,
        "cid":        "role:recover",
        "emoji_name": "ReCoverRCver",
        "emoji_unicode": "🌱",
    },
    {
        "name":       "ecoSMILE",
        "role":       "ecoSMILE",
        "logo_file":  "ecoSMILEロゴ.jpeg",
        "logo_safe":  "logo_ecosmile.jpeg",
        "color":      0xFFD700,
        "cid":        "role:ecosmile",
        "emoji_name": "ecoSMILE",
        "emoji_unicode": "😊",
    },
    {
        "name":       "Precious Plastic Waseda",
        "role":       "PPW",
        "logo_file":  "Precious Plastic Waseda ロド.png",
        "logo_safe":  "logo_ppw.png",
        "color":      0xE91E63,
        "cid":        "role:ppw",
        "emoji_name": "PreciousPlasticWaseda",
        "emoji_unicode": "🔷",
    },
]


def get_emoji_str(guild: discord.Guild, ent: dict) -> str:
    """カスタム絵文字があればそれを、なければUnicode絵文字を返す"""
    e = discord.utils.get(guild.emojis, name=ent["emoji_name"])
    return str(e) if e else ent["emoji_unicode"]


# ── ロールトグル共通処理 ──────────────────────────────────────
async def toggle_role(interaction: discord.Interaction, enterprise: str, role_name: str):
    role = discord.utils.get(interaction.guild.roles, name=role_name)
    if not role:
        await interaction.response.send_message(
            f"❌ @{role_name} ロールが見つかりません。幹事に連絡してください。", ephemeral=True
        )
        return

    if role in interaction.user.roles:
        await interaction.user.remove_roles(role)
        await interaction.response.send_message(
            f"**{enterprise}** の参加を解除しました。", ephemeral=True
        )
    else:
        await interaction.user.add_roles(role)
        await interaction.response.send_message(
            f"✅ **{enterprise}** に参加しました！\n"
            f"企画チャンネルとイベントフォーラムが表示されます。",
            ephemeral=True,
        )


# ── 企画カードの永続ビュー（企画ごとに1つ登録） ──────────────
class EnterpriseCardView(discord.ui.View):
    def __init__(self, cid: str, enterprise: str, role_name: str):
        super().__init__(timeout=None)
        self._enterprise = enterprise
        self._role_name  = role_name
        btn = discord.ui.Button(
            label=f"参加 / 解除",
            style=discord.ButtonStyle.primary,
            custom_id=cid,
            emoji="✋",
        )
        btn.callback = self._on_click
        self.add_item(btn)

    async def _on_click(self, interaction: discord.Interaction):
        await toggle_role(interaction, self._enterprise, self._role_name)


# ── 権限チェック ─────────────────────────────────────────────
def is_staff_or_leader():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        names = {r.name for r in interaction.user.roles}
        return '幹事' in names or '企画長' in names
    return app_commands.check(predicate)


# ── Cog ─────────────────────────────────────────────────────
class Roles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 全企画分の永続ビューを起動時に登録
        for ent in ENTERPRISES:
            bot.add_view(EnterpriseCardView(ent["cid"], ent["name"], ent["role"]))

    @app_commands.command(
        name="企画パネル設置",
        description="企画選択パネルを設置します（幹事・企画長のみ）",
    )
    @is_staff_or_leader()
    async def cmd_setup_panel(self, interaction: discord.Interaction):
        ch = discord.utils.get(interaction.guild.text_channels, name=PANEL_CHANNEL)
        if not ch:
            await interaction.response.send_message(
                f"❌ `#{PANEL_CHANNEL}` チャンネルが見つかりません。", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        # ヘッダーメッセージ
        await ch.send(
            "## 所属企画を選んでください\n"
            "参加したい企画のボタンを押すとロールが付与され、"
            "対応する企画チャンネルとイベント情報が表示されます。\n"
            "複数選択OK・押し直しで解除できます。"
        )

        # 企画ごとにカードを投稿
        for ent in ENTERPRISES:
            logo_path   = os.path.join(LOGO_DIR, ent["logo_file"])
            emoji_str   = get_emoji_str(interaction.guild, ent)
            embed = discord.Embed(title=f"{emoji_str} {ent['name']}", color=ent["color"])
            view  = EnterpriseCardView(ent["cid"], ent["name"], ent["role"])

            try:
                file = discord.File(logo_path, filename=ent["logo_safe"])
                embed.set_image(url=f"attachment://{ent['logo_safe']}")
                await ch.send(file=file, embed=embed, view=view)
            except Exception as e:
                print(f"ロゴ送信失敗 ({ent['name']}): {e}", flush=True)
                await ch.send(embed=embed, view=view)

        await interaction.followup.send(
            f"✅ `#{PANEL_CHANNEL}` にパネルを設置しました！", ephemeral=True
        )

    @cmd_setup_panel.error
    async def cmd_setup_panel_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("❌ 幹事・企画長のみ使用できます。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Roles(bot))
