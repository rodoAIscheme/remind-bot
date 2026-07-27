import json
import os

import discord
from discord import app_commands
from discord.ext import commands

import storage


class GroupInvite(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.groups: list[dict] = []
        self._load()

    def _load(self):
        self.groups = storage.load("groups", [])

    def _save(self):
        storage.save("groups", self.groups)

    def _find_group(self, message_id: int, emoji: str) -> dict | None:
        return next(
            (g for g in self.groups if g["message_id"] == message_id and g["emoji"] == emoji),
            None,
        )

    @app_commands.command(name="group_create", description="リアクションでプライベートチャンネルに招待できるグループを作成します")
    @app_commands.describe(
        target_channel="リアクションした人に閲覧権限を付与するチャンネル",
        emoji="リアクションに使う絵文字",
        description="案内メッセージに表示する説明文",
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def group_create(
        self,
        interaction: discord.Interaction,
        target_channel: discord.TextChannel,
        emoji: str,
        description: str,
    ):
        bot_member = interaction.guild.me
        perms = target_channel.permissions_for(bot_member)
        if not perms.manage_channels and not perms.manage_roles:
            await interaction.response.send_message(
                f"Botに {target_channel.mention} の権限管理(manage_channels/manage_roles)がありません。",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"📌 リアクションを押して {target_channel.name} に参加する",
            description=description,
        )
        message = await interaction.channel.send(embed=embed)
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            await message.delete()
            await interaction.response.send_message("指定された絵文字を使用できませんでした。", ephemeral=True)
            return

        self.groups.append(
            {
                "guild_id": interaction.guild_id,
                "message_id": message.id,
                "channel_id": interaction.channel_id,
                "target_channel_id": target_channel.id,
                "emoji": emoji,
            }
        )
        self._save()

        await interaction.response.send_message(
            f"グループを作成しました。{emoji} のリアクションで招待されます。(message_id: {message.id})",
            ephemeral=True,
        )

    @app_commands.command(name="group_list", description="設定済みのグループ一覧を表示します")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def group_list(self, interaction: discord.Interaction):
        mine = [g for g in self.groups if g["guild_id"] == interaction.guild_id]
        if not mine:
            await interaction.response.send_message("設定されているグループはありません。", ephemeral=True)
            return
        lines = []
        for g in mine:
            channel = interaction.guild.get_channel(g["target_channel_id"])
            channel_text = channel.name if channel else "(削除済みチャンネル)"
            lines.append(f"・{channel_text} | {g['emoji']} | message_id: {g['message_id']}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="group_delete", description="グループ設定を削除します")
    @app_commands.describe(message_id="削除するグループの案内メッセージID (/group_list で確認)")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def group_delete(self, interaction: discord.Interaction, message_id: str):
        try:
            mid = int(message_id)
        except ValueError:
            await interaction.response.send_message("message_id は数値で指定してください。", ephemeral=True)
            return

        target = next((g for g in self.groups if g["message_id"] == mid and g["guild_id"] == interaction.guild_id), None)
        if target is None:
            await interaction.response.send_message("指定されたグループが見つかりません。", ephemeral=True)
            return

        self.groups.remove(target)
        self._save()
        await interaction.response.send_message(f"グループ招待設定 (message_id: {mid}) を削除しました。", ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member is None or payload.member.bot:
            return
        group = self._find_group(payload.message_id, str(payload.emoji))
        if group is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        target_channel = guild.get_channel(group["target_channel_id"])
        if target_channel is None:
            return

        try:
            await target_channel.set_permissions(
                payload.member, view_channel=True, send_messages=True, read_message_history=True
            )
            await target_channel.send(f"{payload.member.mention} さんが「{target_channel.name}」に参加しました。")
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        group = self._find_group(payload.message_id, str(payload.emoji))
        if group is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        member = guild.get_member(payload.user_id)
        if member is None or member.bot:
            return
        target_channel = guild.get_channel(group["target_channel_id"])
        if target_channel is None:
            return

        try:
            await target_channel.set_permissions(member, overwrite=None)
        except discord.Forbidden:
            pass

    @group_create.error
    @group_list.error
    @group_delete.error
    async def on_group_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("このコマンドを実行する権限がありません。", ephemeral=True)
        else:
            await interaction.response.send_message(f"エラーが発生しました: {error}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GroupInvite(bot))
