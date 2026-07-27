import discord
from discord.ext import commands
from discord import app_commands
import json, os, re

DATA_FILE   = os.path.join(os.path.dirname(__file__), '..', 'committee_data.json')
RECRUIT_CH  = "実行委員募集"
COMMITTEE_CAT = "実行委員"
GROUP_CH    = "グループ相談"


# ── データ管理 ──────────────────────────────────────────────
def load() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, encoding='utf-8') as f:
        return json.load(f)

def save(data: dict):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── 権限チェック（events.py と同じ） ─────────────────────────
def is_staff_or_leader():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        names = {r.name for r in interaction.user.roles}
        return '幹事' in names or '企画長' in names
    return app_commands.check(predicate)


# ── Embed 生成 ───────────────────────────────────────────────
def build_recruit_embed(data: dict) -> discord.Embed:
    count = len(data.get('applicants', []))
    target = data.get('count')
    status = "🔒 締め切り" if data.get('closed') else "🟢 募集中"

    embed = discord.Embed(
        title=f"🙋 実行委員募集：{data['title']}",
        description=data.get('description', ''),
        color=0xE67E22 if not data.get('closed') else 0x99AAB5,
    )
    cap_str = f"{count} / {target}名" if target else f"{count}名"
    embed.add_field(name="👥 応募者数", value=cap_str, inline=True)
    embed.add_field(name="📌 状態",     value=status,  inline=True)
    embed.set_footer(text="🙋 で応募 ／ 作成者が🔒で締め切り → 専用チャンネルを自動作成")
    return embed


# ── 募集モーダル ─────────────────────────────────────────────
class RecruitModal(discord.ui.Modal, title="実行委員募集を作成"):
    ev_title = discord.ui.TextInput(
        label="タイトル",
        placeholder="例：夏合宿2026 実行委員",
        max_length=80,
    )
    ev_desc = discord.ui.TextInput(
        label="内容・募集要項",
        style=discord.TextStyle.paragraph,
        placeholder="活動内容、必要なスキル、スケジュールなど",
        required=False,
        max_length=800,
    )
    ev_count = discord.ui.TextInput(
        label="募集人数（任意）",
        placeholder="例：5",
        required=False,
        max_length=5,
    )

    async def on_submit(self, interaction: discord.Interaction):
        count = None
        if self.ev_count.value:
            try:
                count = int(self.ev_count.value)
            except ValueError:
                await interaction.response.send_message("募集人数は数字で入力してください。", ephemeral=True)
                return

        data = {
            'title':       self.ev_title.value,
            'description': self.ev_desc.value or '',
            'count':       count,
            'creator_id':  str(interaction.user.id),
            'applicants':  [],
            'closed':      False,
            'channel_id':  None,
        }

        # 実行委員募集チャンネルに投稿
        ch = discord.utils.get(interaction.guild.text_channels, name=RECRUIT_CH)
        if not ch:
            await interaction.response.send_message(
                f"❌ `#{RECRUIT_CH}` チャンネルが見つかりません。", ephemeral=True
            )
            return

        view  = CommitteeView()
        embed = build_recruit_embed(data)
        msg   = await ch.send(embed=embed, view=view)

        all_data = load()
        all_data[str(msg.id)] = data
        save(all_data)

        await interaction.response.send_message(
            f"✅ **{data['title']}** の募集を投稿しました！ → {msg.jump_url}",
            ephemeral=True,
        )


# ── 募集ビュー（永続） ────────────────────────────────────────
class CommitteeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🙋 応募する",     style=discord.ButtonStyle.success,   custom_id="cm:apply")
    async def apply(self, interaction: discord.Interaction, _: discord.ui.Button):
        await _handle_apply(interaction)

    @discord.ui.button(label="🔒 締め切る",     style=discord.ButtonStyle.danger,    custom_id="cm:close")
    async def close(self, interaction: discord.Interaction, _: discord.ui.Button):
        await _handle_close(interaction)

    @discord.ui.button(label="👥 応募者リスト", style=discord.ButtonStyle.secondary, custom_id="cm:list")
    async def list_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await _handle_cm_list(interaction)


async def _handle_apply(interaction: discord.Interaction):
    all_data = load()
    msg_id = str(interaction.message.id)
    data   = all_data.get(msg_id)
    if not data:
        await interaction.response.send_message("❌ データが見つかりません。", ephemeral=True)
        return
    if data.get('closed'):
        await interaction.response.send_message("⏰ 募集は終了しています。", ephemeral=True)
        return

    uid = str(interaction.user.id)
    if uid in data['applicants']:
        # 取り消し
        data['applicants'].remove(uid)
        all_data[msg_id] = data
        save(all_data)
        await interaction.response.edit_message(embed=build_recruit_embed(data))
        await interaction.followup.send("応募を取り消しました。", ephemeral=True)
        return

    data['applicants'].append(uid)
    all_data[msg_id] = data
    save(all_data)
    await interaction.response.edit_message(embed=build_recruit_embed(data))
    await interaction.followup.send("🙋 応募しました！締め切り後に専用チャンネルへ招待されます。", ephemeral=True)


async def _handle_close(interaction: discord.Interaction):
    # 権限チェック（作成者 or 幹事・企画長）
    names = {r.name for r in interaction.user.roles}
    is_staff = '幹事' in names or '企画長' in names

    all_data = load()
    msg_id = str(interaction.message.id)
    data   = all_data.get(msg_id)
    if not data:
        await interaction.response.send_message("❌ データが見つかりません。", ephemeral=True)
        return
    if data.get('closed'):
        await interaction.response.send_message("すでに締め切り済みです。", ephemeral=True)
        return

    is_creator = str(interaction.user.id) == data.get('creator_id')
    if not (is_staff or is_creator):
        await interaction.response.send_message("❌ 作成者・幹事・企画長のみ締め切れます。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    data['closed'] = True
    all_data[msg_id] = data
    save(all_data)

    # 実行委員チャンネル作成
    ch = await _create_committee_channel(interaction.guild, data)
    data['channel_id'] = ch.id
    all_data[msg_id]   = data
    save(all_data)

    # 元メッセージのEmbedを更新
    await interaction.message.edit(embed=build_recruit_embed(data), view=None)
    await interaction.followup.send(
        f"✅ 締め切りました。専用チャンネル {ch.mention} を作成しました！", ephemeral=True
    )


async def _handle_cm_list(interaction: discord.Interaction):
    all_data = load()
    msg_id = str(interaction.message.id)
    data   = all_data.get(msg_id)
    if not data:
        await interaction.response.send_message("❌ データが見つかりません。", ephemeral=True)
        return

    applicants = data.get('applicants', [])
    if not applicants:
        await interaction.response.send_message("まだ応募者がいません。", ephemeral=True)
        return

    lines = [f"**{data['title']}** 応募者リスト（{len(applicants)}名）\n"]
    for uid in applicants:
        mb = interaction.guild.get_member(int(uid))
        lines.append(f"• {mb.display_name if mb else f'<@{uid}>'}")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


async def _create_committee_channel(guild: discord.Guild, data: dict) -> discord.TextChannel:
    """実行委員専用チャンネルを作成して全応募者を追加"""
    category = discord.utils.get(guild.categories, name=COMMITTEE_CAT)
    kanji    = discord.utils.get(guild.roles, name='幹事')

    safe_name = re.sub(r'[\s　]', '-', data['title'])[:20]
    ch_name   = f"実委-{safe_name}"

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
    }
    if kanji:
        overwrites[kanji] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    ch = await guild.create_text_channel(
        name=ch_name,
        category=category,
        overwrites=overwrites,
    )

    # 作成者 + 応募者全員を追加
    members_to_add = set(data.get('applicants', []))
    members_to_add.add(data['creator_id'])

    mention_parts = []
    for uid in members_to_add:
        mb = guild.get_member(int(uid))
        if mb:
            await ch.set_permissions(mb, view_channel=True, send_messages=True)
            mention_parts.append(mb.mention)

    # ウェルカムメッセージ
    await ch.send(
        f"**{data['title']}** 実行委員チャンネルを開設しました！\n"
        f"メンバー: {' '.join(mention_parts)}\n\n"
        f"よろしくお願いします！ 🎉"
    )
    return ch


# ── グループ相談コマンド ──────────────────────────────────────
class Committee(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(CommitteeView())

    # ── /実行委員募集 ─────────────────────────────────────────
    @app_commands.command(name="実行委員募集", description="実行委員の募集を開始します（幹事・企画長のみ）")
    @is_staff_or_leader()
    async def cmd_recruit(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RecruitModal())

    @cmd_recruit.error
    async def cmd_recruit_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("❌ 幹事・企画長のみ使用できます。", ephemeral=True)

    # ── /グループ作成 ─────────────────────────────────────────
    @app_commands.command(name="グループ作成", description="プライベートグループ（相談用スレッド）を作成します")
    @app_commands.describe(name="グループ名")
    @app_commands.rename(name="グループ名")
    async def cmd_group_create(self, interaction: discord.Interaction, name: str):
        ch = discord.utils.get(interaction.guild.text_channels, name=GROUP_CH)
        if not ch:
            await interaction.response.send_message(
                f"❌ `#{GROUP_CH}` チャンネルが見つかりません。", ephemeral=True
            )
            return

        thread = await ch.create_thread(
            name=name[:100],
            type=discord.ChannelType.private_thread,
            invitable=True,  # スレッドメンバーが他のメンバーを追加できる
        )
        await thread.add_user(interaction.user)

        await interaction.response.send_message(
            f"✅ プライベートグループ「**{name}**」を作成しました！\n"
            f"→ {thread.mention}\n\n"
            f"メンバーを追加するには `/グループ追加 @ユーザー名` をスレッド内で使ってください。",
            ephemeral=True,
        )

    # ── /グループ追加 ─────────────────────────────────────────
    @app_commands.command(name="グループ追加", description="現在のプライベートグループにメンバーを追加します（グループ内で使用）")
    @app_commands.describe(user="追加するメンバー")
    @app_commands.rename(user="メンバー")
    async def cmd_group_add(self, interaction: discord.Interaction, user: discord.Member):
        ch = interaction.channel
        if not isinstance(ch, discord.Thread) or ch.type != discord.ChannelType.private_thread:
            await interaction.response.send_message(
                "このコマンドはプライベートグループ（スレッド）内でのみ使用できます。", ephemeral=True
            )
            return
        await ch.add_user(user)
        await interaction.response.send_message(f"✅ **{user.display_name}** を追加しました！", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Committee(bot))
