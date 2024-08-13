import discord
from discord.ext import commands, tasks
from collections import defaultdict
import json
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix='scruffy/', intents=intents)

# Configuration
delete_threshold = 10  # Default value; will be loaded from JSON
time_period = timedelta(minutes=5)  # Time period to track deletions
notification_users = []
whitelist = []
channel_watch_id = None  # ID of the channel to watch for deletion embeds

# Tracking message deletions
deleted_message_count = defaultdict(list)
user_deletion_info = {}  # Tracks the number of deletions per user

# Load data from JSON file
def load_data():
    global delete_threshold, notification_users, user_deletion_info, channel_watch_id
    try:
        with open('bot_data.json', 'r') as f:
            data = json.load(f)
            delete_threshold = data.get('delete_threshold', 10)
            notification_users = data.get('notification_users', [])
            user_deletion_info = data.get('user_deletion_info', {})
            channel_watch_id = data.get('channel_watch_id', None)
    except FileNotFoundError:
        save_data()

# Save data to JSON file
def save_data():
    data = {
        'delete_threshold': delete_threshold,
        'notification_users': notification_users,
        'user_deletion_info': user_deletion_info,
        'channel_watch_id': channel_watch_id
    }
    with open('bot_data.json', 'w') as f:
        json.dump(data, f)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    load_data()
    check_deletions.start()  # Start the background task to check deletions

@bot.command()
async def channel_watch(ctx, channel: discord.TextChannel):
    """Set the channel to watch for deletion embeds."""
    global channel_watch_id
    channel_watch_id = channel.id
    save_data()
    await ctx.send(f"Watching channel {channel.mention} for message deletion embeds.")
    print(f"Set channel_watch_id to {channel.id}")

@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return  # Ignore bot messages

    user_id = str(message.author.id)  # Ensure user_id is a string

    # Ignore whitelisted users
    if user_id in whitelist:
        return

    # Track the time of deletion
    now = datetime.utcnow()
    deleted_message_count[user_id].append(now)

    # Update user deletion info
    if user_id in user_deletion_info:
        user_deletion_info[user_id]['count'] += 1
    else:
        user_deletion_info[user_id] = {'count': 1, 'last_deleted': now.isoformat()}

    # Always update the last_deleted timestamp
    user_deletion_info[user_id]['last_deleted'] = now.isoformat()

    save_data()
    print(f"Message deleted by {message.author} at {now}")

@bot.event
async def on_message(message):
    print(f"Message detected: {message.content}")
    print(f"Embeds detected: {message.embeds}")


    # Check if the message is in the watched channel and contains an embed
    if message.channel.id == channel_watch_id and message.embeds:
        print(f"New message detected in watched channel: {message.channel.name}")
        
        for embed in message.embeds:
            print("Embed detected:")
            print(f"Title: {embed.title}")
            print(f"Description: {embed.description}")
            print(f"Author: {embed.author.name} (Icon URL: {embed.author.icon_url})")

            if embed.description and "Message Deleted" in embed.description:
                print("Message deletion detected in embed description.")
                
                # Extract user information from the embed
                user_name = embed.author.name
                user_id = int(embed.author.icon_url.split('/')[-1].split('.')[0])  # Assuming user ID is in the URL
                
                print(f"User identified: {user_name} (ID: {user_id})")

                # Track the deletion
                now = datetime.utcnow()
                user_id_str = str(user_id)
                deleted_message_count[user_id_str].append(now)

                # Update user deletion info
                if user_id_str in user_deletion_info:
                    user_deletion_info[user_id_str]['count'] += 1
                else:
                    user_deletion_info[user_id_str] = {'count': 1, 'last_deleted': now.isoformat()}

                # Always update the last_deleted timestamp
                user_deletion_info[user_id_str]['last_deleted'] = now.isoformat()

                save_data()
                print(f"Message deleted by {user_name} at {now}")

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
            for notification_user_id in notification_users:
                notification_user = await bot.fetch_user(notification_user_id)
                await notification_user.send(f"{user.mention} has been restricted from deleting messages due to excessive deletions.")
            # Reset the user's deletion count
            deleted_message_count[user_id] = []

async def restrict_user(user):
    for guild in bot.guilds:
        for channel in guild.text_channels:
            try:
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
                    print(f"Restricted {user} from managing messages in {channel.name}.")

            except discord.Forbidden:
                print(f"Failed to restrict {user} in {channel.name}: Missing Permissions")

            except Exception as e:
                print(f"An error occurred while trying to restrict {user} in {channel.name}: {str(e)}")

@bot.command()
async def status(ctx):
    """Check the status of message deletions."""
    embed = discord.Embed(title="Message Deletion Status", color=discord.Color.blue())
    
    if user_deletion_info:
        for user_id, info in user_deletion_info.items():
            user = await bot.fetch_user(user_id)
            embed.add_field(name=user.name, value=f"Deleted Messages: {info['count']}\nLast Deleted: {info['last_deleted']}", inline=False)
    else:
        embed.description = "No users have deleted messages within the threshold."

    await ctx.send(embed=embed)
    print(f"Status command invoked by {ctx.author}")

bot.run('')
