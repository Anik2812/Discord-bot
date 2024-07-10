import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import pytz
import asyncio
import json

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

reminders = []

# Load reminders from file
def load_reminders():
    global reminders
    try:
        with open('reminders.json', 'r') as f:
            reminders = json.load(f)
    except FileNotFoundError:
        reminders = []

# Save reminders to file
def save_reminders():
    with open('reminders.json', 'w') as f:
        json.dump(reminders, f)

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    load_reminders()
    check_reminders.start()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

def get_next_id():
    return max([r['id'] for r in reminders] + [0]) + 1

async def add_reminder(user_id, channel_id, time, message, repeat_interval=None):
    reminder = {
        "id": get_next_id(),
        "user": user_id,
        "channel": channel_id,
        "time": time.strftime("%Y-%m-%d %H:%M"),
        "message": message,
        "repeat_interval": repeat_interval
    }
    reminders.append(reminder)
    save_reminders()
    return reminder

@bot.hybrid_command(name="remind", description="Set a reminder")
@app_commands.describe(time="Time for the reminder (YYYY-MM-DD HH:MM)", message="Reminder message")
async def remind(ctx, time: str, *, message: str):
    try:
        remind_time = datetime.datetime.strptime(time, "%Y-%m-%d %H:%M")
        reminder = await add_reminder(ctx.author.id, ctx.channel.id, remind_time, message)
        await ctx.send(f"Reminder #{reminder['id']} set for {time}. I'll remind you: {message}")
    except ValueError:
        await ctx.send("Invalid time format. Please use YYYY-MM-DD HH:MM")

@bot.hybrid_command(name="schedule", description="Create a recurring schedule")
@app_commands.describe(
    start_time="Start time for the schedule (YYYY-MM-DD HH:MM)",