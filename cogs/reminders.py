import json
import os
import re
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

import storage

JST = timezone(timedelta(hours=9))

RELATIVE_PATTERN = re.compile(
    r"^(\d+)\s*(分後|時間後|日後|週間後|ヶ月後|か月後|カ月後|年後)$"
)
RELATIVE_UNITS = {
    "分後": lambda n: timedelta(minutes=n),
    "時間後": lambda n: timedelta(hours=n),
    "日後": lambda n: timedelta(days=n),
    "週間後": lambda n: timedelta(weeks=n),
    "ヶ月後": lambda n: timedelta(days=n * 30),
    "か月後": lambda n: timedelta(days=n * 30),
    "カ月後": lambda n: timedelta(days=n * 30),
    "年後": lambda n: timedelta(days=n * 365),
}

ABSOLUTE_FORMATS = [
    "%Y/%m/%d %H:%M",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d",
    "%Y-%m-%d",
    "%m/%d %H:%M",
    "%m/%d",
]


def parse_when(text: str, now: datetime) -> datetime | None:
    text = text.strip()

    m = RELATIVE_PATTERN.match(text)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        return now + RELATIVE_UNITS[unit](amount)

    for fmt in ABSOLUTE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if "%Y" not in fmt:
            parsed = parsed.replace(year=now.year)
        if "%H" not in fmt:
            parsed = parsed.replace(hour=9, minute=0)
        parsed = parsed.replace(tzinfo=JST)
        if "%Y" not in fmt and parsed < now:
            parsed = parsed.replace(year=now.year + 1)
        return parsed

    return None


class Reminders(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reminders: list[dict] = []
        self._next_id = 1
        self._load()
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

    def _load(self):
        self.reminders = storage.load("reminders", [])
        if self.reminders:
            self._next_id = max(r["id"] for r in self.reminders) + 1

    def _save(self):
        storage.save("reminders", self.reminders)

    @app_commands.command(name="remind", description="リマインドを設定します")
    @app_commands.describe(
        when="日時 (例: 2026/07/01 12:00, 7/1, 1週間後, 3日後, 2時間後)",
        content="リマインド内容",
    )
    async def remind(self, interaction: discord.Interaction, when: str, content: str):
        now = datetime.now(JST)
        due = parse_when(when, now)
        if due is None:
            await interaction.response.send_message(
                "日時を解析できませんでした。例: `2026/07/01 12:00`、`7/1`、`1週間後`、`3日後`、`2時間後`",
                ephemeral=True,
            )
            return
        if due <= now:
            await interaction.response.send_message("過去の日時は指定できません。", ephemeral=True)
            return

        reminder = {
            "id": self._next_id,
            "user_id": interaction.user.id,
            "channel_id": interaction.channel_id,
            "content": content,
            "due_at": due.isoformat(),
        }
        self._next_id += 1
        self.reminders.append(reminder)
        self._save()

        await interaction.response.send_message(
            f"リマインドを設定しました: {due.strftime('%Y/%m/%d %H:%M')} JST に「{content}」をお知らせします。(ID: {reminder['id']})",
            ephemeral=True,
        )

    @app_commands.command(name="reminders", description="自分が設定したリマインド一覧を表示します")
    async def list_reminders(self, interaction: discord.Interaction):
        mine = [r for r in self.reminders if r["user_id"] == interaction.user.id]
        if not mine:
            await interaction.response.send_message("設定中のリマインドはありません。", ephemeral=True)
            return
        lines = []
        for r in sorted(mine, key=lambda r: r["due_at"]):
            due = datetime.fromisoformat(r["due_at"])
            lines.append(f"ID {r['id']}: {due.strftime('%Y/%m/%d %H:%M')} - {r['content']}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="remind_cancel", description="リマインドをキャンセルします")
    @app_commands.describe(reminder_id="キャンセルするリマインドのID (/reminders で確認)")
    async def cancel_reminder(self, interaction: discord.Interaction, reminder_id: int):
        target = next(
            (r for r in self.reminders if r["id"] == reminder_id and r["user_id"] == interaction.user.id),
            None,
        )
        if target is None:
            await interaction.response.send_message("指定されたIDのリマインドが見つかりません。", ephemeral=True)
            return
        self.reminders.remove(target)
        self._save()
        await interaction.response.send_message(f"リマインド ID {reminder_id} をキャンセルしました。", ephemeral=True)

    @tasks.loop(seconds=30)
    async def check_reminders(self):
        now = datetime.now(JST)
        due_reminders = [r for r in self.reminders if datetime.fromisoformat(r["due_at"]) <= now]
        for r in due_reminders:
            channel = self.bot.get_channel(r["channel_id"])
            try:
                if channel is not None:
                    await channel.send(f"リマインド: {r['content']}")
                else:
                    user = await self.bot.fetch_user(r["user_id"])
                    await user.send(f"リマインド: {r['content']}")
            except discord.HTTPException:
                pass
            self.reminders.remove(r)
        if due_reminders:
            self._save()

    @check_reminders.before_loop
    async def before_check_reminders(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Reminders(bot))
