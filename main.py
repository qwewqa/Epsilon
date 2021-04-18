import json
import asyncio
import os
import sys
import logging

import re
import random

import psutil
import time
import datetime

import discord
import colorlog
import motor.motor_asyncio

from discord.ext import commands
from discord.utils import find, get
from pymongo import MongoClient
from datetime import timedelta

from formatting.constants import VERSION as BOTVERSION
from formatting.constants import NAME

# read config information
with open("config.json") as file:
    config_json = json.load(file)
    TOKEN = config_json["token"]
    DBPASSWORD = config_json['db_password']


log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

dlog = logging.getLogger('discord')
dlog.setLevel(logging.WARNING)

intents = discord.Intents.default()
intents.members = True

default_prefix = "%"
databaseName = config_json["database_name"]

####################

#set up fancy format logging
def _setup_logging():
    shandler = logging.StreamHandler()
    shandler.setLevel(config_json["log_level"])
    shandler.setFormatter(colorlog.LevelFormatter(
        fmt = {
            'DEBUG': '{log_color}[{levelname}:{module}] {message}',
            'INFO': '{log_color}{message}',
            'WARNING': '{log_color}{levelname}: {message}',
            'ERROR': '{log_color}[{levelname}:{module}] {message}',
            'CRITICAL': '{log_color}[{levelname}:{module}] {message}',

            'EVERYTHING': '{log_color}[{levelname}:{module}] {message}',
            'NOISY': '{log_color}[{levelname}:{module}] {message}',
            'VOICEDEBUG': '{log_color}[{levelname}:{module}][{relativeCreated:.9f}] {message}',
            'FFMPEG': '{log_color}[{levelname}:{module}][{relativeCreated:.9f}] {message}'
        },
        log_colors = {
            'DEBUG':    'cyan',
            'INFO':     'white',
            'WARNING':  'yellow',
            'ERROR':    'red',
            'CRITICAL': 'bold_red',

            'EVERYTHING': 'white',
            'NOISY':      'white',
            'FFMPEG':     'bold_purple',
            'VOICEDEBUG': 'purple',
    },
        style = '{',
        datefmt = ''
    ))
    log.addHandler(shandler)
    dlog.addHandler(shandler)

_setup_logging()

log.info(f"Set logging level to {config_json['log_level']}")

if config_json["debug_mode"] == True:
    debuglog = logging.getLogger('discord')
    debuglog.setLevel(logging.DEBUG)
    dhandler = logging.FileHandler(filename = 'logs/discord.log', encoding = 'utf-8', mode = 'w')
    dhandler.setFormatter(logging.Formatter('{asctime}:{levelname}:{name}: {message}', style = '{'))
    debuglog.addHandler(dhandler)

if os.path.isfile(f"logs/{NAME}.log"):
    log.info("Moving old bot log")
    try:
        if os.path.isfile(f"logs/{NAME}.log.last"):
            os.unlink(f"logs/{NAME}.log.last")
        os.rename(f"logs/{NAME}.log", f"logs/{NAME}.log.last")
    except:
        pass

with open(f"logs/{NAME}.log", 'w', encoding = 'utf8') as f:
    f.write('\n')
    f.write(" PRE-RUN CHECK PASSED ".center(80, '#'))
    f.write('\n\n')

fhandler = logging.FileHandler(f"logs/{NAME}.log", mode = 'a')
fhandler.setFormatter(logging.Formatter(
    fmt="[%(relativeCreated).9f] %(name)s-%(levelname)s: %(message)s"
))
fhandler.setLevel(logging.DEBUG)
log.addHandler(fhandler)

####################

#db init and first time setup
log.info(f'\nEstablishing connection to MongoDB database {databaseName}')

mclient = motor.motor_asyncio.AsyncIOMotorClient(f"mongodb+srv://admin:{DBPASSWORD}@delphinium.jnxfw.mongodb.net/{databaseName}?retryWrites=true&w=majority")
db = mclient[databaseName]

log.info(f'Database loaded.\n')

async def _initialize_document(guild, id):
    post = {'server_id': id,
            'name': guild.name,
            'modrole': None,
            'autorole': None,
            'log_channel': None,
            'welcome_channel': None,
            'max_strike': 3,
            'modmail_channel': None,
            'rules_channel': None,
            'fun': False,
            'prefix': None,
            }
    log.info(f"Creating document for {guild.name}...")
    await db.servers.insert_one(post)


async def _check_document(guild, id):
    log.info("Checking db document for {}".format(guild.name))
    if await db.servers.find_one({"server_id": id}) == None:
        log.info("Did not find one, creating document...")
        await _initialize_document(guild, id)

####################

def gen_embed(name = None, icon_url = None, title = None, content = None):
    """Provides a basic template for embeds"""
    e = discord.Embed(colour = 0x1abc9c)
    if name and icon_url:
        e.set_author(name = name, icon_url = icon_url)
    e.set_footer(text = "Fueee~")
    e.title = title
    e.description = content
    return e 

#This is a super jenk way of handling the prefix without using the async db connection but it works
prefix_list = {}

def prefix(bot, message): 
    results =  None
    try:
        results = prefix_list.get(message.guild.id)
    except:
        pass

    if results:
        prefix = results
    else:
        prefix = default_prefix
    return prefix

####################

log.info(f'Starting {NAME} {BOTVERSION}')

bot = commands.Bot(command_prefix = prefix, intents = intents, case_insensitive = True)

try:
    sys.stdout.write(f"\x1b]2;{NAME} {BOTVERSION}\x07")
except:
    pass

uptime = time.time()
message_count = 0

####################

@bot.event
async def on_ready():
    for guild in bot.guilds:
        await _check_document(guild, guild.id)

    async for document in db.servers.find({}):
        server_id = document['server_id']
        if document['prefix'] is not None:
            prefix_list[server_id] = document['prefix']

    log.info("\n### PRE-STARTUP CHECKS PASSED ###\n")

    ####################

    status = discord.Game(f'{default_prefix}help | {len(bot.guilds)} servers')
    await bot.change_presence(activity = status)

    log.info(f"Connected: {bot.user.id}/{bot.user.name}#{bot.user.discriminator}")
    owner = await bot.application_info()
    owner = owner.owner
    log.info(f"Owner: {owner.id}/{owner.name}#{owner.discriminator}\n")

    log.info("Guild List:")
    for s in bot.guilds:
        ser = (f'{s.name} (unavailable)' if s.unavailable else s.name)
        log.info(f" - {ser}")    
    print(flush = True)

@bot.event
async def on_message(message):
    global message_count
    message_count += 1
    ctx = await bot.get_context(message)

    if isinstance(ctx.channel, discord.TextChannel):

        if ctx.author.bot is False:
            if ctx.prefix:
                log.info(f"{ctx.message.author.id}/{ctx.message.author.name}{ctx.message.author.discriminator}: {ctx.message.content}")
                await bot.invoke(ctx)
            elif ctx.message.reference:
                ref_message = await ctx.message.channel.fetch_message(ctx.message.reference.message_id)
                document = await db.servers.find_one({"server_id": ctx.guild.id})
                if ref_message.author == bot.user:
                    #modmail logic
                    if ctx.channel.id == document['modmail_channel']:
                        if ref_message.embeds[0].title == 'New Modmail':
                            ref_embed = ref_message.embeds[0].footer
                            user_id = ref_embed.text
                            user = await bot.fetch_user(user_id)
                            if document['modmail_channel']:
                                embed = gen_embed(name = f'{ctx.author.name}#{ctx.author.discriminator}', icon_url = ctx.author.avatar_url, title = "New Modmail", content = f'{message.clean_content}\n\nYou may reply to this modmail using the reply function.')
                                embed.set_footer(text = f"{ctx.guild.id}")
                                dm_channel = user.dm_channel
                                if user.dm_channel is None:
                                    dm_channel = await user.create_dm()
                                await dm_channel.send(embed = embed)
                                await ctx.send(embed = gen_embed(title = 'Modmail sent', content = f'Sent modmail to {user.name}#{user.discriminator}.'))
                    elif document['fun']:
                        log.info("Found a reply to me, generating response...")
                        msg = await get_msgid(ctx.message)
                        log.info(f"Message retrieved: {msg}\n")
                        await ctx.message.reply(content = msg)
                elif document['fun']:
                    post = {'server_id': ctx.guild.id,
                            'channel_id': ctx.channel.id,
                            'msg_id': ctx.message.id}
                    await db.msgid.insert_one(post)
            elif bot.user.id in ctx.message.raw_mentions and ctx.author != bot.user:
                log.info("Found a mention of myself, generating response...")
                msg = await get_msgid(ctx.message)
                log.info(f"Message retrieved: {msg}\n")
                await ctx.message.reply(content = msg)
            else:
                document = await db.servers.find_one({"server_id": ctx.guild.id})
                if document['fun']:
                    post = {'server_id': ctx.guild.id,
                            'channel_id': ctx.channel.id,
                            'msg_id': ctx.message.id}
                    await db.msgid.insert_one(post)
            

    elif isinstance(ctx.channel, discord.DMChannel):
        if ctx.author.bot is False:
            if ctx.message.reference:
                ref_message = await ctx.message.channel.fetch_message(ctx.message.reference.message_id)
                valid_options = {'You have been given a strike', 'New Modmail', 'You have been banned', 'You have been kicked'}
                if ref_message.embeds[0].title in valid_options or re.match('You have been muted', ref_message.embeds[0].title):
                    ref_embed = ref_message.embeds[0].footer
                    guild_id = ref_embed.text
                    document = await db.servers.find_one({"server_id": int(guild_id)})
                    if document['modmail_channel']:
                        guild = discord.utils.find(lambda g: g.id == int(guild_id), bot.guilds)
                        embed = gen_embed(name = f'{ctx.author.name}#{ctx.author.discriminator}', icon_url = ctx.author.avatar_url, title = "New Modmail", content = f'{message.clean_content}\n\nYou may reply to this modmail using the reply function.')
                        embed.set_footer(text = f"{ctx.author.id}")
                        channel = discord.utils.find(lambda c: c.id == document['modmail_channel'], guild.channels)
                        await channel.send(embed = embed)
                        await ctx.send(embed = gen_embed(title = 'Modmail sent', content = 'The moderators will review your message and get back to you shortly.'))
                        return
            elif ctx.prefix:
                if ctx.command.name == 'modmail':
                    await bot.invoke(ctx)


@bot.event
async def on_guild_join(guild):
    await _check_document(guild, guild.id)

    status = discord.Game(f'{default_prefix}help | {len(bot.guilds)} servers')
    await bot.change_presence(activity = status)

    general = find(lambda x: x.name == 'general',  guild.text_channels)
    if general and general.permissions_for(guild.me).send_messages:
        embed = gen_embed(name=f'{guild.name}',
                        icon_url = guild.icon_url,
                        title = 'Thanks for inviting me!',
                        content = 'You can get started by typing \%help to find the current command list.\nChange the command prefix by typing \%setprefix, and configure server settings with serverconfig and channelconfig.\n\nSource code: https://github.com/neon10lights/Epsilon\nSupport: https://ko-fi.com/neonlights\nIf you have feedback or need help, please DM Neon#5555.')
        await general.send(embed = embed)

@bot.event
async def on_member_join(member):
    log.info(f"A new member joined in {member.guild.name}")
    document = await db.servers.find_one({"server_id": member.guild.id})
    if document['autorole']:
        role = discord.utils.find(lambda r: r.name == str(document['autorole']), member.guild.roles)
        if role:
            await member.add_roles(role)
            log.info("Auto-assigned role to new member in {}".format(member.guild.name))
        else:
            log.error("Auto-assign role does not exist!")
    if document['welcome_channel']:
        welcome_channel = discord.utils.find(lambda c: c.id == int(document['welcome_channel']), member.guild.text_channels)
        welcomebanners = ["https://files.s-neon.xyz/share/welcomebanner-ps4.png", "https://files.s-neon.xyz/share/welcomebanner.png", "https://files.s-neon.xyz/share/welcomebanner-ritorin.png"]
        if document['rules_channel']:
            ruleschannel = int(document['rules_channel'])
            #TODO: replace with a embed
            content = discord.Embed(colour=0x1abc9c, title="Istariana vilseriol!", description=f"Welcome {member.name} to the {member.guild.name} Discord server. Please read our <#{ruleschannel}>, thank you.")
            content.set_author(name=f"{member.name}", icon_url=member.avatar_url)
            content.set_footer(text="ALICE IN DISSONANCE | {}".format(time.ctime()))
            content.set_thumbnail(url="https://files.s-neon.xyz/share/big-icon-512.png")
            content.set_image(url=random.choice(welcomebanners))
            await welcome_channel.send(embed = content)
        else:
            content = discord.Embed(colour=0x1abc9c, title="Istariana vilseriol!", description=f"Welcome {member.name} to the {member.guild.name} Discord server.")
            content.set_author(name=f"{member.name}", icon_url=member.avatar_url)
            content.set_footer(text="ALICE IN DISSONANCE | {}".format(time.ctime()))
            content.set_thumbnail(url="https://files.s-neon.xyz/share/big-icon-512.png")
            content.set_image(url=random.choice(welcomebanners))
            await welcome_channel.send(embed = content)

@bot.event
async def on_member_update(before, after):
    patreon = before.guild.get_role(201966886861275137)
    guild = after.guild
    if patreon:
        if not patreon in after.roles:
            # To prevent search through the entire audit log, limit to 1 minute in the past
            async for entry in guild.audit_logs(action=discord.AuditLogAction.member_role_update, user=bot.get_user(216303189073461248), after=(datetime.datetime.now() - datetime.timedelta(minutes=1))):
                if entry.target == before:
                    try:
                        await after.add_roles(patreon, reason="Auto-reassignment of patron role") 

                    except discord.Forbidden:
                        raise exceptions.CommandError("I don't have permission to modify a user's roles.")

                    except discord.HTTPException:
                        raise exceptions.CommandError("Something happened while attempting to add role.")

@bot.event
async def on_member_remove(member):
    document = await db.servers.find_one({"server_id": member.guild.id})
    if document['log_channel']:
        farewellchannel = int(document['log_channel'])
        name = member.name
        strip_name = re.sub('discord\.gg\/\w{7,}', '[removed]', name)
        channel = member.guild.get_channel(farewellchannel)
        await channel.send(content = f'Farewell {strip_name}! (ID: {member.id})')

###################

# This recursive function checks the database for a message ID for the bot to fetch a message and respond with when mentioned or replied to.
async def get_msgid(message, attempts = 1):
    # Construct the aggregation pipeline, match for the current server id and exclude bot messages if they somehow snuck past the initial regex.
    pipeline = [{'$match': {'$and': [{'server_id': message.guild.id}, {'author_id': {'$not': {'$regex': str(bot.user.id)}}}] }}, {'$sample': {'size': 1}}]
    async for msgid in db.msgid.aggregate(pipeline):
            # This is jenky and I believe can be fixed to use ctx instead, but it searches each channel until it finds the channel the message was sent in.
            # This lets us fetch the message.
            for channel in message.guild.channels:
                if channel.id == msgid['channel_id']:
                    try:
                        msg = await channel.fetch_message(msgid['msg_id'])
                        # Now let's double check that we aren't mentioning ourself or another bot, and that the messages has no embeds or attachments.
                        if (re.match('^%|^\^|^\$|^!|^\.|@', msg.content) == None) and (re.match(f'<@!?{bot.user.id}>', msg.content) == None) and (len(msg.embeds) == 0) and (msg.author.bot == False):
                            log.info("Attempts taken:{}".format(attempts))
                            log.info("Message ID:{}".format(msg.id))
                            return msg.clean_content
                        else:
                            # If we fail, remove that message ID from the DB so we never call it again.
                            attempts += 1
                            mid = msgid['msg_id']
                            await db.msgid.delete_one({"msg_id": mid})
                            log.info("Removing entry from db...")
                            return await get_msgid(message, attempts)

                    except discord.Forbidden:
                        raise discord.exceptions.CommandError("I don't have permissions to read message history.")

                    except discord.NotFound:
                        # This happens sometimes due to deleted message or other weird shenanigans, so do the same as above.
                        attempts += 1
                        mid = msgid['msg_id']
                        await db.msgid.delete_one({"msg_id": mid})
                        log.info("Removing entry from db...")
                        return await get_msgid(message, attempts)

####################

bot.remove_command('help')
bot.load_extension("commands.help")
bot.load_extension("commands.utility")
bot.load_extension("commands.errorhandler")
bot.load_extension("commands.fun")
bot.load_extension("commands.misc")
bot.load_extension("commands.administration")
bot.load_extension("commands.modmail")
bot.run(TOKEN)
