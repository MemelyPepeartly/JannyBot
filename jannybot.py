import discord
from discord.ext import commands, tasks
from collections import defaultdict
import json
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='scruffy/', intents=intents)

# Configuration
delete_threshold = 10  # Default value; will be loaded from JSON
notification_users = []
whitelist = []
channel_watch_id = None  # ID of the channel to watch for deletion embeds

# Tracking message deletions
deleted_message_count = defaultdict(list)
user_deletion_info = {}  # Tracks the number of deletions per user

# Load data from JSON file
def load_data():
    global delete_threshold, notification_users, whitelist, user_deletion_info, channel_watch_id
    try:
        with open('bot_data.json', 'r') as f:
            data = json.load(f)
            delete_threshold = data.get('delete_threshold', 10)
            notification_users = data.get('notification_users', [])
            whitelist = data.get('whitelist', [])
            user_deletion_info = data.get('user_deletion_info', {})
            channel_watch_id = data.get('channel_watch_id', None)
    except FileNotFoundError:
        save_data()

# Save data to JSON file
def save_data():
    data = {
        'delete_threshold': delete_threshold,
        'notification_users': notification_users,
        'whitelist': whitelist,
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

# Helper function to check for required roles
def has_required_role(ctx):
    required_roles = {"Tard Wrangler", "Fim/Owners"}
    user_roles = {role.name for role in ctx.author.roles}
    return bool(required_roles.intersection(user_roles))

@bot.command()
async def channel_watch(ctx, channel: discord.TextChannel):
    """Set the channel to watch for deletion embeds."""
    if not has_required_role(ctx):
        await ctx.send("You do not have the required role to use this command.")
        return
    
    global channel_watch_id
    channel_watch_id = channel.id
    save_data()
    await ctx.send(f"Watching channel {channel.mention} for message deletion embeds.")
    print(f"Set channel_watch_id to {channel.id}")

@bot.command()
async def add_user(ctx, user: discord.User):
    """Add a user to the notification list."""
    if not has_required_role(ctx):
        await ctx.send("You do not have the required role to use this command.")
        return
    
    if user.id not in notification_users:
        notification_users.append(user.id)
        save_data()
        await ctx.send(f"{user.mention} has been added to the notification list.")
        print(f"Added {user} to the notification list.")
    else:
        await ctx.send(f"{user.mention} is already in the notification list.")
        print(f"{user} is already in the notification list.")

@bot.command()
async def set_threshold(ctx, threshold: int):
    """Set the message deletion threshold."""
    if not has_required_role(ctx):
        await ctx.send("You do not have the required role to use this command.")
        return
    
    global delete_threshold
    delete_threshold = threshold
    save_data()
    await ctx.send(f"Message deletion threshold set to {delete_threshold}.")
    print(f"Threshold set to {delete_threshold}")

@bot.command()
async def whitelist_user(ctx, user: discord.User):
    """Add a user to the whitelist."""
    if not has_required_role(ctx):
        await ctx.send("You do not have the required role to use this command.")
        return
    
    if user.id not in whitelist:
        whitelist.append(user.id)
        save_data()
        await ctx.send(f"{user.mention} has been added to the whitelist.")
        print(f"Added {user} to the whitelist.")
    else:
        await ctx.send(f"{user.mention} is already in the whitelist.")
        print(f"{user} is already in the whitelist.")

@bot.command()
async def status(ctx):
    """Check the status of message deletions."""
    if not has_required_role(ctx):
        await ctx.send("You do not have the required role to use this command.")
        return
    
    embed = discord.Embed(title="Message Deletion Status", color=discord.Color.blue())
    
    if user_deletion_info:
        for user_id, info in user_deletion_info.items():
            user = await bot.fetch_user(user_id)
            embed.add_field(name=user.name, value=f"Deleted Messages: {info['count']}\nLast Deleted: {info['last_deleted']}", inline=False)
    else:
        embed.description = "No users have deleted messages within the threshold."

    await ctx.send(embed=embed)
    print(f"Status command invoked by {ctx.author}")

@bot.event
async def on_message(message):
    # Check if the message is in the watched channel and contains an embed
    if message.channel.id == channel_watch_id and message.embeds:
        print(f"New message embed detected in watched channel: {message.channel.name}")
        
        for embed in message.embeds:
            if embed.author.name and "#0" in embed.author.name:
                username = embed.author.name.replace("#0", "")
                print(f"Username: {username}")

                # Attempt to find the user by username
                user = discord.utils.get(message.guild.members, name=username)

                if user:
                    user_id_str = str(user.id)
                    print(f"User found: {user} (ID: {user_id_str})")

                    # Ignore whitelisted users
                    if user.id in whitelist:
                        print(f"{user} is whitelisted. Ignoring message deletion tracking.")
                        continue

                    # Check the footer's text for the deletion marker
                    if embed.footer and "Message Deleted" in embed.footer.text:
                        print("Message deletion detected in embed footer.")

                        # Track the deletion
                        now = datetime.utcnow()
                        deleted_message_count[user_id_str].append(now)

                        # Update user deletion info
                        if user_id_str in user_deletion_info:
                            user_deletion_info[user_id_str]['count'] += 1
                        else:
                            user_deletion_info[user_id_str] = {'count': 1, 'last_deleted': now.isoformat()}

                        # Always update the last_deleted timestamp
                        user_deletion_info[user_id_str]['last_deleted'] = now.isoformat()

                        save_data()
                        print(f"Message deleted by {username} at {now}")

                else:
                    print(f"User {username} not found in the guild.")

    await bot.process_commands(message)  # Ensure other commands are still processed

@tasks.loop(seconds=15)
async def check_deletions():
    now = datetime.utcnow()
    users_to_remove = []

    for user_id, timestamps in deleted_message_count.items():
        # Reset the user's deletion count if more than 2 minutes have passed since their last deletion
        last_deleted_time = max(timestamps, default=None)
        if last_deleted_time and now - last_deleted_time > timedelta(minutes=2):
            users_to_remove.append(user_id)
            print(f"User {user_id} no longer tracked due to inactivity.")

        # Check if the user has exceeded the threshold
        if len(deleted_message_count[user_id]) >= delete_threshold:
            # Find the member in all the guilds the bot is in
            member = None
            for guild in bot.guilds:
                member = guild.get_member(int(user_id))
                if member:
                    break

            if member:
                # Kick the user from the server
                await kick_user(member)
                # Notify the specified users
                for notification_user_id in notification_users:
                    notification_user = await bot.fetch_user(notification_user_id)
                    await notification_user.send(f"{member.mention} has been kicked from the server due to excessive message deletions.")
                # Mark the user for removal from the list after kicking
                users_to_remove.append(user_id)
            else:
                print(f"Member with ID {user_id} not found in any guild.")

    # Remove users who are no longer active
    for user_id in users_to_remove:
        deleted_message_count.pop(user_id, None)
        user_deletion_info.pop(user_id, None)
        print(f"Removed user {user_id} from tracking data.")
    
    save_data()

async def kick_user(member):
    try:
        # Send a DM to the user before kicking
        await member.send("You have been kicked from the server due to exceeding the message deletion threshold.")
        await member.kick(reason="Exceeded message deletion threshold")
        print(f"Kicked {member} from the server for exceeding message deletion threshold.")
    except discord.Forbidden:
        print(f"Failed to kick {member}: Missing Permissions")
    except Exception as e:
        print(f"An error occurred while trying to kick {member}: {str(e)}")

bot.run('')
