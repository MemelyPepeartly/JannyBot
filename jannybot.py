import discord
from discord.ext import commands, tasks
from collections import defaultdict
import json
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.message_delete = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Configuration
delete_threshold = 10               # Number of deletions allowed within the time period
time_period = timedelta(minutes=5)  # Time period to track deletions
notification_users = []
whitelist = []

# Tracking message deletions
deleted_message_count = defaultdict(list)

# Load the notification users from JSON file
def load_notification_users():
    global notification_users
    try:
        with open('notification_users.json', 'r') as f:
            notification_users = json.load(f)
    except FileNotFoundError:
        notification_users = []

# Save the notification users to JSON file
def save_notification_users():
    with open('notification_users.json', 'w') as f:
        json.dump(notification_users, f)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    load_notification_users()
    check_deletions.start()  # Start the background task to check deletions

@bot.command()
async def add_user(ctx, user: discord.User):
    """Add a user to the notification list."""
    notification_users.append(user.id)
    save_notification_users()
    await ctx.send(f"{user.mention} has been added to the notification list.")

@bot.command()
async def set_threshold(ctx, threshold: int):
    """Set the message deletion threshold."""
    global delete_threshold
    delete_threshold = threshold
    await ctx.send(f"Message deletion threshold set to {delete_threshold}.")

@bot.command()
async def whitelist_user(ctx, user: discord.User):
    """Add a user to the whitelist."""
    whitelist.append(user.id)
    await ctx.send(f"{user.mention} has been added to the whitelist.")

@bot.event
async def on_message_delete(message):
    user_id = message.author.id

    # Ignore whitelisted users
    if user_id in whitelist:
        return

    # Track the time of deletion
    now = datetime.utcnow()
    deleted_message_count[user_id].append(now)

@tasks.loop(minutes=1)
async def check_deletions():
    now = datetime.utcnow()

    for user_id, timestamps in deleted_message_count.items():
        # Filter out timestamps older than the time period
        deleted_message_count[user_id] = [ts for ts in timestamps if now - ts < time_period]

        # Check if the user has exceeded the threshold
        if len(deleted_message_count[user_id]) >= delete_threshold:
            user = await bot.fetch_user(user_id)
            # Restrict the user (customize based on your server's roles/permissions)
            await restrict_user(user)
            # Notify the specified users
            for user_id in notification_users:
                notification_user = await bot.fetch_user(user_id)
                await notification_user.send(f"{user.mention} has been restricted from deleting messages due to excessive deletions.")
            # Reset the user's deletion count
            deleted_message_count[user_id] = []

async def restrict_user(user):
    for guild in bot.guilds:
        for channel in guild.text_channels:
            # Get the current permissions for the user in the channel
            permissions = channel.permissions_for(user)

            # Check if the user can manage messages, then restrict them
            if permissions.manage_messages:
                # Define the new permissions overwriting the existing ones
                overwrite = discord.PermissionOverwrite()
                overwrite.manage_messages = False

                # Apply the permission overwrite to the specific user in this channel
                await channel.set_permissions(user, overwrite=overwrite)

                # Send a notification to the channel
                await channel.send(f"{user.mention} has been restricted from deleting their own messages due to excessive deletions.")


bot.run('TOKEN')
