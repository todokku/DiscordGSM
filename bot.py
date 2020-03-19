import os
import time
import asyncio
import aiohttp
import urllib
import requests
from threading import Thread
from datetime import datetime

# discord
import discord
from discord.ext import commands

# discordgsm
from bin import *
from servers import Servers, ServerCache
from settings import Settings

# bot static data
VERSION = '1.4.0'
MIN_REFRESH_RATE = 5

# download servers.json every heroku dyno start
servers_json_url = os.getenv('SERVERS_JSON_URL')
if servers_json_url and servers_json_url.strip():
    print('Downloading servers.json...')
    try:
        r = requests.get(servers_json_url)
        with open('configs/servers.json', 'wb') as file:
            file.write(r.content)
    except:
        print('Fail to download servers.json on start up')

# download settings.json every heroku dyno start
settings_json_url = os.getenv('SETTINGS_JSON_URL')
if settings_json_url and settings_json_url.strip():
    print('Downloading settings.json...')
    try:
        r = requests.get(settings_json_url)
        with open('configs/settings.json', 'wb') as file:
            file.write(r.content)
    except:
        print('Fail to download settings.json on start up')

# clear cache
print('Clearing cache...')
for file in os.listdir('cache'):
    if file.endswith(".txt") or file.endswith(".json"):
        os.remove(os.path.join('cache', file))

# get settings
print('Setting up...')
settings = Settings.get()

# bot token
TOKEN = os.getenv('DGSM_TOKEN', settings['token'])

# set up bot
bot = commands.Bot(command_prefix=settings['prefix'])

# query servers and save cache
print('Pre-Query servers...')
game_servers = Servers()
game_servers.query()

# get servers
servers = game_servers.load()

# discord messages
messages = []

# boolean is currently refreshing
is_refresh = False

# bot ready action
@bot.event
async def on_ready():
    # set username and avatar
    with open('images/bitfor.jpg', 'rb') as file:
        try:
            avatar = file.read()
            await bot.user.edit(username='BITFOR', avatar=avatar)
        except:
            pass

    # print info to console
    print('----------------')
    print(f'Logged in as: {bot.user.name}')
    print(f'Robot ID: {bot.user.id}')
    app_info = await bot.application_info()
    print(f'Owner ID: {app_info.owner.id} ({app_info.owner.name})')
    print('----------------')

    # set bot presence
    activity_text = len(servers) == 0 and f'Command: {settings["prefix"]}dgsm' or f'{len(servers)} game servers'
    await bot.change_presence(status=discord.Status.online, activity=discord.Activity(name=activity_text, type=3))

    # get channels store to array
    channels = []
    for server in servers:
        channels.append(server['channel'])

    # remove duplicated channels
    channels = list(set(channels))

    for channel in channels:
        # set channel permission
        try:
            await bot.get_channel(channel).set_permissions(bot.user, read_messages=True, send_messages=True, reason='Display servers embed')
            print(f'Set channel: {channel} with permissions: read_messages, send_messages')
        except:
            print(f'Missing permission: Manage Roles, Manage Channels')

        # remove old messages in channels
        await bot.get_channel(channel).purge(check=lambda m: m.author==bot.user)

    # send embed
    for server in servers:
        message = await bot.get_channel(server['channel']).send(embed=get_embed(server))
        messages.append(message)

    # print delay time
    delay = int(settings['refreshrate']) if int(settings['refreshrate']) > MIN_REFRESH_RATE else MIN_REFRESH_RATE
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S') + f' Query servers every {delay} seconds')

    # start print servers
    t = Thread(target=await print_servers())
    t.start()

# print servers to discord
@asyncio.coroutine
async def print_servers():
    edit_error_count = 0
    next_update_time = 0

    while True:
        # don't continue when servers is refreshing
        if is_refresh:
            await asyncio.sleep(1)
            continue

        # edit error with some reasons (maybe messages edit limit?), anyway servers refresh will fix this issue
        if edit_error_count >= 10:
            edit_error_count = 0

            # refresh discord servers list
            await refresh_servers_list()
            continue

        if int(datetime.utcnow().timestamp()) >= next_update_time:
            # delay server query
            delay = int(settings['refreshrate']) if int(settings['refreshrate']) > MIN_REFRESH_RATE else MIN_REFRESH_RATE
            next_update_time = int(datetime.utcnow().timestamp()) + delay

            # query servers and save cache
            game_servers.query()

            # edit embed
            for i, server in zip(range(len(servers)), servers):
                # load server cache. If the data is the same, don't update the discord message
                server_cache = ServerCache(server['addr'], server['port'])
                if not server_cache.has_changed(): continue

                try:
                    await messages[i].edit(embed=get_embed(server))
                except:
                    edit_error_count += 1
                    print(f'Error: message: {messages[i]} fail to edit, message deleted or no permission. Server: {server["addr"]}:{server["port"]}')

        await asyncio.sleep(1)

# get game server embed
def get_embed(server):
    # load server cache
    server_cache = ServerCache(server['addr'], server['port'])

    # load server data
    data = server_cache.get_data()

    if data:
        # load server status Online/Offline
        status = server_cache.get_status()

        if status == 'Online':
            emoji = ':green_circle:'
            if data['maxplayers'] <= data['players']:
                color = discord.Color.from_rgb(240, 71, 71) # red
            elif data['maxplayers'] <= data['players'] * 2:
                color = discord.Color.from_rgb(250, 166, 26) # yellew
            else:
                color = discord.Color.from_rgb(67, 181, 129) # green
        else:
            emoji = ':red_circle:'
            color = discord.Color.from_rgb(32, 34, 37) # dark

        title = (data['password'] and ':lock: ' or '') + data["name"]
        description = ('custom' in server) and server['custom'] or ''
        if server['type'] == 'SourceQuery':
            embed = discord.Embed(title=title, description=f'Connect: steam://connect/{data["addr"]}:{server["port"]}\n' + description, color=color)
        elif description.strip():
            embed = discord.Embed(title=title, description=description, color=color)
        else:
            embed = discord.Embed(title=title, color=color)

        embed.add_field(name=f'{settings["fieldname"]["status"]}', value=f'{emoji} **{status}**', inline=True)
        embed.add_field(name=f'{settings["fieldname"]["address"]}:{settings["fieldname"]["port"]}', value=f'`{data["addr"]}:{data["port"]}`', inline=True)

        flag_emoji = ('country' in server) and (':flag_' + server['country'].lower() + f': {server["country"]}') or ':united_nations: Unknown'
        embed.add_field(name=f'{settings["fieldname"]["country"]}', value=flag_emoji, inline=True)

        embed.add_field(name=f'{settings["fieldname"]["game"]}', value=f'{data["game"]}', inline=True)
        embed.add_field(name=f'{settings["fieldname"]["currentmap"]}', value=f'{data["map"]}', inline=True)

        if status == 'Online':
            value = f'{data["players"]}' # example: 20/32
            if data['bots'] > 0: value += f' ({data["bots"]})' # example: 20 (2)/32
        else:
            value = '0' # example: 0/32
                
        embed.add_field(name=f'{settings["fieldname"]["players"]}', value=f'{value}/{data["maxplayers"]}', inline=True)

        if 'image_url' in server:
            image_url = str(server['image_url'])
        else:
            image_url = f'https://github.com/DiscordGSM/Map-Thumbnails/raw/master/{urllib.parse.quote(data["game"])}/{urllib.parse.quote(data["map"])}.jpg'

        embed.set_thumbnail(url=image_url)
    else:
        # server fail to query
        color = discord.Color.from_rgb(240, 71, 71) # red
        embed = discord.Embed(title='ERROR', description=f'{settings["fieldname"]["status"]}: :warning: **Fail to query**', color=color)
        embed.add_field(name=f'{settings["fieldname"]["port"]}', value=f'{server["addr"]}:{server["port"]}', inline=True)
    
    embed.set_footer(text=f'DiscordGSM v{VERSION} | Monitor game server | Last update: ' + datetime.now().strftime('%a, %Y-%m-%d %I:%M:%S%p'), icon_url='https://github.com/BattlefieldDuck/DiscordGSM/raw/master/images/discordgsm.png')
    
    return embed

# command: servers
# list all the servers in configs/servers.json
@bot.command(name='dgsm', aliases=['discordgsm'])
@commands.is_owner()
async def _dgsm(ctx):
    title = f'Command: {settings["prefix"]}dgsm'
    description = f'Thanks for using Discord Game Server Monitor ([DiscordGSM](https://github.com/BattlefieldDuck/DiscordGSM))\n'
    description += f'\nUseful commands:\n{settings["prefix"]}servers - Display the server list'
    description += f'\n{settings["prefix"]}serveradd - Add a server'
    description += f'\n{settings["prefix"]}serverdel - Delete a server'
    description += f'\n{settings["prefix"]}serversrefresh - Refresh the server list'
    description += f'\n{settings["prefix"]}getserversjson - get servers.json file'
    description += f'\n{settings["prefix"]}setserversjson - set servers.json file'
    color = discord.Color.from_rgb(114, 137, 218) # discord theme color
    embed = discord.Embed(title=title, description=description, color=color)
    embed.add_field(name='Support server', value='https://discord.gg/Cg4Au9T', inline=True)
    embed.add_field(name='Github', value='https://github.com/BattlefieldDuck/DiscordGSM', inline=True)
    await ctx.send(embed=embed)

# command: servers
# list all the servers in configs/servers.json
@bot.command(name='serversrefresh')
@commands.is_owner()
async def _serversrefresh(ctx):
    # refresh discord servers list
    await refresh_servers_list()

    # send response
    title = f'Command: {settings["prefix"]}serversrefresh'
    color = discord.Color.from_rgb(114, 137, 218) # discord theme color
    embed = discord.Embed(title=title, description=f'Servers list refreshed', color=color)
    await ctx.send(embed=embed)

async def refresh_servers_list():
    # currently refreshing
    global is_refresh
    if is_refresh: return
    is_refresh = True

    # set bot presence
    activity_text = '... Refreshing...'
    await bot.change_presence(status=discord.Status.idle, activity=discord.Activity(name=activity_text, type=3))

    # remove old messages
    global messages
    for message in messages:
        try:
            await message.delete()
        except:
            pass

    # reset messages
    messages = []

    # refresh server list
    game_servers.refresh()

    # reload servers
    global servers
    servers = game_servers.load()

    # get channels store to array
    channels = []
    for server in servers:
        channels.append(server['channel'])

    # remove duplicated channels
    channels = list(set(channels))

    # set channel permission and purge messages
    tasks = [set_channel_permission_and_purge_messages(channel) for channel in channels]
    await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED, timeout=None)

    # send embed
    for server in servers:
        message = await bot.get_channel(server['channel']).send(embed=get_embed(server))
        messages.append(message)

    activity_text = len(servers) == 0 and 'Command: !dgsm' or f'{len(servers)} game servers'
    await bot.change_presence(status=discord.Status.online, activity=discord.Activity(name=activity_text, type=3))

    # refresh finish
    is_refresh = False

    # log
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' Refreshed servers')

async def set_channel_permission_and_purge_messages(channel):
    # set channel permission
    try:
        await bot.get_channel(channel).set_permissions(bot.user, read_messages=True, send_messages=True, reason='Display servers embed')
        print(f'Set channel: {channel} with permissions: read_messages, send_messages')
    except:
        print(f'Missing permission: Manage Roles, Manage Channels')

    # remove old messages in channels
    await bot.get_channel(channel).purge(check=lambda m: m.author==bot.user)

# command: servers
# list all the servers in configs/servers.json
@bot.command(name='servers')
@commands.is_owner()
async def _servers(ctx):
    title = f'Command: {settings["prefix"]}servers'
    color = discord.Color.from_rgb(114, 137, 218) # discord theme color
    embed = discord.Embed(title=title, color=color)
    type, addr_port, channel = '', '', ''

    servers = game_servers.load()

    for i in range(len(servers)):
        type += f'`{i+1}`. {servers[i]["type"]}\n'
        addr_port += f'`{servers[i]["addr"]}:{servers[i]["port"]}`\n'
        channel += f'`{servers[i]["channel"]}`\n'

    embed.add_field(name='ID. Type', value=type, inline=True)
    embed.add_field(name='Address:Port', value=addr_port, inline=True)
    embed.add_field(name='Channel ID', value=channel, inline=True)
    await ctx.send(embed=embed)

# command: serveradd
# add a server to configs/servers.json
@bot.command(name='serveradd')
@commands.is_owner()
async def _serveradd(ctx, *args):
    title = f'Command: {settings["prefix"]}serveradd'
    color = discord.Color.from_rgb(114, 137, 218) # discord theme color

    if len(args) == 5:
        type, game, addr, port, channel = args

        if port.isdigit() and channel.isdigit():
            game_servers.add(type, game, addr, port, channel)

            # refresh discord servers list
            await refresh_servers_list()

            description=f'Server added successfully'
            embed = discord.Embed(title=title, description=description, color=color)
            embed.add_field(name='Type:Game', value=f'{type}:{game}', inline=True)
            embed.add_field(name='Address:Port', value=f'{addr}:{port}', inline=True)
            embed.add_field(name='Channel ID', value=channel, inline=True)
            await ctx.send(embed=embed)
            return

    description=f'Usage: {settings["prefix"]}serveradd <type> <game> <addr> <port> <channel>\nRemark: <port> and <channel> should be digit only'
    embed = discord.Embed(title=title, description=description, color=color)
    await ctx.send(embed=embed)

# command: serverdel
# delete a server by id from configs/servers.json
@bot.command(name='serverdel')
@commands.is_owner()
async def _serverdel(ctx, *args):
    title = f'Command: {settings["prefix"]}serverdel'
    color = discord.Color.from_rgb(114, 137, 218) # discord theme color

    if len(args) == 1:
        server_id = args[0]
        if server_id.isdigit():
            if game_servers.delete(server_id):
                # refresh discord servers list
                await refresh_servers_list()

                description=f'Server deleted successfully. ID: {server_id}'
                embed = discord.Embed(title=title, description=description, color=color)
                await ctx.send(embed=embed)
                return

    description=f'Usage: {settings["prefix"]}serverdel <id>\nRemark: view id with command {settings["prefix"]}servers'
    embed = discord.Embed(title=title, description=description, color=color)
    await ctx.send(embed=embed)

# command: getserversjson
# get configs/servers.json
@bot.command(name='getserversjson')
@commands.is_owner()
async def _getsfile(ctx):
    await ctx.send(file=discord.File('configs/servers.json'))

# command: setserversjson
# set configs/servers.json
@bot.command(name='setserversjson')
@commands.is_owner()
async def _serverdel(ctx, *args):
    title = f'Command: {settings["prefix"]}setserversjson'
    color = discord.Color.from_rgb(114, 137, 218) # discord theme color

    if len(args) == 1:
        url = args[0]
        r = requests.get(url)
        with open('configs/servers.json', 'wb') as file:
            file.write(r.content)

        description=f'File servers.json uploaded'
        embed = discord.Embed(title=title, description=description, color=color)
        await ctx.send(embed=embed)
        return

    description=f'Usage: {settings["prefix"]}setserversjson <url>\nRemark: <url> is the servers.json download url'
    embed = discord.Embed(title=title, description=description, color=color)
    await ctx.send(embed=embed)

# run the bot
print('Starting bot...')
bot.run(TOKEN)
