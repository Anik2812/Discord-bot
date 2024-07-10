import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import pytz
import json
import asyncio
import random
import re

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command('help')

reminders = []
user_timezones = {}

# Load data from files
def load_data():
    global reminders, user_timezones
    try:
        with open('reminders.json', 'r') as f:
            reminders = json.load(f)
        with open('timezones.json', 'r') as f:
            user_timezones = json.load(f)
    except FileNotFoundError:
        reminders = []
        user_timezones = {}

# Save data to files
def save_data():
    with open('reminders.json', 'w') as f:
        json.dump(reminders, f)
    with open('timezones.json', 'w') as f:
        json.dump(user_timezones, f)

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    load_data()
    check_reminders.start()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

def get_next_id():
    return max([r['id'] for r in reminders] + [0]) + 1

def parse_time(time_str, user_id):
    try:
        if ':' in time_str:
            time = datetime.datetime.strptime(time_str, "%H:%M").time()
            date = datetime.date.today()
            dt = datetime.datetime.combine(date, time)
            if dt <= datetime.datetime.now():
                dt += datetime.timedelta(days=1)
        else:
            dt = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        
        if user_id in user_timezones:
            user_tz = pytz.timezone(user_timezones[user_id])
            dt = user_tz.localize(dt)
        else:
            dt = pytz.UTC.localize(dt)
        
        return dt.astimezone(pytz.UTC)
    except ValueError:
        return None

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
    save_data()
    return reminder

@bot.hybrid_command(name="remind", description="Set a reminder")
@app_commands.describe(time="Time for the reminder (HH:MM or YYYY-MM-DD HH:MM)", message="Reminder message")
async def remind(ctx, time: str, *, message: str):
    remind_time = parse_time(time, str(ctx.author.id))
    if not remind_time:
        await ctx.send("Invalid time format. Please use HH:MM for today/tomorrow or YYYY-MM-DD HH:MM for a specific date.")
        return
    now = datetime.datetime.now(pytz.UTC)
    if remind_time < now:
        await ctx.send("The reminder time must be in the future.")
        return
    reminder = await add_reminder(ctx.author.id, ctx.channel.id, remind_time, message)
    await ctx.send(f"Reminder #{reminder['id']} set for {remind_time.strftime('%Y-%m-%d %H:%M')} UTC. I'll remind you: {message}")

@bot.hybrid_command(name="schedule", description="Create a recurring schedule")
@app_commands.describe(
    start_time="Start time for the schedule (HH:MM or YYYY-MM-DD HH:MM)",
    repeat_interval="Repeat interval in minutes",
    message="Schedule message"
)
async def schedule(ctx, start_time: str, repeat_interval: int, *, message: str):
    schedule_time = parse_time(start_time, ctx.author.id)
    if not schedule_time:
        await ctx.send("Invalid time format. Please use HH:MM for today/tomorrow or YYYY-MM-DD HH:MM for a specific date.")
        return
    if schedule_time < datetime.datetime.now(pytz.UTC):
        await ctx.send("The start time must be in the future.")
        return
    if repeat_interval <= 0:
        await ctx.send("The repeat interval must be a positive number.")
        return
    reminder = await add_reminder(ctx.author.id, ctx.channel.id, schedule_time, message, repeat_interval)
    await ctx.send(f"Schedule #{reminder['id']} set starting at {schedule_time.strftime('%Y-%m-%d %H:%M')} UTC, repeating every {repeat_interval} minutes. Message: {message}")

@bot.hybrid_command(name="list", description="List all reminders and schedules")
async def list_reminders(ctx):
    user_reminders = [r for r in reminders if r['user'] == ctx.author.id]
    if not user_reminders:
        await ctx.send("You have no active reminders or schedules.")
    else:
        reminder_list = "\n".join([f"#{r['id']}: {r['time']} UTC - {r['message']}" + (f" (Repeats every {r['repeat_interval']} minutes)" if r['repeat_interval'] else "") for r in user_reminders])
        await ctx.send(f"Your reminders:\n{reminder_list}")

@bot.hybrid_command(name="delete", description="Delete a reminder or schedule")
@app_commands.describe(reminder_id="ID of the reminder to delete")
async def delete_reminder(ctx, reminder_id: int):
    global reminders
    user_reminders = [r for r in reminders if r['user'] == ctx.author.id]
    reminder = next((r for r in user_reminders if r['id'] == reminder_id), None)
    if reminder:
        reminders = [r for r in reminders if r['id'] != reminder_id]
        save_data()
        await ctx.send(f"Reminder #{reminder_id} deleted.")
    else:
        await ctx.send(f"Reminder #{reminder_id} not found or you don't have permission to delete it.")

@bot.hybrid_command(name="clear", description="Clear all your reminders and schedules")
async def clear_reminders(ctx):
    global reminders
    old_count = len(reminders)
    reminders = [r for r in reminders if r['user'] != ctx.author.id]
    new_count = len(reminders)
    deleted_count = old_count - new_count
    save_data()
    await ctx.send(f"{deleted_count} reminder(s) and schedule(s) have been cleared.")

@bot.hybrid_command(name="snooze", description="Snooze a reminder")
@app_commands.describe(reminder_id="ID of the reminder to snooze", minutes="Number of minutes to snooze")
async def snooze_reminder(ctx, reminder_id: int, minutes: int):
    reminder = next((r for r in reminders if r['id'] == reminder_id and r['user'] == ctx.author.id), None)
    if reminder:
        current_time = datetime.datetime.strptime(reminder['time'], "%Y-%m-%d %H:%M")
        new_time = current_time + datetime.timedelta(minutes=minutes)
        reminder['time'] = new_time.strftime("%Y-%m-%d %H:%M")
        save_data()
        await ctx.send(f"Reminder #{reminder_id} snoozed. New time: {new_time.strftime('%Y-%m-%d %H:%M')} UTC")
    else:
        await ctx.send(f"Reminder #{reminder_id} not found or you don't have permission to snooze it.")

@bot.hybrid_command(name="timezone", description="Set your timezone")
@app_commands.describe(timezone="Your timezone (e.g., US/Eastern, Europe/London)")
async def set_timezone(ctx, timezone: str):
    try:
        pytz.timezone(timezone)
        user_timezones[str(ctx.author.id)] = timezone
        save_data()
        await ctx.send(f"Your timezone has been set to {timezone}.")
    except pytz.exceptions.UnknownTimeZoneError:
        await ctx.send("Invalid timezone. Please use a valid timezone name (e.g., US/Eastern, Europe/London).")

@bot.hybrid_command(name="help", description="Show help for bot commands")
async def help_command(ctx):
    help_text = """
    Available commands:
    !remind <time> <message> - Set a reminder (time: HH:MM or YYYY-MM-DD HH:MM)
    !schedule <start_time> <repeat_interval> <message> - Create a recurring schedule
    !list - List all your reminders and schedules
    !delete <reminder_id> - Delete a specific reminder or schedule
    !clear - Clear all your reminders and schedules
    !snooze <reminder_id> <minutes> - Snooze a reminder
    !timezone <timezone> - Set your timezone
    !help - Show this help message
    !random <choices...> - Pick a random item from the given choices
    !poll <question> | <option1> | <option2> | ... - Create a poll
    
    All commands can also be used as slash commands.
    """
    await ctx.send(help_text)

@bot.hybrid_command(name="random", description="Pick a random item from the given choices")
@app_commands.describe(choices="List of choices separated by spaces")
async def random_choice(ctx, *, choices: str):
    items = choices.split()
    if len(items) < 2:
        await ctx.send("Please provide at least two choices.")
    else:
        chosen = random.choice(items)
        await ctx.send(f"I choose: {chosen}")

@bot.hybrid_command(name="poll", description="Create a poll")
@app_commands.describe(options="Question and options separated by |")
async def create_poll(ctx, *, options: str):
    parts = options.split('|')
    if len(parts) < 3:
        await ctx.send("Please provide a question and at least two options, separated by |")
        return
    
    question = parts[0].strip()
    poll_options = [option.strip() for option in parts[1:]]
    
    description = "\n".join(f"{chr(127462 + i)} {option}" for i, option in enumerate(poll_options))
    embed = discord.Embed(title=question, description=description, color=0x00ff00)
    embed.set_footer(text=f"Poll created by {ctx.author.display_name}")
    
    poll_message = await ctx.send(embed=embed)
    for i in range(len(poll_options)):
        await poll_message.add_reaction(chr(127462 + i))

@tasks.loop(minutes=1)
async def check_reminders():
    now = datetime.datetime.now(pytz.UTC)
    to_remove = []
    for reminder in reminders:
        reminder_time = datetime.datetime.strptime(reminder['time'], "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)
        if reminder_time <= now:
            channel = bot.get_channel(reminder['channel'])
            if channel:
                await channel.send(f"<@{reminder['user']}> Reminder: {reminder['message']}")
            
            if reminder['repeat_interval']:
                next_time = reminder_time + datetime.timedelta(minutes=reminder['repeat_interval'])
                reminder['time'] = next_time.strftime("%Y-%m-%d %H:%M")
            else:
                to_remove.append(reminder)
    
    for reminder in to_remove:
        reminders.remove(reminder)
    
    save_data()

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing required argument. Use '!help' for more information.")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("Command not found. Use '!help' to see available commands.")
    else:
        await ctx.send(f"An error occurred: {str(error)}")

bot.run('add_bot_token')