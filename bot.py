import discord
from discord.ext import commands
import os, sys
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)

COGS = ['cogs.events', 'cogs.committee', 'cogs.roles', 'cogs.reminders', 'cogs.group_invite']

async def setup_hook():
    for cog in COGS:
        await bot.load_extension(cog)
        print(f'  {cog} 読み込み完了', flush=True)

bot.setup_hook = setup_hook

@bot.event
async def on_ready():
    synced = await bot.tree.sync()
    print(f'{bot.user} 起動完了 / コマンド {len(synced)}件 同期済み', flush=True)

bot.run(os.getenv('DISCORD_TOKEN'))
