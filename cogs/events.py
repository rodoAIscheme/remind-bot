import discord
from discord.ext import commands, tasks
from discord import app_commands
import json, os, re, traceback
from datetime import datetime

import storage

# ── 企画定義 ────────────────────────────────────────────────
ENTERPRISES = [
    "うみさんぽ",
    "REC",
    "やまなび",
    "Re-Cover",
    "ecoSMILE",
    "Precious Plastic Waseda",
    "全体",
]

ENTERPRISE_ROLE = {
    "うみさんぽ":              "うみさんぽ",
    "REC":                   "REC",
    "やまなび":               "やまなび",
    "Re-Cover":              "Re-Cover",
    "ecoSMILE":              "ecoSMILE",
    "Precious Plastic Waseda": "PPW",
    "全体":                   None,
}

ENTERPRISE_TAG = {
    "うみさんぽ":              "うみさんぽ",
    "REC":                   "REC",
    "やまなび":               "やまなび",
    "Re-Cover":              "Re-Cover",
    "ecoSMILE":              "ecoSMILE",
    "Precious Plastic Waseda": "PPW",
    "全体":                   "全体",
}

ENTERPRISE_COLOR = {
    "うみさんぽ":              0x1E90FF,
    "REC":                   0xFF6B35,
    "やまなび":               0x4CAF50,
    "Re-Cover":              0x9C27B0,
    "ecoSMILE":              0xFFD700,
    "Precious Plastic Waseda": 0xE91E63,
    "全体":                   0x607D8B,
}

# チャンネル名プレフィックス用 Unicode 絵文字（チャンネル名にはカスタム絵文字不可）
ENTERPRISE_EMOJI = {
    "うみさんぽ":              "🌊",
    "REC":                   "🦩",
    "やまなび":               "🏔️",
    "Re-Cover":              "🌱",
    "ecoSMILE":              "😊",
    "Precious Plastic Waseda": "🔷",
    "全体":                   "📢",
}

# 企画 → 企画テキストチャンネル名（通知先）
ENTERPRISE_CH = {
    "うみさんぽ":              "うみさんぽ",
    "REC":                   "rec",
    "やまなび":               "やまなび",
    "Re-Cover":              "re-cover",
    "ecoSMILE":              "ecosmile",
    "Precious Plastic Waseda": "precious-plastic",
    "全体":                   "全体連絡",
}

# サーバーに登録したカスタム絵文字名（メッセージ・Embed内で使用）
ENTERPRISE_CUSTOM_EMOJI = {
    "うみさんぽ":              "_umisanpo_",
    "REC":                   "REC",
    "やまなび":               "_yamanabi_",
    "Re-Cover":              "ReCoverRCver",
    "ecoSMILE":              "ecoSMILE",
    "Precious Plastic Waseda": "PreciousPlasticWaseda",
    "全体":                   None,
}


def get_enterprise_emoji(guild: discord.Guild, enterprise: str) -> str:
    """カスタム絵文字があればそれを、なければUnicode絵文字を返す"""
    custom_name = ENTERPRISE_CUSTOM_EMOJI.get(enterprise)
    if custom_name:
        e = discord.utils.get(guild.emojis, name=custom_name)
        if e:
            return str(e)
    return ENTERPRISE_EMOJI.get(enterprise, "📋")

ENTERPRISE_FORUM = {
    "うみさんぽ":              "うみさんぽ-イベント",
    "REC":                   "rec-イベント",
    "やまなび":               "やまなび-イベント",
    "Re-Cover":              "re-cover-イベント",
    "ecoSMILE":              "ecosmile-イベント",
    "Precious Plastic Waseda": "ppw-イベント",
    "全体":                   "全体-イベント",
}

# 参加者チャンネルを置くカテゴリ名
EVENT_CH_CATEGORY = "イベント"


# ── データ管理 ──────────────────────────────────────────────
def load_data() -> dict:
    return storage.load('events', {})

def save_data(data: dict):
    storage.save('events', data)

def parse_dt(text: str) -> datetime | None:
    patterns = [
        (r'(\d{4})[/\-年](\d{1,2})[/\-月](\d{1,2})[日\s]*(\d{1,2}):(\d{2})', 5),
        (r'(\d{4})[/\-年](\d{1,2})[/\-月](\d{1,2})',                           3),
        (r'(\d{1,2})[/\-](\d{1,2})[日\s]*(\d{1,2}):(\d{2})',                  4),
        (r'(\d{1,2})[/\-](\d{1,2})',                                            2),
    ]
    now = datetime.now()
    for pat, n in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        try:
            if n == 5: return datetime(g[0], g[1], g[2], g[3], g[4])
            if n == 3: return datetime(g[0], g[1], g[2])
            if n == 4: return datetime(now.year, g[0], g[1], g[2], g[3])
            if n == 2: return datetime(now.year, g[0], g[1])
        except ValueError:
            pass
    return None


# ── 権限チェック ────────────────────────────────────────────
def is_staff_or_leader():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        names = {r.name for r in interaction.user.roles}
        return '幹事' in names or '企画長' in names
    return app_commands.check(predicate)


# ── チャンネル名サニタイズ ───────────────────────────────────
def sanitize_channel_name(name: str) -> str:
    # 日本語・絵文字・英数字・ハイフン・アンダースコア以外をハイフンに置換
    result = re.sub(r'[^\w　-鿿\-]', '-', name, flags=re.UNICODE)
    result = re.sub(r'\-+', '-', result).strip('-')
    return (result or 'event')[:80]


# ── イベント参加チャンネル作成 ───────────────────────────────
async def create_event_channel(guild: discord.Guild, ev_data: dict) -> discord.TextChannel:
    # カテゴリを取得 or 作成
    cat = discord.utils.get(guild.categories, name=EVENT_CH_CATEGORY)
    if cat is None:
        cat = await guild.create_category(EVENT_CH_CATEGORY)

    enterprise = ev_data['enterprise']
    emoji      = ENTERPRISE_EMOJI.get(enterprise, '📋')
    safe_name  = sanitize_channel_name(ev_data['name'])
    ch_name    = f"{emoji}{safe_name}"

    # @everyone は閲覧禁止、幹事・企画長は閲覧可
    # Bot 自身も明示的に許可しないと、作成直後に自分のチャンネルへ
    # アクセスできなくなり set_permissions が Missing Access で失敗する
    overwrites: dict = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
            manage_permissions=True,
        ),
    }
    for role_name in ('幹事', '企画長'):
        role = discord.utils.get(guild.roles, name=role_name)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

    ch = await guild.create_text_channel(ch_name, category=cat, overwrites=overwrites)
    await ch.edit(position=0)
    return ch


# ── Embed 生成 ───────────────────────────────────────────────
def build_event_embed(ev: dict, guild: discord.Guild | None = None) -> discord.Embed:
    enterprise = ev.get('enterprise', '全体')
    color      = ENTERPRISE_COLOR.get(enterprise, 0x5865F2)
    emoji      = get_enterprise_emoji(guild, enterprise) if guild else ENTERPRISE_EMOJI.get(enterprise, "📋")
    embed = discord.Embed(title=f"{emoji} {ev['name']}", color=color)
    embed.add_field(name="🏷️ 企画",  value=enterprise,           inline=True)
    embed.add_field(name="📅 日時",  value=ev.get('date', '未定'), inline=True)
    if ev.get('location'):
        embed.add_field(name="📍 場所", value=ev['location'], inline=True)
    if ev.get('description'):
        embed.add_field(name="📝 内容", value=ev['description'], inline=False)
    if ev.get('cap_deadline'):
        embed.add_field(name="📌 定員・締切", value=ev['cap_deadline'], inline=False)

    count  = len(ev.get('participants', []))
    status = f"{count}名が参加予定" if count else "まだいません"
    embed.add_field(name=f"👥 参加者（{count}名）", value=status, inline=False)

    if ev.get('channel_id'):
        embed.add_field(
            name="💬 参加チャンネル",
            value=f"<#{ev['channel_id']}>\n参加登録後に表示されます",
            inline=False,
        )

    if ev.get('closed'):
        embed.set_footer(text="⏰ 受付終了")
    else:
        embed.set_footer(text="✅ で参加登録 ／ ❌ でキャンセル ／ ✏️ で編集")
    return embed

def build_mtg_embed(mtg: dict, guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title=f"🗓️ {mtg['title']}",
        description=mtg.get('description', ''),
        color=0x5865F2,
    )
    embed.add_field(name="📅 日時", value=mtg.get('date', '未定'), inline=True)
    embed.add_field(name="📍 場所", value=mtg.get('location', '未定'), inline=True)

    def _names(ids: list) -> str:
        names = []
        for uid in ids:
            m = guild.get_member(int(uid))
            names.append(m.display_name if m else f"<@{uid}>")
        return ", ".join(names) if names else "なし"

    a = mtg.get('attending', [])
    b = mtg.get('absent',    [])
    c = mtg.get('maybe',     [])
    embed.add_field(name=f"✅ 参加（{len(a)}名）", value=_names(a), inline=False)
    embed.add_field(name=f"❌ 欠席（{len(b)}名）", value=_names(b), inline=False)
    embed.add_field(name=f"🤔 未定（{len(c)}名）", value=_names(c), inline=False)
    embed.set_footer(text="ボタンで出欠を登録（押し直しで変更可）")
    return embed


# ── フォーラムタグを取得or作成 ──────────────────────────────
async def get_or_create_tag(forum: discord.ForumChannel, name: str) -> discord.ForumTag | None:
    for tag in forum.available_tags:
        if tag.name == name:
            return tag
    try:
        new_list = list(forum.available_tags) + [discord.ForumTag(name=name)]
        updated = await forum.edit(available_tags=new_list)
        for tag in updated.available_tags:
            if tag.name == name:
                return tag
    except Exception as e:
        print(f"タグ作成失敗: {e}", flush=True)
    return None


# ── イベント投稿を作成 ───────────────────────────────────────
async def create_event_post(interaction: discord.Interaction, ev_data: dict):
    guild      = interaction.guild
    enterprise = ev_data['enterprise']

    # 1. 参加者チャンネルを先に作成
    try:
        event_ch = await create_event_channel(guild, ev_data)
    except Exception as e:
        await interaction.followup.send(f"❌ チャンネル作成失敗: {e}", ephemeral=True)
        return
    ev_data['channel_id'] = str(event_ch.id)

    # 作成者に閲覧権限を付与
    await event_ch.set_permissions(
        interaction.user,
        view_channel=True,
        read_message_history=True,
        send_messages=True,
    )

    # 2. フォーラムスレッドに投稿
    forum_name = ENTERPRISE_FORUM.get(enterprise, "全体-イベント")
    forum = discord.utils.get(guild.forums, name=forum_name)
    if not forum:
        await event_ch.delete()
        await interaction.followup.send(f"❌ `#{forum_name}` が見つかりません。", ephemeral=True)
        return

    tag_name     = ENTERPRISE_TAG.get(enterprise, enterprise[:20])
    tag          = await get_or_create_tag(forum, tag_name)
    applied_tags = [tag] if tag else []

    role_name = ENTERPRISE_ROLE.get(enterprise)
    if role_name:
        role    = discord.utils.get(guild.roles, name=role_name)
        mention = role.mention if role else f"@{role_name}"
    else:
        mention = "@everyone"

    view  = EventView()
    embed = build_event_embed(ev_data, guild)

    thread, msg = await forum.create_thread(
        name=ev_data['name'],
        content=(
            f"{mention} 新しいイベントのお知らせです！\n"
            f"✅ で参加登録すると {event_ch.mention} が表示されます。"
        ),
        embed=embed,
        applied_tags=applied_tags,
        view=view,
    )

    all_data = load_data()
    all_data[str(msg.id)] = {
        **ev_data,
        'creator_id': str(interaction.user.id),
        'thread_id':  str(thread.id),
        'msg_id':     str(msg.id),
        'channel_id': str(event_ch.id),
        'participants': [],
        'reminders':  [],
        'closed':     False,
        'created_at': datetime.now().isoformat(),
    }
    save_data(all_data)

    # 企画テキストチャンネルに通知（メッセージIDを保存して後で削除できるように）
    ch_name = ENTERPRISE_CH.get(enterprise)
    if ch_name:
        notify_ch = discord.utils.get(guild.text_channels, name=ch_name)
        if notify_ch:
            emoji = get_enterprise_emoji(guild, enterprise)
            try:
                notify_msg = await notify_ch.send(
                    f"{emoji} **新しいイベントが募集されました！**\n"
                    f"**{ev_data['name']}** ／ 📅 {ev_data.get('date', '未定')}\n"
                    f"[詳細・参加登録はこちら]({msg.jump_url})"
                )
                all_data[str(msg.id)]['notify_msg_id'] = str(notify_msg.id)
                all_data[str(msg.id)]['notify_ch_name'] = ch_name
                save_data(all_data)
            except Exception as e:
                print(f"企画チャンネル通知失敗: {e}", flush=True)

    await interaction.followup.send(
        f"✅ **{ev_data['name']}** を投稿しました！\n"
        f"[フォーラムを見る]({msg.jump_url})\n"
        f"参加チャンネル: {event_ch.mention}\n\n"
        f"リマインドは `/リマインド設定 {msg.id}` で設定できます。",
        ephemeral=True,
    )


# ── イベント投稿を更新（編集後） ─────────────────────────────
async def update_event_post(interaction: discord.Interaction, event_id: str, new_data: dict):
    all_data = load_data()
    ev = all_data.get(event_id)
    if not ev:
        await interaction.followup.send("❌ イベントが見つかりません。", ephemeral=True)
        return

    keep_fields = ('creator_id', 'thread_id', 'msg_id', 'channel_id',
                   'participants', 'reminders', 'closed', 'created_at')
    for k in keep_fields:
        new_data[k] = ev.get(k)
    all_data[event_id] = new_data
    save_data(all_data)

    try:
        thread = interaction.guild.get_thread(int(ev['thread_id']))
        if thread is None:
            thread = await interaction.guild.fetch_channel(int(ev['thread_id']))
        async for msg in thread.history(limit=1, oldest_first=True):
            await msg.edit(embed=build_event_embed(new_data, interaction.guild))
            break
        await interaction.followup.send("✅ イベント情報を更新しました！", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ メッセージ更新失敗: {e}", ephemeral=True)


# ── ステップ1: 企画選択UI ─────────────────────────────────────
class EnterpriseSelect(discord.ui.Select):
    def __init__(self):
        opts = [discord.SelectOption(label=e, value=e) for e in ENTERPRISES]
        super().__init__(placeholder="どの企画のイベントですか？", options=opts)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected = self.values[0]
        await interaction.response.edit_message(
            content=f"**企画：{self.values[0]}**\n\n内容を入力するにはボタンを押してください。",
            view=self.view,
        )

class EnterpriseSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.selected: str | None = None
        self.add_item(EnterpriseSelect())

    @discord.ui.button(label="フォームへ進む →", style=discord.ButtonStyle.primary, emoji="📝")
    async def open_form(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected:
            await interaction.response.send_message("先に企画を選択してください。", ephemeral=True)
            return
        await interaction.response.send_modal(EventModal(enterprise=self.selected))


# ── ステップ2: イベント作成/編集モーダル ──────────────────────
class EventModal(discord.ui.Modal):
    def __init__(self, enterprise: str, event_id: str | None = None, defaults: dict | None = None):
        super().__init__(title=f"イベント作成「{enterprise[:15]}」")
        self.enterprise = enterprise
        self.event_id   = event_id
        d = defaults or {}

        self.ev_name = discord.ui.TextInput(
            label="イベント名",
            placeholder="例：江ノ島うみさんぽ",
            max_length=100,
            default=d.get('name', ''),
        )
        self.ev_date = discord.ui.TextInput(
            label="日時",
            placeholder="例：2026/8/10（日）10:00 集合",
            max_length=100,
            default=d.get('date', ''),
        )
        self.ev_location = discord.ui.TextInput(
            label="場所（任意）",
            placeholder="例：江ノ島駅 改札前",
            required=False,
            max_length=100,
            default=d.get('location', ''),
        )
        self.ev_desc = discord.ui.TextInput(
            label="内容・説明（任意）",
            style=discord.TextStyle.paragraph,
            placeholder="活動内容・持ち物・注意事項など",
            required=False,
            max_length=800,
            default=d.get('description', ''),
        )
        self.ev_cap = discord.ui.TextInput(
            label="定員・締切（任意）",
            placeholder="例：定員15名 ／ 参加締切 8/7（水）",
            required=False,
            max_length=100,
            default=d.get('cap_deadline', ''),
        )
        for item in (self.ev_name, self.ev_date, self.ev_location, self.ev_desc, self.ev_cap):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        ev_data = {
            'name':        self.ev_name.value,
            'date':        self.ev_date.value,
            'location':    self.ev_location.value or '',
            'description': self.ev_desc.value    or '',
            'cap_deadline': self.ev_cap.value     or '',
            'enterprise':  self.enterprise,
        }
        if self.event_id:
            await update_event_post(interaction, self.event_id, ev_data)
        else:
            await create_event_post(interaction, ev_data)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item=None):
        # defer 済みで例外が出ると「考え中...」のまま固まるため、必ず理由を返す
        traceback.print_exception(type(error), error, error.__traceback__)
        msg = f"❌ 処理に失敗しました: {type(error).__name__}: {error}"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except discord.HTTPException:
            pass


# ── イベント投稿上のボタン（永続） ───────────────────────────
class EventView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ 参加する",    style=discord.ButtonStyle.success,   custom_id="ev:join")
    async def btn_join(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_join(interaction)

    @discord.ui.button(label="❌ キャンセル",  style=discord.ButtonStyle.secondary, custom_id="ev:cancel")
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_cancel(interaction)

    @discord.ui.button(label="✏️ 編集",        style=discord.ButtonStyle.primary,   custom_id="ev:edit")
    async def btn_edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_edit(interaction)

    @discord.ui.button(label="👥 参加者リスト", style=discord.ButtonStyle.secondary, custom_id="ev:list")
    async def btn_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_list(interaction)

    @discord.ui.button(label="⏰ リマインド設定", style=discord.ButtonStyle.secondary, custom_id="ev:remind")
    async def btn_remind(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_remind(interaction)

    @discord.ui.button(label="🗑️ 募集取り消し", style=discord.ButtonStyle.danger, custom_id="ev:delete")
    async def btn_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_delete_event(interaction)


# ── 削除確認ビュー（非永続・ephemeral） ──────────────────────
class CancelEventConfirmView(discord.ui.View):
    def __init__(self, eid: str, ev: dict):
        super().__init__(timeout=60)
        self.eid = eid
        self.ev  = ev

    @discord.ui.button(label="削除する", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="🗑️ 削除中...", view=None)
        await _do_delete_event(interaction, self.eid, self.ev)

    @discord.ui.button(label="やっぱりやめる", style=discord.ButtonStyle.secondary)
    async def abort(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="キャンセルしました。", view=None)
        self.stop()


def _find_event_by_thread(all_data: dict, thread_id: str) -> tuple[str | None, dict | None]:
    for eid, ev in all_data.items():
        if isinstance(ev, dict) and ev.get('thread_id') == thread_id:
            return eid, ev
    return None, None


async def _handle_join(interaction: discord.Interaction):
    all_data = load_data()
    eid, ev = _find_event_by_thread(all_data, str(interaction.channel_id))
    if not ev:
        await interaction.response.send_message("❌ イベントデータが見つかりません。", ephemeral=True)
        return
    if ev.get('closed'):
        await interaction.response.send_message("⏰ 受付は終了しています。", ephemeral=True)
        return

    uid   = str(interaction.user.id)
    parts = ev.setdefault('participants', [])
    if uid in parts:
        await interaction.response.send_message(
            "すでに参加登録済みです。❌ボタンでキャンセルできます。", ephemeral=True
        )
        return

    cap_text = ev.get('cap_deadline', '')
    m = re.search(r'定員\s*(\d+)', cap_text)
    if m and len(parts) >= int(m.group(1)):
        await interaction.response.send_message("🈵 定員に達しています。", ephemeral=True)
        return

    parts.append(uid)
    all_data[eid] = ev
    save_data(all_data)

    # 参加者チャンネルの閲覧権限を付与
    channel_msg = ""
    channel_id  = ev.get('channel_id')
    if channel_id:
        ch = interaction.guild.get_channel(int(channel_id))
        if ch:
            try:
                await ch.set_permissions(
                    interaction.user,
                    view_channel=True,
                    read_message_history=True,
                    send_messages=True,
                )
                channel_msg = f"\n{ch.mention} が表示されるようになりました！"
            except Exception as e:
                print(f"チャンネル権限付与失敗: {e}", flush=True)

    await interaction.response.edit_message(embed=build_event_embed(ev, interaction.guild))
    await interaction.followup.send(
        f"✅ **{ev['name']}** への参加登録が完了しました！{channel_msg}", ephemeral=True
    )


async def _handle_cancel(interaction: discord.Interaction):
    all_data = load_data()
    eid, ev = _find_event_by_thread(all_data, str(interaction.channel_id))
    if not ev:
        await interaction.response.send_message("❌ イベントデータが見つかりません。", ephemeral=True)
        return

    uid   = str(interaction.user.id)
    parts = ev.get('participants', [])
    if uid not in parts:
        await interaction.response.send_message("参加登録されていません。", ephemeral=True)
        return

    parts.remove(uid)
    all_data[eid] = ev
    save_data(all_data)

    # 参加者チャンネルの閲覧権限を剥奪
    channel_id = ev.get('channel_id')
    if channel_id:
        ch = interaction.guild.get_channel(int(channel_id))
        if ch:
            try:
                await ch.set_permissions(interaction.user, overwrite=None)
            except Exception as e:
                print(f"チャンネル権限削除失敗: {e}", flush=True)

    await interaction.response.edit_message(embed=build_event_embed(ev, interaction.guild))
    await interaction.followup.send("参加をキャンセルしました。", ephemeral=True)


async def _handle_edit(interaction: discord.Interaction):
    names    = {r.name for r in interaction.user.roles}
    is_staff = '幹事' in names or '企画長' in names

    all_data = load_data()
    eid, ev  = _find_event_by_thread(all_data, str(interaction.channel_id))
    if not ev:
        await interaction.response.send_message("❌ イベントデータが見つかりません。", ephemeral=True)
        return

    is_creator = str(interaction.user.id) == ev.get('creator_id')
    if not (is_staff or is_creator):
        await interaction.response.send_message(
            "❌ 編集できるのは幹事・企画長・作成者のみです。", ephemeral=True
        )
        return

    await interaction.response.send_modal(
        EventModal(enterprise=ev['enterprise'], event_id=eid, defaults=ev)
    )


async def _handle_list(interaction: discord.Interaction):
    all_data = load_data()
    _, ev    = _find_event_by_thread(all_data, str(interaction.channel_id))
    if not ev:
        await interaction.response.send_message("❌ イベントデータが見つかりません。", ephemeral=True)
        return

    parts = ev.get('participants', [])
    if not parts:
        await interaction.response.send_message("まだ参加者がいません。", ephemeral=True)
        return

    lines = [f"**{ev['name']}** 参加者リスト（{len(parts)}名）\n"]
    for uid in parts:
        mb = interaction.guild.get_member(int(uid))
        lines.append(f"• {mb.display_name if mb else f'<@{uid}>'}")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


async def _handle_remind(interaction: discord.Interaction):
    names    = {r.name for r in interaction.user.roles}
    is_staff = '幹事' in names or '企画長' in names

    all_data = load_data()
    eid, ev  = _find_event_by_thread(all_data, str(interaction.channel_id))
    if not ev:
        await interaction.response.send_message("❌ イベントデータが見つかりません。", ephemeral=True)
        return

    is_creator = str(interaction.user.id) == ev.get('creator_id')
    if not (is_staff or is_creator):
        await interaction.response.send_message(
            "❌ リマインド設定できるのは幹事・企画長・作成者のみです。", ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"⏰ **{ev['name']}** のリマインド管理",
        view=ReminderMenuView(eid, ev),
        ephemeral=True,
    )


class ReminderMenuView(discord.ui.View):
    def __init__(self, eid: str, ev: dict):
        super().__init__(timeout=60)
        self.eid = eid
        self.ev  = ev

    @discord.ui.button(label="📝 新規作成", style=discord.ButtonStyle.primary)
    async def btn_create(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReminderModal(event_id=self.eid))

    @discord.ui.button(label="📋 確認", style=discord.ButtonStyle.secondary)
    async def btn_view(self, interaction: discord.Interaction, button: discord.ui.Button):
        all_data = load_data()
        ev = all_data.get(self.eid, self.ev)
        reminders = ev.get('reminders', [])
        if not reminders:
            await interaction.response.edit_message(content="リマインドはまだ設定されていません。", view=self)
            return

        lines = ["**設定中のリマインド一覧**\n"]
        for i, r in enumerate(reminders, 1):
            status = "✅ 送信済" if r.get('sent') else "⏳ 未送信"
            msg    = f"「{r['message']}」" if r.get('message') else ""
            lines.append(f"{i}. {r['time'][:16]}  {status}  {msg}")
        await interaction.response.edit_message(content="\n".join(lines), view=self)

    @discord.ui.button(label="📢 今すぐ送信", style=discord.ButtonStyle.success)
    async def btn_instant(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(InstantReminderModal(self.eid, self.ev))

    @discord.ui.button(label="🗑️ 未送信を全削除", style=discord.ButtonStyle.danger)
    async def btn_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        all_data = load_data()
        ev = all_data.get(self.eid)
        if not ev:
            await interaction.response.edit_message(content="❌ イベントが見つかりません。", view=None)
            return

        before = len(ev.get('reminders', []))
        ev['reminders'] = [r for r in ev.get('reminders', []) if r.get('sent')]
        deleted = before - len(ev['reminders'])
        all_data[self.eid] = ev
        save_data(all_data)

        if deleted:
            await interaction.response.edit_message(
                content=f"🗑️ 未送信のリマインドを {deleted} 件削除しました。", view=None
            )
        else:
            await interaction.response.edit_message(
                content="削除できる未送信のリマインドがありません。", view=self
            )


class InstantReminderModal(discord.ui.Modal, title="今すぐ送信"):
    msg_text = discord.ui.TextInput(
        label="メッセージ",
        placeholder="例：参加締め切りは本日23:59です！まだの方はお早めに！",
        style=discord.TextStyle.paragraph,
        max_length=300,
    )

    def __init__(self, eid: str, ev: dict):
        super().__init__()
        self.eid = eid
        self.ev  = ev

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        ev         = load_data().get(self.eid, self.ev)
        enterprise = ev.get('enterprise', '全体')
        guild      = interaction.guild
        ch_name    = ENTERPRISE_CH.get(enterprise)
        ch         = discord.utils.get(guild.text_channels, name=ch_name) if ch_name else None

        if not ch:
            await interaction.followup.send("❌ 送信先チャンネルが見つかりません。", ephemeral=True)
            return

        role_name = ENTERPRISE_ROLE.get(enterprise)
        if role_name:
            role    = discord.utils.get(guild.roles, name=role_name)
            mention = role.mention if role else f"@{role_name}"
        else:
            mention = "@everyone"

        thread_id = ev.get('thread_id')
        msg_id    = ev.get('msg_id')
        jump_url  = f"https://discord.com/channels/{guild.id}/{thread_id}/{msg_id}" \
                    if thread_id and msg_id else ""
        link_text = f"\n[詳細・参加登録はこちら]({jump_url})" if jump_url else ""

        body = (
            f"⏰ **{ev.get('name', '')}**\n"
            f"📅 {ev.get('date', '日時未定')}\n"
            f"{self.msg_text.value}"
        )
        await ch.send(f"{mention}\n{body}{link_text}")
        await interaction.followup.send(f"✅ {ch.mention} に送信しました！", ephemeral=True)


async def _handle_delete_event(interaction: discord.Interaction):
    names    = {r.name for r in interaction.user.roles}
    is_staff = '幹事' in names or '企画長' in names

    all_data = load_data()
    eid, ev  = _find_event_by_thread(all_data, str(interaction.channel_id))
    if not ev:
        await interaction.response.send_message("❌ イベントデータが見つかりません。", ephemeral=True)
        return

    is_creator = str(interaction.user.id) == ev.get('creator_id')
    if not (is_staff or is_creator):
        await interaction.response.send_message(
            "❌ 削除できるのは幹事・企画長・作成者のみです。", ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"⚠️ **{ev['name']}** の募集を取り消しますか？\n"
        "フォーラム投稿・参加チャンネル・企画チャンネルの告知がすべて削除されます。",
        view=CancelEventConfirmView(eid, ev),
        ephemeral=True,
    )


async def _do_delete_event(interaction: discord.Interaction, eid: str, ev: dict):
    guild  = interaction.guild
    errors = []

    # 1. 企画チャンネルの告知メッセージを削除
    notify_msg_id  = ev.get('notify_msg_id')
    notify_ch_name = ev.get('notify_ch_name')
    if notify_msg_id and notify_ch_name:
        notify_ch = discord.utils.get(guild.text_channels, name=notify_ch_name)
        if notify_ch:
            try:
                notify_msg = await notify_ch.fetch_message(int(notify_msg_id))
                await notify_msg.delete()
            except Exception as e:
                errors.append(f"告知削除失敗: {e}")

    # 2. 参加者チャンネルを削除
    channel_id = ev.get('channel_id')
    if channel_id:
        ch = guild.get_channel(int(channel_id))
        if ch:
            try:
                await ch.delete()
            except Exception as e:
                errors.append(f"チャンネル削除失敗: {e}")

    # 3. JSONから削除
    all_data = load_data()
    all_data.pop(eid, None)
    save_data(all_data)

    # 4. フォーラムスレッドを削除（最後に実行）
    thread_id = ev.get('thread_id')
    if thread_id:
        try:
            thread = guild.get_thread(int(thread_id)) \
                     or await guild.fetch_channel(int(thread_id))
            await thread.delete()
        except Exception as e:
            errors.append(f"スレッド削除失敗: {e}")

    result = "✅ 募集を取り消しました。" if not errors else \
             "⚠️ 一部削除できませんでした:\n" + "\n".join(errors)
    try:
        await interaction.edit_original_response(content=result)
    except Exception:
        pass


# ── リマインドモーダル ────────────────────────────────────────
class ReminderModal(discord.ui.Modal, title="締め切りリマインド設定"):
    r1 = discord.ui.TextInput(
        label="通知日時1",
        placeholder="例：2026/8/9 10:00 または 8/9",
    )
    r2 = discord.ui.TextInput(label="通知日時2（任意）", required=False,
                               placeholder="例：締切3日前 → 2026/8/7")
    r3 = discord.ui.TextInput(label="通知日時3（任意）", required=False,
                               placeholder="例：締切前日 → 2026/8/9")
    msg_text = discord.ui.TextInput(
        label="メッセージ（任意）",
        placeholder="例：参加締め切りは明日です！まだの方はお早めに！",
        required=False, max_length=200,
    )

    def __init__(self, event_id: str):
        super().__init__()
        self.event_id = event_id

    async def on_submit(self, interaction: discord.Interaction):
        all_data = load_data()
        ev = all_data.get(self.event_id)
        if not ev:
            await interaction.response.send_message("❌ イベントが見つかりません。", ephemeral=True)
            return

        message      = self.msg_text.value or None
        new_reminders = []
        errors        = []
        for val in [self.r1.value, self.r2.value, self.r3.value]:
            if not val:
                continue
            dt = parse_dt(val)
            if dt:
                new_reminders.append({'time': dt.isoformat(), 'message': message, 'sent': False})
            else:
                errors.append(val)

        if errors:
            await interaction.response.send_message(
                f"⚠️ 以下の日時を解析できませんでした: {', '.join(errors)}\n"
                "形式: `2026/8/9 10:00` または `8/9`",
                ephemeral=True,
            )
            return

        ev.setdefault('reminders', []).extend(new_reminders)
        all_data[self.event_id] = ev
        save_data(all_data)

        lines = [f"✅ {len(new_reminders)}件のリマインドを設定しました"]
        for r in new_reminders:
            lines.append(f"  • {r['time']}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


# ── MTG 出欠確認 ─────────────────────────────────────────────
class MTGModal(discord.ui.Modal, title="MTG 出欠確認を作成"):
    mtg_title = discord.ui.TextInput(label="タイトル", placeholder="例：うみさんぽ 定例MTG", max_length=80)
    mtg_date  = discord.ui.TextInput(label="日時",     placeholder="例：毎週水曜 19:00〜")
    mtg_place = discord.ui.TextInput(label="場所（任意）", required=False,
                                      placeholder="例：55号館401 / Discordボイチャ")
    mtg_desc  = discord.ui.TextInput(label="説明・議題（任意）", style=discord.TextStyle.paragraph,
                                      required=False, placeholder="今週の議題など")

    async def on_submit(self, interaction: discord.Interaction):
        mtg_data = {
            'title':       self.mtg_title.value,
            'date':        self.mtg_date.value,
            'location':    self.mtg_place.value or '未定',
            'description': self.mtg_desc.value  or '',
            'attending':   [],
            'absent':      [],
            'maybe':       [],
        }
        embed = build_mtg_embed(mtg_data, interaction.guild)
        view  = MTGView()
        await interaction.response.send_message(embed=embed, view=view)

        sent     = await interaction.original_response()
        all_data = load_data()
        all_data.setdefault('mtg', {})[str(sent.id)] = mtg_data
        save_data(all_data)

class MTGView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ 参加", style=discord.ButtonStyle.success,   custom_id="mtg:attend")
    async def attend(self, interaction: discord.Interaction, _: discord.ui.Button):
        await _mtg_update(interaction, 'attending')

    @discord.ui.button(label="❌ 欠席", style=discord.ButtonStyle.danger,    custom_id="mtg:absent")
    async def absent(self, interaction: discord.Interaction, _: discord.ui.Button):
        await _mtg_update(interaction, 'absent')

    @discord.ui.button(label="🤔 未定", style=discord.ButtonStyle.secondary, custom_id="mtg:maybe")
    async def maybe(self, interaction: discord.Interaction, _: discord.ui.Button):
        await _mtg_update(interaction, 'maybe')

async def _mtg_update(interaction: discord.Interaction, choice: str):
    all_data = load_data()
    msg_id   = str(interaction.message.id)
    mtg      = all_data.get('mtg', {}).get(msg_id)
    if not mtg:
        await interaction.response.send_message("❌ MTGデータが見つかりません。", ephemeral=True)
        return

    uid = str(interaction.user.id)
    for key in ('attending', 'absent', 'maybe'):
        lst = mtg.setdefault(key, [])
        if uid in lst:
            lst.remove(uid)

    mtg.setdefault(choice, []).append(uid)
    all_data['mtg'][msg_id] = mtg
    save_data(all_data)

    label = {"attending": "参加", "absent": "欠席", "maybe": "未定"}[choice]
    await interaction.response.edit_message(embed=build_mtg_embed(mtg, interaction.guild))
    await interaction.followup.send(f"「{label}」で登録しました。", ephemeral=True)


# ── Cog 本体 ─────────────────────────────────────────────────
class Events(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(EventView())
        bot.add_view(MTGView())
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()

    @tasks.loop(minutes=5)
    async def reminder_loop(self):
        all_data = load_data()
        now      = datetime.now()
        changed  = False

        for eid, ev in all_data.items():
            if not isinstance(ev, dict) or 'reminders' not in ev:
                continue
            for r in ev['reminders']:
                if r.get('sent'):
                    continue
                if parse_dt(r['time']) and parse_dt(r['time']) <= now:
                    try:
                        enterprise   = ev.get('enterprise', '全体')
                        ch_name      = ENTERPRISE_CH.get(enterprise)
                        thread_id    = ev.get('thread_id')
                        msg_id       = ev.get('msg_id')

                        # 企画チャンネルを送信先にする
                        ch = None
                        if ch_name:
                            for guild in self.bot.guilds:
                                ch = discord.utils.get(guild.text_channels, name=ch_name)
                                if ch:
                                    break

                        if ch:
                            # 企画ロールをメンション
                            role_name = ENTERPRISE_ROLE.get(enterprise)
                            guild     = ch.guild
                            if role_name:
                                role    = discord.utils.get(guild.roles, name=role_name)
                                mention = role.mention if role else f"@{role_name}"
                            else:
                                mention = "@everyone"

                            custom_msg = r.get('message') or "締め切りが近づいています！まだの方はお早めに！"
                            jump_url   = f"https://discord.com/channels/{guild.id}/{thread_id}/{msg_id}" \
                                         if thread_id and msg_id else ""
                            link_text  = f"\n[詳細・参加登録はこちら]({jump_url})" if jump_url else ""

                            body = (
                                f"⏰ **{ev['name']}**\n"
                                f"📅 {ev.get('date', '日時未定')}\n"
                                f"{custom_msg}"
                            )
                            await ch.send(f"{mention}\n{body}{link_text}")
                        else:
                            print(f"リマインド送信先チャンネルが見つかりません: {ch_name}", flush=True)
                    except Exception as e:
                        print(f"リマインド送信失敗: {e}", flush=True)
                    r['sent'] = True
                    changed   = True

        if changed:
            save_data(all_data)

    @reminder_loop.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="イベント作成", description="新しいイベントを作成します")
    async def cmd_create(self, interaction: discord.Interaction):
        view = EnterpriseSelectView()
        await interaction.response.send_message("**企画を選択してください**", view=view, ephemeral=True)

    @app_commands.command(name="リマインド設定", description="イベントにリマインドを設定します（幹事・企画長のみ）")
    @app_commands.describe(message_id="イベント投稿のメッセージID")
    @is_staff_or_leader()
    async def cmd_reminder(self, interaction: discord.Interaction, message_id: str):
        all_data = load_data()
        if message_id not in all_data:
            await interaction.response.send_message(
                "❌ イベントが見つかりません。メッセージIDを確認してください。", ephemeral=True
            )
            return
        await interaction.response.send_modal(ReminderModal(event_id=message_id))

    @cmd_reminder.error
    async def cmd_reminder_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("❌ 幹事・企画長のみ使用できます。", ephemeral=True)

    @app_commands.command(name="イベント一覧", description="企画ごとのイベント一覧を表示します")
    @app_commands.describe(kikaku="特定の企画でフィルタリング（省略可）")
    @app_commands.rename(kikaku="企画")
    @app_commands.choices(kikaku=[app_commands.Choice(name=e, value=e) for e in ENTERPRISES])
    async def cmd_list(self, interaction: discord.Interaction, kikaku: str | None = None):
        all_data = load_data()
        events   = {
            k: v for k, v in all_data.items()
            if isinstance(v, dict) and 'name' in v and k != 'mtg'
        }
        if kikaku:
            events = {k: v for k, v in events.items() if v.get('enterprise') == kikaku}

        if not events:
            label = f"**{kikaku}**の" if kikaku else ""
            await interaction.response.send_message(f"{label}イベントはまだありません。", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"{'📋 ' + kikaku if kikaku else '📋 全企画'} イベント一覧",
            color=0x5865F2,
        )
        for ev in list(events.values())[-10:]:
            status = "🔒" if ev.get('closed') else "🟢"
            count  = len(ev.get('participants', []))
            embed.add_field(
                name=f"{status} {ev['name']} [{ev.get('enterprise', '')}]",
                value=f"📅 {ev.get('date', '未定')} ｜ 👥 {count}名",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="mtg", description="MTGの出欠確認を投稿します（幹事・企画長のみ）")
    @is_staff_or_leader()
    async def cmd_mtg(self, interaction: discord.Interaction):
        await interaction.response.send_modal(MTGModal())

    @cmd_mtg.error
    async def cmd_mtg_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("❌ 幹事・企画長のみ使用できます。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Events(bot))
