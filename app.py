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
bot.remove_command('help')  
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
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing required argument. Use '!help {ctx.command.name}' for more information.")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("Command not found. Use '!help' to see available commands.")
    else:
        await ctx.send(f"An error occurred: {str(error)}")

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
async def remind(ctx, time: str = None, *, message: str = None):
    if time is None or message is None:
        await ctx.send("Usage: !remind <YYYY-MM-DD HH:MM> <message>\nExample: !remind 2024-07-11 15:30 Take a break")
        return

    try:
        remind_time = datetime.datetime.strptime(time, "%Y-%m-%d %H:%M")
        reminder = await add_reminder(ctx.author.id, ctx.channel.id, remind_time, message)
        await ctx.send(f"Reminder #{reminder['id']} set for {time}. I'll remind you: {message}")
    except ValueError:
        await ctx.send("Invalid time format. Please use YYYY-MM-DD HH:MM")

@bot.hybrid_command(name="schedule", description="Create a recurring schedule")
@app_commands.describe(
    start_time="Start time for the schedule (YYYY-MM-DD HH:MM)",
    repeat_interval="Repeat interval in minutes",
    message="Schedule message"
)
async def schedule(ctx, start_time: str = None, repeat_interval: int = None, *, message: str = None):
    if start_time is None or repeat_interval is None or message is None:
        await ctx.send("Usage: !schedule <YYYY-MM-DD HH:MM> <repeat_interval_in_minutes> <message>\nExample: !schedule 2024-07-11 09:00 60 Daily standup meeting")
        return

    try:
        schedule_time = datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M")
        reminder = await add_reminder(ctx.author.id, ctx.channel.id, schedule_time, message, repeat_interval)
        await ctx.send(f"Schedule #{reminder['id']} set starting at {start_time}, repeating every {repeat_interval} minutes. Message: {message}")
    except ValueError:
        await ctx.send("Invalid time format. Please use YYYY-MM-DD HH:MM")

@bot.hybrid_command(name="list", description="List all reminders and schedules")
async def list_reminders(ctx):
    user_reminders = [r for r in reminders if r['user'] == ctx.author.id]
    if not user_reminders:
        await ctx.send("You have no active reminders or schedules.")
    else:
        reminder_list = "\n".join([f"#{r['id']}: {r['time']} - {r['message']}" + (f" (Repeats every {r['repeat_interval']} minutes)" if r['repeat_interval'] else "") for r in user_reminders])
        await ctx.send(f"Your reminders:\n{reminder_list}")

@bot.hybrid_command(name="delete", description="Delete a reminder or schedule")
@app_commands.describe(reminder_id="ID of the reminder to delete")
async def delete_reminder(ctx, reminder_id: int = None):
    if reminder_id is None:
        await ctx.send("Usage: !delete <reminder_id>\nExample: !delete 5")
        return

    global reminders
    user_reminders = [r for r in reminders if r['user'] == ctx.author.id]
    reminder = next((r for r in user_reminders if r['id'] == reminder_id), None)
    if reminder:
        reminders = [r for r in reminders if r['id'] != reminder_id]
        save_reminders()
        await ctx.send(f"Reminder #{reminder_id} deleted.")
    else:
        await ctx.send(f"Reminder #{reminder_id} not found or you don't have permission to delete it.")

@bot.hybrid_command(name="clear", description="Clear all your reminders and schedules")
async def clear_reminders(ctx):
    global reminders
    reminders = [r for r in reminders if r['user'] != ctx.author.id]
    save_reminders()
    await ctx.send("All your reminders and schedules have been cleared.")

@tasks.loop(minutes=1)
async def check_reminders():
    now = datetime.datetime.now()
    to_remove = []
    for reminder in reminders:
        reminder_time = datetime.datetime.strptime(reminder['time'], "%Y-%m-%d %H:%M")
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
    
    save_reminders()

@bot.hybrid_command(name="timezone", description="Set your timezone")
@app_commands.describe(timezone="Your timezone (e.g., US/Eastern, Europe/London)")
async def set_timezone(ctx, timezone: str = None):
    if timezone is None:
        await ctx.send("Usage: !timezone <timezone>\nExample: !timezone US/Eastern\n\nCommon timezones:\nUS/Eastern, US/Central, US/Pacific, Europe/London, Europe/Berlin, Asia/Tokyo")
        return

    try:
        pytz.timezone(timezone)
        # In a real implementation, you'd save this to a database
        await ctx.send(f"Your timezone has been set to {timezone}.")
    except pytz.exceptions.UnknownTimeZoneError:
        await ctx.send("Invalid timezone. Please use a valid timezone name. Type '!timezone' without arguments to see examples.")

@bot.hybrid_command(name="help", description="Show help for bot commands")
async def help_command(ctx):
    help_text = """
    Available commands:
    !remind <YYYY-MM-DD HH:MM> <message> - Set a reminder
    !schedule <YYYY-MM-DD HH:MM> <repeat_interval_in_minutes> <message> - Create a recurring schedule
    !list - List all your reminders and schedules
    !delete <reminder_id> - Delete a specific reminder or schedule
    !clear - Clear all your reminders and schedules
    !timezone <timezone> - Set your timezone
    !help - Show this help message
    
    All commands can also be used as slash commands.
    """
    await ctx.send(help_text)

bot.run('your_bot_token')