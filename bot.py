import discord
from discord.ext import commands
import asyncio
import os
import json
import time
from dotenv import load_dotenv
from mcstatus import JavaServer
from mcrcon import MCRcon
import psutil
import threading
import random
from pathlib import Path
from itertools import cycle
import re 
import datetime
from discord import app_commands
from zoneinfo import available_timezones, ZoneInfo
from typing import Optional
import aiohttp


# Load environment
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

class BotState:
    status_channel_id = None
    server_start_time = time.time()

CONFIG = {
    "server_ip": None,
    "server_port": None,
    "rcon_port": None,
    "rcon_password": None,
    "config_file": "bot_config.json",
    "log_poll_interval": 1,
    "server_check_interval": 5,
    "guild_id": None
}

pending_purges = {}

DATA_DIR = "data"
LINKED_FILE = os.path.join("data", "linked_users.json")
REWARD_FILE = os.path.join("data", "daily_rewards.json")
CLAIMS_FILE = os.path.join("data", "daily_claims.json")

status_msgs = cycle([
    "Keeping eyes on creepers 👀",
    "Type /mcstatus for server stats 📊",
    "Snoopin' in the Nether? 🔥",
    "Fishing for lag... 🎣",
    "Looking for Herobrine 👻",
    "Feeding parrots cookies 🍪 (don't!)",
    "Mining bedrock with a wooden pickaxe 🪓 (wish me luck)",
    "Chopping wood like it’s a full-time job 🌲",
    "Listening for ghast screams in the distance 😱",
    "Smelting memes in the furnace 🔥",
    "Planting beets no one asked for 🥬",
    "Whispers: 'The cake is a lie...' 🍰",
    "Checking villager trades for soul-selling deals 🧑‍🌾",
    "Sniffing for diamonds 💎",
    "Stealing beds from villages 🛏️",
    "Avoiding eye contact with endermen 🙈",
    "Shaking llamas for answers 🦙",
    "Making deals with piglins 🔥💰",
    "Rewriting the redstone laws ⚙️",
    "Digging straight down like an absolute maniac 🕳️",
    "Lost in the stronghold again... 📜",
    "Converting creeper hisses into dubstep 💣🎵",
    "Farming XP like it's 2012 🧪",
    "Building a dirt mansion (again) 🏚️",
    "Bribing skeletons for better aim 🎯",
    "Dancing with phantoms at 3AM 🌌",
    "Snorting blaze powder for good luck 🧡",
    "Hiding behind obsidian like a pro 🧱",
    "Trying to ride a ghast 🚀",
    "Brewing coffee instead of potions ☕",
    "Speedrunning chores IRL... ⏱️",
    "Debugging chickens 🐔",
    "Slapping slimes for science 🧪",
    "Checking TPS — Totally Powerful Stats 😎",
    "Sending pigeons to Mojang with bug reports 🐦",
])

server_ready_messages = [
    "✅ Server is fully initialized! Time to craft greatness.",
    "🚀 Boot complete — join the adventure!",
    "🌟 The realm is ready. Enter if you dare!",
    "🎮 Server is online and accepting heroes.",
    "🟢 All systems go. You're clear to connect!",
    "🧱 Startup complete — blocks await!"
]

STREAK_SOUNDS = {
    1: "minecraft:block.note_block.pling",
    2: "minecraft:entity.experience_orb.pickup",
    3: "minecraft:entity.player.levelup",
    4: "minecraft:item.totem.use",
    5: "minecraft:ui.toast.challenge_complete",
    6: "minecraft:entity.ender_dragon.growl",
    7: "minecraft:entity.lightning_bolt.thunder"
}

FAREWELL_MESSAGES = [
    "👋 Server's gone to sleep — guess I will too. Bye everyone!",
    "🛑 Minecraft server powered off. Logging out until next time!",
    "💤 The server took a nap... so I'm outta here!",
    "🚪 Doors are shut, chunks unloaded. See you after the restart!",
    "😴 Server's offline — time for me to dream of pixel sheep.",
    "🌙 The night has fallen on the server... disconnecting now!",
    "🎮 Minecraft said 'bye', so I'm dipping too. Catch you later!",
    "📴 Server shutdown detected. Executing emergency nap protocol.",
    "🥾 The server pulled the plug — and kicked me offline with it!"
]

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------------- Helpers ----------------------

def save_config():
    config_to_save = {
        "server_ip": CONFIG["server_ip"],
        "server_port": CONFIG["server_port"],
        "rcon_port": CONFIG["rcon_port"],
        "rcon_password": CONFIG["rcon_password"],
        "guild_id": CONFIG["guild_id"],
        "status_channel_id": BotState.status_channel_id,
        "timezone": CONFIG.get("timezone", "UTC"),  # Default to UTC if not set
        "thread_id": CONFIG.get("thread_id"),
        "message_id": CONFIG.get("message_id")
    }
    with open(CONFIG["config_file"], "w") as f:
        json.dump(config_to_save, f, indent=4)

def load_config():
    if not os.path.exists(CONFIG["config_file"]):
        print("❌ Config file not found. Creating one with empty values.")
        save_config()
        return

    with open(CONFIG["config_file"], "r") as f:
        data = json.load(f)

    CONFIG["server_ip"] = data.get("server_ip")
    CONFIG["server_port"] = data.get("server_port")
    CONFIG["rcon_port"] = data.get("rcon_port")
    CONFIG["rcon_password"] = data.get("rcon_password")
    CONFIG["guild_id"] = data.get("guild_id")
    CONFIG["timezone"] = data.get("timezone", "UTC")  # Default to UTC if not set
    CONFIG["thread_id"] = data.get("thread_id")      
    CONFIG["message_id"] = data.get("message_id")
    BotState.status_channel_id = data.get("status_channel_id")

    # Validate essential settings
    missing = []
    for key in ["server_ip", "server_port", "rcon_port", "rcon_password"]:
        if not CONFIG[key]:
            missing.append(key)

    if missing:
        print(f"⚠️ Missing config values: {', '.join(missing)}")
        print("   ➤ Please fill them manually in bot_config.json or use a command like /setserverconfig")


def query_server():
    if not all([CONFIG["server_ip"], CONFIG["server_port"]]):
        print("❌ Cannot query server: IP or port missing from config.")
        return {"online": False, "error": "Missing server config"}
    try:
        status = JavaServer(CONFIG["server_ip"], CONFIG["server_port"]).status()
        return {
            "online": True,
            "players_online": status.players.online,
            "players_sample": getattr(status.players, "sample", []),
            "latency": round(status.latency),
            "motd": status.description
        }
    except Exception as e:
        return {"online": False, "error": str(e)}

def send_to_minecraft_chat(msg: str):
    try:
        with MCRcon(CONFIG["server_ip"], CONFIG["rcon_password"], port=CONFIG["rcon_port"]) as m:
            tellraw_json = json.dumps([
                {"text": "[Discord] ", "color": "blue", "bold": True},
                {"text": msg, "color": "gray"}
            ])
            m.command(f'tellraw @a {tellraw_json}')
        return True
    except Exception as e:
        print("❌ RCON error:", e)
        return False

def get_online_players_rcon():
    try:
        with MCRcon(CONFIG["server_ip"], CONFIG["rcon_password"], port=CONFIG["rcon_port"]) as m:
            response = m.command("list")
            print(f"📄 Full RCON Response: {response}")
            match = re.search(r"There are (\d+) of a max of \d+ players online(?:: (.*))?", response)
            if match:
                count = int(match.group(1))
                names = match.group(2) or ""
                name_list = [n.strip() for n in names.split(",")] if names else []
                return {"count": count, "names": name_list}
            else:
                return {"count": 0, "names": []}
    except Exception as e:
        print(f"❌ RCON player list error: {e}")
        return {"count": -1, "names": []}
    
def get_minecraft_start_time():
    log_path = Path("H:/Wanderlust Unbound Lite Server/logs/latest.log")
    if not log_path.exists():
        print(f"⚠️ Could not find latest.log at: {log_path}")
        return None

    try:
        with open(log_path, "r", encoding="utf-8") as file:
            for line in file:
                if "Done (" in line and "For help, type" in line:
                    # Match Forge-style timestamp: [19Jun2025 09:41:05.638]
                    match = re.search(r'\[(\d{2}[A-Za-z]{3}\d{4}) (\d{2}:\d{2}:\d{2})\.\d+\]', line)
                    if match:
                        date_str = match.group(1)
                        time_str = match.group(2)
                        full_str = f"{date_str} {time_str}"
                        try:
                            dt = datetime.datetime.strptime(full_str, "%d%b%Y %H:%M:%S")
                            return dt.timestamp()
                        except ValueError as ve:
                            print(f"⛔ Date parse error: {ve}")
                            return None
        print("⚠️ No server 'Done' line found in latest.log.")
        return None
    except Exception as e:
        print(f"❌ Error reading latest.log: {e}")
        return None
    
def check_server_ready():
    try:
        with MCRcon(CONFIG["server_ip"], CONFIG["rcon_password"], port=CONFIG["rcon_port"]) as m:
            response = m.command("list")
            return "There are" in response
    except Exception:
        return False

def start_server_watcher():
    def watch():
        while True:
            alive = any('java' in p.name().lower() for p in psutil.process_iter())
            if not alive:
                print("🛑 Server not found — shutting down bot.")
                asyncio.run_coroutine_threadsafe(bot.close(), bot.loop)
                break
            time.sleep(CONFIG["server_check_interval"])
    threading.Thread(target=watch, daemon=True).start()

async def get_minecraft_start_time_with_retry(delay=20):
    attempt = 1
    while True:
        log_time = get_minecraft_start_time()
        if log_time:
            return log_time
        print(f"⏳ Attempt {attempt}: Waiting for server to finish booting...")
        await asyncio.sleep(delay)
        attempt += 1


async def change_status():
    try:
        while True:
            await bot.change_presence(activity=discord.Game(next(status_msgs)))
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        print("🛑 change_status task was cancelled during shutdown.")
        return
    except (discord.ConnectionClosed, discord.HTTPException, aiohttp.ClientConnectionError) as e:
        print(f"⚠️ Connection lost while changing status: {e}")

async def wait_for_server_ready():
    await asyncio.sleep(10)

    if not BotState.status_channel_id:
        return

    channel = bot.get_channel(BotState.status_channel_id)
    if not channel:
        return

    dots = ["⏳", "🕐", "🕑", "🕒", "🕓", "🕔", "⌛"]
    booting_flairs = [
        "🔄 Checking server core...",
        "🚧 Calibrating dimensions...",
        "⚙️ Spinning up redstone...",
        "🌀 Warming up portals...",
        "📶 Pinging chunk loaders...",
        "🔧 Aligning circuits...",
    ]

    progress_msg = await channel.send("🔧 Booting up the server...")

    i = 0
    while True:
        if check_server_ready():
            # Update server start time from logs
            log_time = get_minecraft_start_time()
            if log_time:
                BotState.server_start_time = log_time
            else:
                print("⚠️ Could not determine actual server start time from log.")
                if BotState.server_start_time is None:
                    BotState.server_start_time = time.time()  # Fallback

            ready_text = f" **{random.choice(server_ready_messages)}**"
            await progress_msg.edit(content=ready_text)
            await progress_msg.add_reaction("🎉")
            break

        flair = random.choice(booting_flairs)
        dot = dots[i % len(dots)]
        await progress_msg.edit(content=f"{dot} {flair}")
        i += 1
        await asyncio.sleep(10)

async def monitor_server_shutdown():
    await bot.wait_until_ready()
    while True:
        try:
            status = query_server()
            if not status.get("online"):
                print("🔴 Detected server shutdown. Closing bot...")

                # 📢 Send farewell message to Discord if status channel is set
                if BotState.status_channel_id:
                    channel = bot.get_channel(BotState.status_channel_id)
                    if channel:
                        try:
                            goodbye = random.choice(FAREWELL_MESSAGES)
                            await channel.send(f"{goodbye}")
                        except Exception as e:
                            print(f"⚠️ Failed to send shutdown message: {e}")

                await bot.close()
                break
        except Exception as e:
            print(f"⚠️ Error checking server status: {e}")
        await asyncio.sleep(60)

def load_daily_data():
    if not os.path.exists(REWARD_FILE):
        print(f"⚠️ {REWARD_FILE} not found!")
        return {}
    with open(REWARD_FILE, "r") as f:
        try:
            data = json.load(f)
            print(f"📦 Loaded daily rewards: {data}")
            return data
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse {REWARD_FILE}: {e}")
            return {}

def save_daily_data(data):
    os.makedirs(os.path.dirname(REWARD_FILE), exist_ok=True)
    with open(REWARD_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_streak_info(username: str):
    now = datetime.datetime.now(datetime.timezone.utc)
    if not os.path.exists(CLAIMS_FILE):
        return True, 1, now, None

    with open(CLAIMS_FILE, "r") as f:
        claims = json.load(f)

    info = claims.get(username, {})
    last_claim = info.get("last_claim")
    streak = info.get("streak", 0)

    if last_claim:
        last_dt = datetime.datetime.fromisoformat(last_claim)
        delta = (now - last_dt).days
        if delta < 1:
            return False, streak, now, last_dt
        elif delta == 1:
            streak = min(streak + 1, 7)
        else:
            streak = 1
    else:
        streak = 1
        last_dt = None

    return True, streak, now, last_dt

# Update claim file
def update_streak_info(username: str, now: datetime.datetime, streak: int):
    if os.path.exists(CLAIMS_FILE):
        with open(CLAIMS_FILE, "r") as f:
            claims = json.load(f)
    else:
        claims = {}

    claims[username] = {
        "last_claim": now.isoformat(),
        "streak": streak
    }

    with open(CLAIMS_FILE, "w") as f:
        json.dump(claims, f, indent=2)

# Parse RCON list output
def parse_rcon_list_output(output: str):
    names = []
    if ":" in output:
        try:
            names = output.split(":")[1].strip().split(", ")
        except Exception:
            pass
    return {"names": names}

import random

def get_fancy_particle_commands(username: str) -> list[str]:
    sets = [
        #  Enchanting Theme
        [
            f"execute as {username} at {username} run particle minecraft:enchant ~ ~1 ~ 1 0.5 1 0.01 80 force",
            f"execute as {username} at {username} run particle minecraft:totem_of_undying ~ ~1 ~ 0.5 1 0.5 0.1 40 force"
        ],
        #  Celebration Theme
        [
            f"execute as {username} at {username} run particle minecraft:happy_villager ~ ~1 ~ 0.3 0.5 0.3 0.05 60 force",
            f"execute as {username} at {username} run particle minecraft:note ~ ~1 ~ 0.4 0.2 0.4 0.05 40 force"
        ],
        #  Nature Theme
        [
            f"execute as {username} at {username} run particle minecraft:composter ~ ~1 ~ 0.5 0.3 0.5 0.02 70 force",
            f"execute as {username} at {username} run particle minecraft:falling_leaf ~ ~1 ~ 0.6 0.6 0.6 0.03 50 force"
        ],
        #  Arcane Burst Theme
        [
            f"execute as {username} at {username} run particle minecraft:dragon_breath ~ ~1 ~ 0.5 1 0.5 0.1 60 force",
            f"execute as {username} at {username} run particle minecraft:portal ~ ~1 ~ 1 1 1 0.05 100 force"
        ]
    ]

    selected_set = random.choice(sets)
    return selected_set

def load_links():
    if not os.path.exists(LINK_FILE):
        return {}
    with open(LINK_FILE, "r") as f:
        return json.load(f)

def save_links(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LINK_FILE, "w") as f:
        json.dump(data, f, indent=4)

# Utility to get linked username
def get_linked_username(discord_id: int):
    if not os.path.exists(LINKED_FILE):
        return None
    with open(LINKED_FILE, "r") as f:
        linked = json.load(f)
    return linked.get(str(discord_id))

def set_linked_username(discord_id, mc_username):
    links = load_links()
    links[str(discord_id)] = mc_username
    save_links(links)


# ---------------------- Log Polling (MC → Discord) ----------------------

def handle_log_line(line):
    # Chat messages
    chat_match = re.search(r'<(.+?)> (.+)', line)
    if chat_match:
        player, msg = chat_match.groups()
        asyncio.run_coroutine_threadsafe(
            send_to_discord_chat(f"💬 **{player}**: {msg}"),
            bot.loop
        )
        return

    # Player joined
    join_match = re.search(r'\[.+\]: (.+) joined the game', line)
    if join_match:
        player = join_match.group(1)
        asyncio.run_coroutine_threadsafe(
            send_to_discord_chat(f"➕ **{player}** joined the game"),
            bot.loop
        )
        return

    # Player left
    leave_match = re.search(r'\[.+\]: (.+) left the game', line)
    if leave_match:
        player = leave_match.group(1)
        asyncio.run_coroutine_threadsafe(
            send_to_discord_chat(f"➖ **{player}** left the game"),
            bot.loop
        )
        return

    # Advancements (covering all 3 types: advancement, challenge, goal)
    adv_match = re.search(
        r'\[.+\]: (.+) has (?:made the advancement|completed the challenge|reached the goal) \[(.+)\]',
        line
    )
    if adv_match:
        player, advancement = adv_match.groups()
        asyncio.run_coroutine_threadsafe(
            send_to_discord_chat(f"🏅 **{player}** earned advancement **{advancement}**!"),
            bot.loop
        )
        return
    
    # Player death
    death_match = re.search(r'\[.+\]: (.+) (was|fell|drowned|died|blew up|tried|walked|hit|went|got|discovered|suffocated|starved|froze|experience|dropped).+', line)
    if death_match:
        message = death_match.group(0)
        # Strip log timestamp and prefixes to only get the death message
        clean_msg = re.sub(r'^\[.+\]: ', '', message)
        asyncio.run_coroutine_threadsafe(
            send_to_discord_chat(f"💀 {clean_msg}"),
            bot.loop
        )
    return

async def send_to_discord_chat(message):
    if BotState.status_channel_id:
        channel = bot.get_channel(BotState.status_channel_id)
        if channel:
            try:
                await channel.send(message)
            except Exception as e:
                print(f" Failed to send message to Discord: {e}")

def start_log_poller():
    log_path = Path("H:/Wanderlust Unbound Lite Server/logs/latest.log")
    if not log_path.exists():
        print(f" Could not find log file at: {log_path}")
        return

    def poll():
        print(f"📂 Polling log file: {log_path}")
        with open(log_path, "r", encoding="utf-8") as file:
            file.seek(0, os.SEEK_END)
            while True:
                try:
                    line = file.readline()
                    if line:
                        handle_log_line(line.strip())
                    else:
                        time.sleep(CONFIG["log_poll_interval"])
                except Exception as e:
                    print(f" Log read error: {e}")
                    time.sleep(5)

    threading.Thread(target=poll, daemon=True).start()

# ---------------------- Events ----------------------

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    if not hasattr(bot, "status_task"):
        bot.status_task = asyncio.create_task(change_status())
    load_config()

    # 🔒 Config safety check
    required_keys = ["server_ip", "server_port", "rcon_port", "rcon_password"]
    missing = [key for key in required_keys if not CONFIG.get(key)]
    if missing:
        print(f"⛔ Cannot continue: Missing required config values: {', '.join(missing)}")
        await bot.close()
        return

    try:
        # Sync global commands
        await bot.tree.sync()
        print("✅ Global slash commands synced.")

        # List global commands
        print("🌍 Global commands:")
        for cmd in bot.tree.get_commands():
            print(f" ├─ /{cmd.name} — {cmd.description}")

        # Also sync to test guild for instant availability
        if CONFIG["guild_id"]:
            guild = discord.Object(id=int(CONFIG["guild_id"]))
            await bot.tree.sync(guild=guild)
            print(f"✅ Slash commands also synced to test guild {CONFIG['guild_id']} for instant testing.")

            # List guild-specific commands
            guild_cmds = await bot.tree.fetch_commands(guild=guild)
            print(f"🛠️ Guild commands for {CONFIG['guild_id']}:")
            for cmd in guild_cmds:
                print(f" ├─ /{cmd.name} — {cmd.description}")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")

    # Send "starting up" message to channel if configured
    startup_msg = None
    if BotState.status_channel_id:
        print("📌 Status channel:", BotState.status_channel_id)
        channel = bot.get_channel(BotState.status_channel_id)
        if channel:
            try:
                startup_msg = await channel.send("⏳ Server is **starting up**, please wait...")
            except Exception as e:
                print(f"⚠️ Couldn't send startup message: {e}")

    # Wait for Minecraft server to fully boot
    log_time = await get_minecraft_start_time_with_retry()
    if log_time:
        BotState.server_start_time = log_time
        print(f"🕰️ Server start time (from log): {datetime.datetime.fromtimestamp(log_time)}")

        if startup_msg:
            try:
                await startup_msg.edit(content="✅ Minecraft server is already **online**!")
            except Exception as e:
                print(f"⚠️ Couldn't update startup message: {e}")
    else:
        print("⚠️ Could not determine server start time from log.")

    # Start background services
    start_server_watcher()
    start_log_poller()
    bot.loop.create_task(wait_for_server_ready())
    bot.loop.create_task(monitor_server_shutdown())

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)
    if BotState.status_channel_id and message.channel.id == BotState.status_channel_id:
        send_to_minecraft_chat(f"{message.author.display_name}: {message.clean_content}")

# ---------------------- Slash Commands ----------------------

# /mcstatus
@bot.tree.command(name="mcstatus", description="Check if the Minecraft server is online")
async def mcstatus(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    try:
        server = JavaServer(CONFIG["server_ip"], CONFIG["server_port"])
        status = server.status()
        latency = round(status.latency)
    except Exception as e:
        return await interaction.followup.send(
            embed=discord.Embed(
                title="🚫 Server Offline",
                description=f"🧯 Error: `{e}`\n_The gates remain sealed..._",
                color=discord.Color.red()
            )
        )

    try:
        with MCRcon(CONFIG["server_ip"], CONFIG["rcon_password"], port=CONFIG["rcon_port"]) as m:
            response = m.command("list")
            match = re.search(r"There are (\d+) of a max of \d+ players online(?:: (.*))?", response)
            if match:
                count = int(match.group(1))
                names = match.group(2) or ""
                name_list = [n.strip() for n in names.split(",")] if names else []
                names_text = ", ".join(name_list) if name_list else "None"
            else:
                count = 0
                names_text = "None"
    except Exception as e:
        count = "?"
        names_text = f"⚠️ Could not retrieve names: {e}"

    status_description = (
        random.choice([
            "🛌 The world slumbers, awaiting its heroes...",
            "🌌 The land is quiet... for now.",
            "📜 No adventurers stir. The story awaits.",
            "🌿 All is calm. Not a soul in sight..."
        ]) if count == 0 else random.choice([
            "⚔️ The world hums with life and purpose!",
            "🧭 Brave souls wander the wilderness...",
            "🔥 The battle rages on. Glory awaits!",
            "📦 The overworld stirs with movement!"
        ])
    )

    elapsed = int(time.time() - BotState.server_start_time)
    hours = elapsed // 3600
    minutes = (elapsed % 3600) // 60
    uptime_text = (
        "Just awakened from the void..." if hours == 0 and minutes == 0 else
        f"For {minutes} minute(s), the realm has held steady." if hours == 0 else
        f"For {hours} hour(s), the world has persisted." if minutes == 0 else
        f"The world has stood for {hours} hour(s) and {minutes} minute(s)."
    )

    embed = discord.Embed(
        title="📜 Server Status Report",
        description=status_description,
        color=discord.Color.green()
    )
    embed.add_field(name="🟢 Status", value="Online", inline=True)
    embed.add_field(name="👥 Adventurers Present", value=str(count), inline=True)
    embed.add_field(name="🧑‍🤝‍🧑 Names", value=names_text, inline=False)
    embed.add_field(name="🏓 Latency", value=f"{latency}ms", inline=True)
    embed.add_field(name="📜 Age of the World (Uptime)", value=uptime_text, inline=False)
    embed.set_footer(text=f"IP: {CONFIG['server_ip']}:{CONFIG['server_port']}")

    await interaction.followup.send(embed=embed)


# /motd
@bot.tree.command(name="motd", description="Get the Minecraft server's MOTD")
async def motd(interaction: discord.Interaction):
    res = query_server()
    if res["online"]:
        motd_clean = re.sub(r"§[0-9a-fklmnor]", "", str(res['motd']))
        await interaction.response.send_message(f"📝 MOTD: `{motd_clean}`")
    else:
        await interaction.response.send_message("❌ Cannot fetch MOTD — server offline.")


# /statushere
@bot.tree.command(name="statushere", description="Set this channel for Minecraft updates and chat")
async def statushere(interaction: discord.Interaction):
    BotState.status_channel_id = interaction.channel.id
    save_config()
    await interaction.response.send_message("📍 This channel is now my Minecraft status outlet!", ephemeral=True)


# /howtojoin
@bot.tree.command(name="howtojoin", description="Get instructions on how to join the Minecraft server")
async def howtojoin(interaction: discord.Interaction):
    thread_id = CONFIG.get("thread_id")
    message_id = CONFIG.get("message_id")

    if not message_id:
        await interaction.response.send_message(
            "❌ The join instructions message ID hasn't been configured yet.\nAsk an admin to use `/setserverconfig`.",
            ephemeral=True
        )
        return

    try:
        if thread_id:
            # 🧵 Fetch message from the specified thread
            thread = await bot.fetch_channel(thread_id)
            message = await thread.fetch_message(message_id)
        else:
            # 📥 Try to fetch from the status channel if available
            if not BotState.status_channel_id:
                raise ValueError("No thread or fallback channel defined.")
            channel = bot.get_channel(BotState.status_channel_id)
            if not channel:
                channel = await bot.fetch_channel(BotState.status_channel_id)
            message = await channel.fetch_message(message_id)

        content = message.content or "Instructions not found."

        embed = discord.Embed(
            title="🧭 How to Join the Minecraft Server",
            description=content,
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Let the adventure begin!")

        await interaction.user.send(embed=embed)
        await interaction.response.send_message("📬 I've sent you a DM with the join instructions!", ephemeral=True)

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I couldn't DM you. Please enable DMs from server members.", ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"⚠️ Failed to fetch instructions: `{e}`", ephemeral=True
        )

@bot.tree.command(name="setserverconfig", description="Set Minecraft server connection details and timezone")
@app_commands.describe(
    server_ip="Server IP address",
    server_port="Minecraft server port",
    rcon_port="RCON port",
    rcon_password="RCON password",
    guild_id="Discord server ID for syncing slash commands",
    timezone="Timezone (e.g., Asia/Manila)",
    thread_id="(Optional) Discord thread ID for /howtojoin message",
    message_id="(Optional) Discord message ID for /howtojoin message"
)
async def setserverconfig(
    interaction: discord.Interaction,
    server_ip: str,
    server_port: int,
    rcon_port: int,
    rcon_password: str,
    guild_id: str,
    timezone: str,
    thread_id: Optional[str] = None,
    message_id: Optional[str] = None
):
    #  Validate timezone
    if timezone not in available_timezones():
        await interaction.response.send_message(
            f"❌ Invalid timezone: `{timezone}`\n"
            f"See: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones",
            ephemeral=True
        )
        return

    #  Update config
    CONFIG["server_ip"] = server_ip
    CONFIG["server_port"] = server_port
    CONFIG["rcon_port"] = rcon_port
    CONFIG["rcon_password"] = rcon_password
    CONFIG["guild_id"] = int(guild_id)
    CONFIG["timezone"] = timezone

    # Optional
    if thread_id:
        CONFIG["thread_id"] = int(thread_id)
    else:
        CONFIG.pop("thread_id", None)

    if message_id:
        CONFIG["message_id"] = int(message_id)
    else:
        CONFIG.pop("message_id", None)

    try:
        await bot.tree.sync(guild=discord.Object(id=CONFIG["guild_id"]))
        response = f"✅ Configuration saved and commands synced to guild `{guild_id}`."
    except Exception as e:
        response = f"⚠️ Config saved, but sync failed: `{e}`"

    save_config()
    await interaction.response.send_message(response, ephemeral=True)

@bot.tree.command(name="purge", description="Mark messages older than X days for deletion (requires confirmation)")
async def purge(interaction: discord.Interaction, days: int):
    await interaction.response.defer(ephemeral=True)

    #  Admin check
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.followup.send("🚫 You need **Manage Messages** permission to use this command.", ephemeral=True)
        return

    if days < 1 or days > 30:
        await interaction.followup.send("❌ Please choose between 1 and 30 days.", ephemeral=True)
        return

    channel_id = BotState.status_channel_id
    if not channel_id:
        await interaction.followup.send("❌ Status channel is not set in config.", ephemeral=True)
        return

    pending_purges[interaction.user.id] = {
        "channel_id": channel_id,
        "days": days,
        "created": datetime.datetime.now(datetime.timezone.utc)
    }

    await interaction.followup.send(
        f"⚠️ Are you sure you want to purge messages older than **{days} day(s)** from <#{channel_id}>?\n"
        f"Run `/confirm_purge` within 60 seconds to proceed.",
        ephemeral=True
    )

@bot.tree.command(name="confirm_purge", description="Confirm the purge request")
async def confirm_purge(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if not interaction.user.guild_permissions.manage_messages:
        await interaction.followup.send("🚫 You need **Manage Messages** permission to confirm purges.", ephemeral=True)
        return

    request = pending_purges.get(interaction.user.id)
    if not request:
        await interaction.followup.send("❌ No pending purge request found or it expired.", ephemeral=True)
        return

    elapsed = (datetime.datetime.now(datetime.UTC) - request["created"]).total_seconds()
    if elapsed > 60:
        del pending_purges[interaction.user.id]
        await interaction.followup.send("⏰ Purge request expired. Please run `/purge` again.", ephemeral=True)
        return

    channel = bot.get_channel(request["channel_id"])
    if not channel:
        await interaction.followup.send("❌ Could not find the target channel.", ephemeral=True)
        return

    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=request["days"])
    now = datetime.datetime.now(datetime.timezone.utc)
    deleted = 0
    failed = 0
    to_delete = []

    # 🧹 Inform user we're starting
    progress_msg = await interaction.followup.send("⏳ Gathering messages to delete...", ephemeral=True)

    try:
        async for message in channel.history(limit=1000, oldest_first=False):
            if message.created_at < cutoff and not message.pinned:
                # Collect for bulk delete if less than 14 days old
                if (now - message.created_at).days < 14:
                    to_delete.append(message)
                else:
                    try:
                        await message.delete()
                        deleted += 1
                        await asyncio.sleep(1)
                    except discord.HTTPException:
                        failed += 1
                        await asyncio.sleep(2)

        # 🧹 Bulk delete supported messages
        if to_delete:
            try:
                # Bulk delete accepts up to 100 messages at once
                while to_delete:
                    batch = to_delete[:100]
                    await channel.delete_messages(batch)
                    deleted += len(batch)
                    to_delete = to_delete[100:]
                    await asyncio.sleep(2)
            except discord.HTTPException as e:
                await progress_msg.edit(content=f"⚠️ Bulk delete failed: `{e}`")

        await progress_msg.edit(content=(
            f"✅ Purge complete: **{deleted}** message(s) deleted."
            + (f"\n⚠️ {failed} message(s) couldn't be deleted." if failed else "")
        ))
    except Exception as e:
        await progress_msg.edit(content=f"❌ Error while purging: `{e}`")
    finally:
        del pending_purges[interaction.user.id]
        

@bot.tree.command(name="forcesync", description="Force re-sync of all commands")
async def forcesync(interaction: discord.Interaction):
    await bot.tree.sync(guild=discord.Object(id=int(CONFIG["guild_id"])))
    cmds = [cmd.name for cmd in bot.tree.get_commands()]
    await interaction.response.send_message(f"🔄 Synced commands: {', '.join(cmds)}", ephemeral=True)
#/daily
@bot.tree.command(name="daily", description="Claim your daily Minecraft login reward!")
async def daily(interaction: discord.Interaction):
    print("🔔 /daily command triggered")
    await interaction.response.defer(ephemeral=True)

    if interaction.channel.id != BotState.status_channel_id:
        print("❌ Wrong channel used")
        await interaction.followup.send("❌ Please use this command in the Minecraft status channel.", ephemeral=True)
        return

    username = get_linked_username(interaction.user.id)
    print(f"👤 Linked username: {username}")
    if not username:
        await interaction.followup.send("❌ You haven't linked your Minecraft username yet. Use `/linkmc`.", ephemeral=True)
        return

    can_claim, streak, now, last_claim = get_streak_info(username)
    print(f"✅ Streak info — Can Claim: {can_claim}, Streak: {streak}, Now: {now}, Last Claim: {last_claim}")

    if not can_claim:
        tz_name = CONFIG.get("timezone", "UTC")
        tz = ZoneInfo(tz_name)
        print(f"🕒 Claim denied — Using timezone: {tz_name}")

        if last_claim:
            next_claim_time = last_claim + datetime.timedelta(days=1)
            remaining = next_claim_time - now
            hours, remainder = divmod(int(remaining.total_seconds()), 3600)
            minutes = remainder // 60

            last_claim_local = last_claim.astimezone(tz)
            formatted_claim_time = last_claim_local.strftime('%Y-%m-%d %I:%M %p %Z')

            print(f"🕒 Last claim at: {formatted_claim_time}, Next claim in: {hours}h {minutes}m")
            await interaction.followup.send(
                f"🕒 You last claimed your daily reward on **{formatted_claim_time}**.\n"
                f"⏳ You can claim again in **{hours}h {minutes}m**.",
                ephemeral=True
            )
        else:
            print("🕒 No record of last claim")
            await interaction.followup.send("🕒 You've already claimed your daily reward recently.", ephemeral=True)
        return

    print("🎁 Loading reward info")
    daily_rewards = load_daily_data()
    reward_day = min(streak, 7)
    reward = daily_rewards.get(str(reward_day))

    if not reward:
        print(f"⚠️ No reward configured for day {reward_day}")
        await interaction.followup.send("⚠️ No reward configured for this day.", ephemeral=True)
        return

    item_id = reward["item"]
    amount = reward["amount"]
    sound = STREAK_SOUNDS.get(reward_day, "minecraft:entity.player.levelup")
    print(f"🎁 Reward for Day {streak}: {amount}x {item_id} | Sound: {sound}")

    try:
        print("🔌 Connecting to RCON")
        with MCRcon(CONFIG["server_ip"], CONFIG["rcon_password"], port=CONFIG["rcon_port"]) as m:
            print("✅ RCON connection successful")
            rcon_output = m.command("list")
            rcon_players = parse_rcon_list_output(rcon_output)["names"]
            print(f"🧍 Online players: {rcon_players}")

            if username.lower() not in [n.lower() for n in rcon_players]:
                print("❌ Player not online")
                await interaction.followup.send(
                    f"❌ You are not currently online in Minecraft as **{username}**.\nPlease join the server first.",
                    ephemeral=True
                )
                return

            try:
                print("⚙️ Giving reward")
                m.command("gamerule sendCommandFeedback false")
                m.command(f"execute as {username} run give {username} {item_id} {amount}")
                m.command(f"execute as {username} at {username} run playsound {sound} player {username} ~ ~ ~ 1 1")

                print("✨ Playing particles")
                for cmd in get_fancy_particle_commands(username):
                    m.command(cmd)

                print("📢 Broadcasting reward message")
                message_json = json.dumps([
                    {"text": "🎁 ", "color": "gold"},
                    {"text": f"{username}", "color": "yellow"},
                    {"text": " has claimed their daily reward: ", "color": "gold"},
                    {"text": f"{amount}x {item_id.replace('numismatic-overhaul:', '')}", "color": "aqua"},
                    {"text": "\nType ", "color": "gray"},
                    {"text": "/daily", "color": "blue"},
                    {"text": " in Discord to get yours.", "color": "gray"},
                    {"text": "\n(Link your account with ", "color": "dark_gray"},
                    {"text": "/linkmc <username>", "color": "blue"},
                    {"text": ")", "color": "dark_gray"}
                ])
                m.command(f'tellraw @a {message_json}')

            finally:
                print("✅ Re-enabling command feedback")
                m.command("gamerule sendCommandFeedback true")

        print("✅ Reward delivered successfully")
        await interaction.followup.send(
            f"🎉 You received **{amount}x `{item_id}`** for your **Day {streak}** login streak!",
            ephemeral=True
        )
        print("💾 Updating streak info")
        update_streak_info(username, now, streak)

    except Exception as e:
        print(f"❌ Failed to issue reward: {e}")
        await interaction.followup.send(f"❌ Failed to issue reward: `{e}`", ephemeral=True)

#/linkmc
@bot.tree.command(name="linkmc", description="Link your Discord account to your Minecraft username.")
@app_commands.describe(username="Your Minecraft username")
async def linkmc(interaction: discord.Interaction, username: str):
    await interaction.response.defer(ephemeral=True)

    filepath = "data/linked_users.json"
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(filepath):
        with open(filepath, "w") as f:
            json.dump({}, f)

    with open(filepath, "r") as f:
        linked_users = json.load(f)

    discord_id_str = str(interaction.user.id)
    prev = linked_users.get(discord_id_str)

    linked_users[discord_id_str] = username

    with open(filepath, "w") as f:
        json.dump(linked_users, f, indent=2)

    if prev and prev != username:
        await interaction.followup.send(
            f"🔁 Updated your linked Minecraft username from **{prev}** to **{username}**.", ephemeral=True)
    elif prev == username:
        await interaction.followup.send(f"🔗 You are already linked to **{username}**.", ephemeral=True)
    else:
        await interaction.followup.send(f"✅ Your Discord account is now linked to **{username}**!", ephemeral=True)

#helpme
@bot.tree.command(name="helpme", description="List all Wanderbot commands")
async def helpme(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    embed = discord.Embed(
        title="🎮 Wanderbot Command Guide",
        description="Here's a list of everything I can help you with!",
        color=discord.Color.gold()
    )

    # 🧍 General Player Commands
    embed.add_field(
        name="🧍 Player Commands",
        value=(
            "**`/linkmc <username>`** — Link your Minecraft username to your Discord.\n"
            "**`/daily`** — Claim your daily reward (must be online in Minecraft).\n"
            "**`/howtojoin`** — Get instructions on how to join the Minecraft server."
        ),
        inline=False
    )

    # 📊 Server Info
    embed.add_field(
        name="📊 Server Info",
        value=(
            "**`/mcstatus`** — Check if the Minecraft server is online.\n"
            "**`/motd`** — View the server's current message of the day (MOTD)."
        ),
        inline=False
    )

    # 🛠️ Admin & Config Commands
    embed.add_field(
        name="🛠️ Admin Commands",
        value=(
            "**`/setserverconfig`** — Set server IP, port, RCON password, and guild ID.\n"
            "**`/statushere`** — Set this channel to receive status updates.\n"
            "**`/purge <days>`** — Delete messages older than X days in this channel."
        ),
        inline=False
    )

    # 📘 Help Command
    embed.add_field(
        name="📘 Help",
        value="**`/helpme`** — Display this help message anytime.",
        inline=False
    )

    embed.set_footer(text="✨ Some commands require admin permissions or a linked Minecraft account.")

    await interaction.followup.send(embed=embed, ephemeral=True)

# ---------------------- Run ----------------------

async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
