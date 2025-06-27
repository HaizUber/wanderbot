import discord
from discord.ext import commands
import asyncio
import sys
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
from datetime import datetime, timezone, timedelta, date
from discord import app_commands
from zoneinfo import available_timezones, ZoneInfo
from typing import Optional
import aiohttp
import gzip
import logging
from logging.handlers import TimedRotatingFileHandler
import random
import base64
import traceback
import io

# Load environment
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

os.makedirs("logs", exist_ok=True)  # Make sure 'logs/' folder exists

# Configure the bot logger with daily log rotation
logger = logging.getLogger()
logger.setLevel(logging.INFO)

formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')

# Daily rotating file handler: creates new log at midnight, keeps last 7 logs
file_handler = TimedRotatingFileHandler(
    filename="logs/bot.log",
    when="midnight",
    interval=1,
    backupCount=7,
    encoding="utf-8",
    utc=False
)
file_handler.suffix = "%Y-%m-%d"
file_handler.extMatch = re.compile(r"^\d{4}-\d{2}-\d{2}$")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Also log to console
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

class BotState:
    status_channel_id = None
    server_start_time = time.time()
    server_is_online = False

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

DATA_DIR = "data"
LINKED_FILE = os.path.join("data", "linked_users.json")
REWARD_FILE = os.path.join("data", "daily_rewards.json")
CLAIMS_FILE = os.path.join("data", "daily_claims.json")
START_TIME_CACHE_FILE = os.path.join("data", "last_server_start.json")

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

tz_name = CONFIG.get("timezone", "UTC")
tz = ZoneInfo(tz_name)

# Build today's 6:00 AM in that timezone
now_utc = datetime.now(timezone.utc)
today_local = now_utc.astimezone(tz)
reset_time_local = today_local.replace(hour=6, minute=0, second=0, microsecond=0)

# If it's past 6 AM already today, use tomorrow's reset time
if today_local >= reset_time_local:
    reset_time_local += timedelta(days=1)

# Format: 6:00 AM PHT / 6:00 AM PST / etc.
formatted_reset_time = reset_time_local.strftime("%I:%M %p %Z")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------------- Helpers ----------------------

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        # Allow Ctrl+C to pass through cleanly
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Log to main logger
    logger.critical("❌ Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    # Optional: also dump to separate crash log
    try:
        crash_dir = "logs/crashes"
        os.makedirs(crash_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        crash_file = os.path.join(crash_dir, f"crash_{timestamp}.log")

        with open(crash_file, "w", encoding="utf-8") as f:
            f.write("❌ Uncaught Exception:\n\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)

        logger.info(f"🧨 Crash details saved to {crash_file}")
    except Exception as e:
        logger.error(f"⚠️ Failed to write crash log: {e}")

def clear_server_start_cache():
    try:
        if os.path.exists(START_TIME_CACHE_FILE):
            os.remove(START_TIME_CACHE_FILE)
            logger.info("🗑️ Cleared server start cache.")
    except Exception as e:
        logger.error(f"❌ Failed to clear cache: {e}")

def save_server_start_time(timestamp):
    try:
        os.makedirs("data", exist_ok=True)
        with open(START_TIME_CACHE_FILE, "w") as f:
            json.dump({"timestamp": timestamp}, f)
        logger.info(f"🕰️ Cached server start time: {timestamp}")
    except Exception as e:
        logger.error(f"❌ Failed to save server start time: {e}")

def load_cached_server_start_time():
    try:
        if os.path.exists(START_TIME_CACHE_FILE):
            with open(START_TIME_CACHE_FILE, "r") as f:
                data = json.load(f)
                ts = data.get("timestamp")

                if ts:
                    boot_time = datetime.fromtimestamp(ts)
                    now = datetime.now()

                    # Invalidate cache older than 15 minutes or from a different day
                    if (now - boot_time).total_seconds() > 900 or now.date() != boot_time.date():
                        logger.warning("⚠️ Cached server start time is stale or outdated. Ignoring.")
                        return None

                    logger.info(f"📦 Loaded fresh cached server start time: {ts}")
                    return ts
    except Exception as e:
        logger.error(f"❌ Failed to read server start time cache: {e}")
    return None

def save_config():
    config_to_save = {
        "server_ip": CONFIG.get("server_ip"),
        "server_port": CONFIG.get("server_port"),
        "rcon_port": CONFIG.get("rcon_port"),
        "rcon_password": CONFIG.get("rcon_password"),
        "guild_id": CONFIG.get("guild_id"),
        "status_channel_id": BotState.status_channel_id,
        "timezone": CONFIG.get("timezone", "UTC"),
        "thread_id": CONFIG.get("thread_id"),
        "message_id": CONFIG.get("message_id"),
        "server_check_interval": CONFIG.get("server_check_interval", 5)
    }

    config_path = CONFIG["config_file"]
    backup_path = config_path + ".bak"
    temp_path = config_path + ".tmp"

    try:
        # Write to temporary file first
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(config_to_save, f, indent=4)
        
        # Backup old config
        if os.path.exists(config_path):
            os.replace(config_path, backup_path)
            logger.info(f"📦 Backup created: {backup_path}")
        
        # Move temp file to actual config
        os.replace(temp_path, config_path)
        logger.info(f"📝 Config saved successfully to {config_path}")

    except Exception as e:
        logger.error(f"❌ Failed to save config to {config_path}: {e}")
        # Cleanup temp file on failure
        if os.path.exists(temp_path):
            os.remove(temp_path)

def load_config():
    config_file = CONFIG["config_file"]

    if not os.path.exists(config_file):
        logger.warning("⚠️ Config file not found. Creating a new one with default values...")
        save_config()
        return

    try:
        with open(config_file, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.critical(f"⛔ Failed to parse config file '{config_file}': {e}")
        logger.info("🔁 Backing up corrupt file and generating a new one...")
        os.rename(config_file, config_file + ".backup")
        save_config()
        return
    except Exception as e:
        logger.error(f"❌ Unexpected error reading config: {e}")
        return

    # Define expected schema
    expected_fields = {
        "server_ip": None,
        "server_port": None,
        "rcon_port": None,
        "rcon_password": None,
        "guild_id": None,
        "timezone": "UTC",
        "thread_id": None,
        "message_id": None,
        "status_channel_id": None,
        "server_check_interval": 60
    }

    # Load all values using defaults when missing
    for key, default in expected_fields.items():
        CONFIG[key] = data.get(key, default)
        if key == "status_channel_id":
            BotState.status_channel_id = CONFIG[key]

    BotState.last_server_start_time = None

    # Detect and log missing critical fields
    required = ["server_ip", "server_port", "rcon_port", "rcon_password"]
    missing = [k for k in required if not CONFIG.get(k)]
    if missing:
        logger.warning(f"⚠️ Missing critical config values: {', '.join(missing)}")
        logger.info("🔧 You can update them manually or use /setserverconfig")
    else:
        logger.info("✅ Configuration loaded successfully.")

def is_rcon_alive(wait_until_online=False, delay=5):
    attempt = 1
    while True:
        try:
            with MCRcon(CONFIG["server_ip"], CONFIG["rcon_password"], port=int(CONFIG["rcon_port"])) as mcr:
                response = mcr.command("list")
                if response:
                    return True
                else:
                    logger.warning("⚠️ RCON responded but returned empty.")
                    if not wait_until_online:
                        return False
        except Exception as e:
            logger.debug(f"⏳ Attempt {attempt}: RCON not ready ({e})")
            if not wait_until_online:
                return False

        logger.info(f"🔄 Retrying RCON connection in {delay} seconds...")
        time.sleep(delay)
        attempt += 1

def query_server(wait_until_online=False, delay=5):
    if not CONFIG.get("server_ip") or not CONFIG.get("server_port"):
        logger.error("❌ Cannot query server: Missing IP or port in config.")
        return {"online": False, "error": "Missing server config"}

    attempt = 1
    while True:
        try:
            server = JavaServer(CONFIG["server_ip"], CONFIG["server_port"])
            status = server.status()
            logger.info(f"✅ Server is online. {status.players.online} player(s) currently.")
            return {
                "online": True,
                "players_online": status.players.online,
                "players_sample": getattr(status.players, "sample", []),
                "latency": round(status.latency),
                "favicon": getattr(status, "favicon", None),  #  Safe access
                "motd": getattr(status, "description", "No MOTD")  
            }

        except Exception as e:
            if wait_until_online:
                logger.debug(f"⏳ Attempt {attempt}: Server query failed ({e})")
                logger.info(f"🔄 Retrying query in {delay} seconds...")
                time.sleep(delay)
                attempt += 1
            else:
                logger.error(f"❌ Server query failed: {e}")
                return {"online": False, "error": str(e)}

def send_to_minecraft_chat(msg: str) -> bool:
    if not all([CONFIG.get("server_ip"), CONFIG.get("rcon_port"), CONFIG.get("rcon_password")]):
        logger.error("❌ Missing RCON configuration. Cannot send message to Minecraft chat.")
        return False

    try:
        with MCRcon(CONFIG["server_ip"], CONFIG["rcon_password"], port=int(CONFIG["rcon_port"])) as m:
            tellraw_json = json.dumps([
                {"text": "[Discord] ", "color": "blue", "bold": True},
                {"text": msg, "color": "gray"}
            ])
            m.command(f'tellraw @a {tellraw_json}')
            logger.info(f"📨 Sent message to Minecraft chat: {msg}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to send RCON message: {e}")
        return False

def get_online_players_rcon():
    if not all([CONFIG.get("server_ip"), CONFIG.get("rcon_port"), CONFIG.get("rcon_password")]):
        logger.error("❌ Missing RCON configuration. Cannot fetch online players.")
        return {"count": -1, "names": []}

    try:
        with MCRcon(CONFIG["server_ip"], CONFIG["rcon_password"], port=int(CONFIG["rcon_port"])) as m:
            response = m.command("list")
            logger.debug(f"📄 Full RCON Response: {response}")

            match = re.search(r"There are (\d+) of a max of \d+ players online(?:: (.*))?", response)
            if match:
                count = int(match.group(1))
                names = match.group(2)
                name_list = [n.strip() for n in names.split(",")] if names else []
                logger.info(f"👥 Online players via RCON: {count} — {name_list}")
                return {"count": count, "names": name_list}
            else:
                logger.warning("⚠️ Could not parse RCON player list response.")
                return {"count": 0, "names": []}
    except Exception as e:
        logger.error(f"❌ RCON player list error: {e}")
        return {"count": -1, "names": []}
    
def get_minecraft_start_time():
    # ✅ Use cached start time if available
    cached = load_cached_server_start_time()
    if cached:
        logger.info(f"📦 Loaded cached server start time: {cached}")
        return cached

    # 🧾 Continue with log scanning...
    log_dir = Path("H:/Wanderlust Unbound Lite Server/logs")
    log_files = sorted(log_dir.glob("*.log*"), key=os.path.getmtime, reverse=True)

    def extract_start_time_from_log(path: Path):
        try:
            is_gzip = path.suffix == ".gz"
            open_func = gzip.open if is_gzip else open
            mode = "rt" if is_gzip else "r"

            with open_func(path, mode, encoding="utf-8", errors="replace") as file:
                for line in file:
                    if "Done (" in line and "For help, type" in line:
                        match = re.search(r'\[(\d{2}[A-Za-z]{3}\d{4}) (\d{2}:\d{2}:\d{2})\.\d+\]', line)
                        if match:
                            full_str = f"{match.group(1)} {match.group(2)}"
                            try:
                                dt = datetime.strptime(full_str, "%d%b%Y %H:%M:%S")
                                logger.info(f"🕰️ Boot time found in {path.name}: {full_str}")
                                save_server_start_time(dt.timestamp())
                                return dt.timestamp()
                            except ValueError as ve:
                                logger.warning(f"⛔ Date parse error in {path.name}: {ve}")
        except Exception as e:
            logger.error(f"❌ Error reading {path.name}: {e}")
        return None

    logger.info("🔎 Searching for server start time in recent logs...")
    for log_path in log_files[:5]:
        logger.debug(f"🔍 Scanning log file: {log_path.name}")
        timestamp = extract_start_time_from_log(log_path)
        if timestamp:
            return timestamp

    logger.warning("🔁 Falling back to RCON...")
    try:
        with MCRcon(CONFIG["server_ip"], CONFIG["rcon_password"], port=int(CONFIG["rcon_port"])) as m:
            response = m.command("list")
            if response:
                now = datetime.now().timestamp()
                save_server_start_time(now)
                return now
    except Exception as e:
        logger.error(f"❌ RCON fallback failed: {e}")

    logger.error("❌ Unable to determine server start time.")
    return None
    
def check_server_ready():
    try:
        with MCRcon(CONFIG["server_ip"], CONFIG["rcon_password"], port=CONFIG["rcon_port"]) as m:
            response = m.command("list")
            if "There are" in response:
                logger.info("✅ Server is ready (RCON responded with player list).")
                return True
            else:
                logger.warning(f"⚠️ Unexpected RCON response: {response}")
                return False
    except Exception as e:
        logger.warning(f"❌ RCON check failed while checking server readiness: {e}")
        return False

def start_server_watcher():
    def watch():
        logger.info("👁️ Started server process watcher thread.")
        while True:
            try:
                alive = any('java' in p.name().lower() for p in psutil.process_iter())
                if not alive:
                    logger.warning("🛑 Minecraft server process not found — shutting down bot.")
                    asyncio.run_coroutine_threadsafe(bot.close(), bot.loop)
                    break
                time.sleep(CONFIG["server_check_interval"])
            except Exception as e:
                logger.error(f"❌ Error in server watcher: {e}")
                time.sleep(5)  # prevent tight loop on failure
    threading.Thread(target=watch, daemon=True).start()

async def get_minecraft_start_time_with_retry(delay=20, max_attempts=None):
    start_wait = time.time()
    attempt = 1

    while True:
        log_time = get_minecraft_start_time()
        if log_time:
            BotState.server_start_time = log_time
            duration = int(time.time() - start_wait)
            logger.info(f"✅ Server start time retrieved on attempt {attempt} after {duration} seconds.")

            if BotState.status_channel_id:
                channel = bot.get_channel(BotState.status_channel_id)
                if channel:
                    try:
                        await channel.send(
                            f"🟢 Server boot complete! \n"
                            f"⏱️ Boot duration: `{duration}` seconds."
                        )
                    except Exception as e:
                        logger.error(f"❌ Failed to send boot time to Discord: {e}")

            return log_time

        logger.warning(f"⏳ Attempt {attempt}: Waiting for server to finish booting...")
        await asyncio.sleep(delay)
        attempt += 1

        if max_attempts is not None and attempt > max_attempts:
            logger.error("❌ Max attempts reached. Could not determine server start time.")
            clear_server_start_cache()

            if BotState.status_channel_id:
                channel = bot.get_channel(BotState.status_channel_id)
                if channel:
                    try:
                        await channel.send(
                            f"❌ Failed to determine server start time after `{attempt - 1}` attempts.\n"
                            f"🧼 Cache cleared — retry manually or check the log."
                        )
                    except Exception as e:
                        logger.error(f"❌ Failed to send failure message to Discord: {e}")

            return None

async def change_status():
    backoff = 5  # seconds
    try:
        while True:
            try:
                new_status = next(status_msgs)
                await bot.change_presence(activity=discord.Game(new_status))
                logger.debug(f"🔄 Updated status: {new_status}")
                await asyncio.sleep(60)
            except (discord.ConnectionClosed, discord.HTTPException, aiohttp.ClientConnectionError) as e:
                logger.warning(f"⚠️ Discord status update failed: {e}. Retrying in {backoff}s...")
                await asyncio.sleep(backoff)
    except asyncio.CancelledError:
        logger.info("🛑 change_status task was cancelled during shutdown.")
    except Exception as e:
        logger.error(f"❌ Unexpected error in change_status: {e}", exc_info=True)

async def wait_for_server_ready():
    clear_server_start_cache()
    await asyncio.sleep(10)

    if not BotState.status_channel_id:
        logger.warning("⚠️ Status channel ID not set. Cannot announce server status.")
        return

    channel = bot.get_channel(BotState.status_channel_id)
    if not channel:
        logger.warning(f"⚠️ Could not get channel with ID {BotState.status_channel_id}")
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
    logger.info("🚀 Server boot process started...")

    i = 0
    boot_start_time = time.time()

    while True:
        if check_server_ready():
            log_time = get_minecraft_start_time()
            if log_time:
                BotState.server_start_time = log_time
                readable = datetime.fromtimestamp(log_time).strftime("%Y-%m-%d %H:%M:%S")
                await channel.send(f"🟢 Minecraft server boot completed at `{readable}`")
                logger.info(f"✅ Server successfully booted at: {readable}")
            else:
                fallback_time = time.time()
                BotState.server_start_time = fallback_time
                logger.warning("⚠️ Could not determine actual server start time from log. Using fallback time.")
                await channel.send("⚠️ Server booted, but log time could not be determined. Using fallback.")

            # ⏱️ Boot duration
            duration = time.time() - boot_start_time
            mins, secs = divmod(int(duration), 60)
            logger.info(f"🕰️ Server boot duration: {mins}m {secs}s")
            await channel.send(f"🕰️ Boot time: **{mins}m {secs}s**")

            # 🎉 Finalize
            ready_text = f"**{random.choice(server_ready_messages)}**"
            await progress_msg.edit(content=ready_text)
            await progress_msg.add_reaction("🎉")

            bot.loop.create_task(monitor_server_shutdown())
            break

        flair = random.choice(booting_flairs)
        dot = dots[i % len(dots)]
        await progress_msg.edit(content=f"{dot} {flair}")
        i += 1
        await asyncio.sleep(10)

async def restart_bot_after_midnight_once():
    await bot.wait_until_ready()

    today = date.today()
    already_restarted = False

    while True:
        now = datetime.now()

        # ⏱️ Between 12:00:05 AM and 12:01:00 AM, restart if not yet done
        if now.hour == 0 and now.minute == 0 and now.second >= 5 and not already_restarted:
            logger.info("🕛 Triggering bot restart after midnight to reattach to new latest.log.")

            if BotState.status_channel_id:
                channel = bot.get_channel(BotState.status_channel_id)
                if channel:
                    try:
                        await channel.send("🔄 Restarting bot after midnight to reattach to new `latest.log`.")
                        logger.info("📢 Sent restart notice to Discord.")
                    except Exception as e:
                        logger.warning(f"⚠️ Could not send restart notice to Discord: {e}")

            await asyncio.sleep(1)  # Let Discord send the message
            logger.info("🔁 Executing self-restart via os.execv()")
            os.execv(sys.executable, [sys.executable] + sys.argv)

        # 🔁 Reset the restart flag if the date has changed
        if now.date() != today:
            today = now.date()
            already_restarted = False
            logger.info("📅 Date changed — reset midnight restart flag.")

        await asyncio.sleep(1)

async def monitor_server_shutdown():
    await bot.wait_until_ready()
    logger.info("👁️ Started monitoring for server shutdown...")

    check_interval = CONFIG.get("server_check_interval", 5)
    seen_server_online_once = False
    BotState.server_is_online = False

    while True:
        try:
            status = query_server()
            server_offline = not status.get("online")
            rcon_offline = not is_rcon_alive()

            # ✅ Server is reachable by ping or RCON
            if not server_offline or not rcon_offline:
                if not BotState.server_is_online:
                    logger.info("🟢 Server is back online.")
                BotState.server_is_online = True

                if not seen_server_online_once:
                    seen_server_online_once = True
                    logger.info("✅ First confirmed server online state. Beginning shutdown monitoring.")

            # 🔴 Server is fully unreachable
            elif seen_server_online_once:  # 🔧 Only shut down *after* we've confirmed it was online once
                if BotState.server_is_online:
                    logger.info("🔴 Server is now unreachable (RCON + ping failed).")

                BotState.server_is_online = False

                # Send shutdown message to Discord
                if BotState.status_channel_id:
                    channel = bot.get_channel(BotState.status_channel_id)
                    if channel:
                        try:
                            goodbye = random.choice(FAREWELL_MESSAGES)
                            await channel.send(goodbye)
                            logger.info("📤 Sent farewell shutdown message to Discord.")
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to send shutdown message to Discord: {e}")

                logger.info("🛑 Closing bot due to immediate server shutdown...")
                await bot.close()
                break

            else:
                logger.info("⏳ Waiting for first successful server contact...")

        except Exception as e:
            logger.error(f"❌ Exception in server shutdown monitor: {e}", exc_info=True)

        await asyncio.sleep(check_interval)

def load_daily_data():
    if not os.path.exists(REWARD_FILE):
        logger.warning(f"⚠️ Reward file not found: {REWARD_FILE}")
        return {}

    try:
        with open(REWARD_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info(f"📦 Loaded daily rewards ({len(data)} entries)")
            return data
    except json.JSONDecodeError as e:
        logger.error(f"❌ Failed to parse {REWARD_FILE}: {e}")
        # Backup corrupt file
        backup_path = REWARD_FILE + ".corrupt"
        try:
            os.rename(REWARD_FILE, backup_path)
            logger.warning(f"📦 Corrupt reward file backed up to {backup_path}")
        except Exception as backup_error:
            logger.error(f"❌ Failed to backup corrupt reward file: {backup_error}")
        return {}
    except Exception as e:
        logger.exception(f"❌ Unexpected error loading {REWARD_FILE}")
        return {}

def save_daily_data(data):
    os.makedirs(os.path.dirname(REWARD_FILE), exist_ok=True)
    temp_path = REWARD_FILE + ".tmp"
    backup_path = REWARD_FILE + ".bak"

    try:
        # Write to a temporary file first
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        
        # Backup current file if it exists
        if os.path.exists(REWARD_FILE):
            os.replace(REWARD_FILE, backup_path)
            logger.info(f"📦 Backup of previous reward file created: {backup_path}")
        
        # Replace original with new temp file
        os.replace(temp_path, REWARD_FILE)
        logger.info(f"✅ Daily rewards saved to {REWARD_FILE} ({len(data)} entries)")
    
    except Exception as e:
        logger.error(f"❌ Failed to save daily rewards to {REWARD_FILE}: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)

def get_streak_info(username: str):
    tz_name = CONFIG.get("timezone", "UTC")
    tz = ZoneInfo(tz_name)

    now = datetime.now(timezone.utc).astimezone(tz)
    today_6am = now.replace(hour=6, minute=0, second=0, microsecond=0)
    if now < today_6am:
        today_6am -= timedelta(days=1)

    if not os.path.exists(CLAIMS_FILE):
        logger.warning(f"⚠️ Claims file not found: {CLAIMS_FILE}")
        return True, 1, now, None

    try:
        with open(CLAIMS_FILE, "r", encoding="utf-8") as f:
            claims = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"❌ Failed to parse claims file: {e}")
        return True, 1, now, None
    except Exception as e:
        logger.error(f"❌ Error loading claims file: {e}")
        return True, 1, now, None

    info = claims.get(username, {})
    last_claim = info.get("last_claim")
    streak = info.get("streak", 0)

    last_dt = None
    if last_claim:
        try:
            last_dt = datetime.fromisoformat(last_claim).astimezone(tz)

            last_6am = last_dt.replace(hour=6, minute=0, second=0, microsecond=0)
            if last_dt < last_6am:
                last_6am -= timedelta(days=1)

            # Already claimed today
            if last_6am >= today_6am:
                return False, streak, now, last_dt

            # Continue streak if claimed yesterday
            days_between = (today_6am.date() - last_6am.date()).days
            if days_between == 1:
                streak = min(streak + 1, 7)
            else:
                streak = 1

        except ValueError:
            logger.warning(f"⚠️ Invalid last_claim format for user {username}: {last_claim}")
            streak = 1
    else:
        streak = 1

    return True, streak, now, last_dt

def update_streak_info(username: str, now: datetime, streak: int):
    os.makedirs(os.path.dirname(CLAIMS_FILE), exist_ok=True)

    # Load existing data or initialize
    claims = {}
    if os.path.exists(CLAIMS_FILE):
        try:
            with open(CLAIMS_FILE, "r", encoding="utf-8") as f:
                claims = json.load(f)
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ Claims file corrupted, overwriting: {e}")
        except Exception as e:
            logger.error(f"❌ Error reading {CLAIMS_FILE}: {e}")

    # Update user's claim info
    claims[username] = {
        "last_claim": now.isoformat(),
        "streak": streak
    }

    # Safe write via temp file
    tmp_path = CLAIMS_FILE + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(claims, f, indent=2)

        os.replace(tmp_path, CLAIMS_FILE)
        logger.info(f"✅ Updated streak for {username}: streak={streak}, time={now.isoformat()}")
    except Exception as e:
        logger.error(f"❌ Failed to save claims to {CLAIMS_FILE}: {e}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def parse_rcon_list_output(output: str):
    """
    Parses RCON 'list' command output and logs raw output.
    Example input:
        "There are 2 of a max of 20 players online: Player1, Player2"

    Returns:
        {
            "count": int (online players),
            "names": list of str (player names)
        }
    """
    logger.debug(f"📡 Raw RCON list output: '{output}'")

    try:
        match = re.search(r"There are (\d+) of a max of \d+ players online(?:: (.*))?", output)
        if match:
            count = int(match.group(1))
            names_str = match.group(2)
            names = [n.strip() for n in names_str.split(",")] if names_str else []
            logger.info(f"👥 Parsed {count} player(s): {names}")
            return {"count": count, "names": names}
        else:
            logger.warning(f"⚠️ Could not parse player count from output: '{output}'")
            return {"count": -1, "names": []}
    except Exception as e:
        logger.error(f"❌ Failed to parse RCON list output: {e}")
        return {"count": -1, "names": []}

def get_fancy_particle_commands(username: str) -> list[str]:
    sets = [
        # ✨ Enchanting Theme
        [
            f"execute as {username} at {username} run particle minecraft:enchant ~ ~1 ~ 1 0.5 1 0.01 80 force",
            f"execute as {username} at {username} run particle minecraft:totem_of_undying ~ ~1 ~ 0.5 1 0.5 0.1 40 force"
        ],
        # 🎉 Celebration Theme
        [
            f"execute as {username} at {username} run particle minecraft:happy_villager ~ ~1 ~ 0.3 0.5 0.3 0.05 60 force",
            f"execute as {username} at {username} run particle minecraft:note ~ ~1 ~ 0.4 0.2 0.4 0.05 40 force"
        ],
        # 🍃 Nature Theme
        [
            f"execute as {username} at {username} run particle minecraft:composter ~ ~1 ~ 0.5 0.3 0.5 0.02 70 force",
            f"execute as {username} at {username} run particle minecraft:falling_leaf ~ ~1 ~ 0.6 0.6 0.6 0.03 50 force"
        ],
        # 🌀 Arcane Burst Theme
        [
            f"execute as {username} at {username} run particle minecraft:dragon_breath ~ ~1 ~ 0.5 1 0.5 0.1 60 force",
            f"execute as {username} at {username} run particle minecraft:portal ~ ~1 ~ 1 1 1 0.05 100 force"
        ],
        # 🎆 Fireworks (Safe Visual Only)
        [
            f"execute as {username} at {username} run particle minecraft:firework ~ ~2 ~ 0.2 0.2 0.2 0 1 force",
            f"execute as {username} at {username} run particle minecraft:flash ~ ~1 ~ 0 0 0 0 1 force"
        ],
        # ❄️ Ice/Crystal Theme
        [
            f"execute as {username} at {username} run particle minecraft:snowflake ~ ~1 ~ 0.5 0.5 0.5 0.03 50 force",
            f"execute as {username} at {username} run particle minecraft:end_rod ~ ~1 ~ 0.2 0.2 0.2 0.01 70 force"
        ],
        # ⚡ Tech Sparks Theme
        [
            f"execute as {username} at {username} run particle minecraft:crit ~ ~1 ~ 0.5 0.5 0.5 0.05 80 force",
            f"execute as {username} at {username} run particle minecraft:instant_effect ~ ~1 ~ 0.2 0.2 0.2 0.05 50 force"
        ]
    ]

    try:
        selected_set = random.choice(sets)
        logger.debug(f"✨ Selected particle set for {username}: {selected_set}")
        return selected_set
    except Exception as e:
        logger.error(f"❌ Failed to generate particle commands for {username}: {e}")
        return []

def load_links():
    if not os.path.exists(LINKED_FILE):
        return {}
    with open(LINKED_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to load linked users: {e}")
            return {}

def save_links(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LINKED_FILE, "w") as f:
        json.dump(data, f, indent=4)

# Utility to get linked username from Discord user ID
def get_linked_username(discord_id: int):
    links = load_links()
    return links.get(str(discord_id))

# Set (or update) linked username
def set_linked_username(discord_id: int, mc_username: str):
    links = load_links()
    links[str(discord_id)] = mc_username
    save_links(links)
    logger.info(f"🔗 Linked Discord ID {discord_id} to Minecraft user '{mc_username}'")

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
    
    # Player death (improved match for typical and custom death messages)
    death_match = re.search(
        r'\[Server thread/INFO\] \[minecraft/MinecraftServer\]: ([\w\d_]+) (was|fell|drowned|died|blew up|tried|walked|hit|went|got|discovered|suffocated|starved|froze|burned|shot|killed|crashed|squashed|impaled|froze to death)(.*)',
        line
    )
    if death_match:
        clean_msg = re.search(r'\[minecraft/MinecraftServer\]: (.+)', line)
        if clean_msg:
            asyncio.run_coroutine_threadsafe(
                send_to_discord_chat(f"💀 {clean_msg.group(1)}"),
                bot.loop
            )
        return

async def send_to_discord_chat(message: str):
    if not BotState.status_channel_id:
        logger.warning("⚠️ No status channel ID set — cannot send message.")
        return

    channel = bot.get_channel(BotState.status_channel_id)
    if not channel:
        logger.warning(f"⚠️ Channel with ID {BotState.status_channel_id} not found.")
        return

    try:
        await channel.send(message)
        logger.info(f"✅ Sent message to Discord: {message}")
    except discord.Forbidden:
        logger.error(f"🚫 Missing permissions to send messages in channel {channel.id}.")
    except discord.HTTPException as e:
        logger.error(f"❌ HTTP error sending message to Discord: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error sending to Discord: {e}")

def extract_server_start_time_from_log(log_path):
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if "Done (" in line and "For help, type" in line:
                    match = re.search(r'\[(\d{2}[A-Za-z]{3}\d{4}) (\d{2}:\d{2}:\d{2})\.\d+\]', line)
                    if match:
                        date_str = match.group(1)
                        time_str = match.group(2)
                        full_str = f"{date_str} {time_str}"
                        try:
                            dt = datetime.strptime(full_str, "%d%b%Y %H:%M:%S")
                            logger.info(f"🕰️ Extracted server start time: {dt} from {log_path}")
                            return dt.timestamp()
                        except ValueError as ve:
                            logger.error(f"⛔ Date parse error in {log_path}: {ve}")
    except Exception as e:
        logger.error(f"❌ Error extracting server start time from {log_path}: {e}")
    return None

def start_log_poller():
    log_path = Path("H:/Wanderlust Unbound Lite Server/logs/latest.log")
    if not log_path.exists():
        logger.error(f"❌ Could not find log file at: {log_path}")
        return

    def poll():
        logger.info(f"📂 Starting log poller on: {log_path}")
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as file:
                file.seek(0, os.SEEK_END)

                while True:
                    line = file.readline()
                    if line:
                        handle_log_line(line.strip())
                    else:
                        time.sleep(CONFIG.get("log_poll_interval", 1))
        except Exception as e:
            logger.exception(f"❌ Log poller encountered an error: {e}")
            time.sleep(5)

    threading.Thread(target=poll, daemon=True).start()

def strip_minecraft_formatting(text: str) -> str:
    return re.sub(r'§[0-9a-fk-or]', '', text, flags=re.IGNORECASE)

# ---------------------- Events ----------------------

@bot.event
async def on_ready():
    logger.info(f"✅ Logged in as {bot.user}")
    
    if not hasattr(bot, "status_task"):
        bot.status_task = asyncio.create_task(change_status())

    load_config()

    # 🔒 Config safety check
    required_keys = ["server_ip", "server_port", "rcon_port", "rcon_password"]
    missing = [key for key in required_keys if not CONFIG.get(key)]
    if missing:
        logger.critical(f"⛔ Cannot continue: Missing required config values: {', '.join(missing)}")
        await bot.close()
        return

    try:
        # Sync global commands
        await bot.tree.sync()
        logger.info("✅ Global slash commands synced.")

        logger.info("🌍 Global commands:")
        for cmd in bot.tree.get_commands():
            logger.info(f" ├─ /{cmd.name} — {cmd.description}")

        # Sync to test guild for instant availability
        if CONFIG.get("guild_id"):
            guild = discord.Object(id=int(CONFIG["guild_id"]))
            await bot.tree.sync(guild=guild)
            logger.info(f"✅ Slash commands synced to test guild {CONFIG['guild_id']}.")

            guild_cmds = await bot.tree.fetch_commands(guild=guild)
            logger.info(f"🛠️ Guild-specific commands:")
            for cmd in guild_cmds:
                logger.info(f" ├─ /{cmd.name} — {cmd.description}")
    except Exception as e:
        logger.exception(f"❌ Error syncing commands: {e}")

    # Send startup message to status channel if set
    startup_msg = None
    if BotState.status_channel_id:
        logger.info(f"📌 Status channel: {BotState.status_channel_id}")
        channel = bot.get_channel(BotState.status_channel_id)
        if channel:
            try:
                startup_msg = await channel.send("⏳ Server is **starting up**, please wait...")
            except Exception as e:
                logger.warning(f"⚠️ Couldn't send startup message: {e}")
        else:
            logger.warning(f"⚠️ Channel with ID {BotState.status_channel_id} not found.")
    else:
        logger.warning("⚠️ No status channel ID set in config.")

    # Start all background tasks
    start_server_watcher()
    start_log_poller()
    bot.loop.create_task(restart_bot_after_midnight_once())
    bot.loop.create_task(wait_for_server_ready())

@bot.event
async def on_message(message):
    # Ignore bot messages
    if message.author.bot:
        return

    # Process commands
    await bot.process_commands(message)

    # Relay to Minecraft chat if message is in the status channel
    if BotState.status_channel_id and message.channel.id == BotState.status_channel_id:
        try:
            text = f"{message.author.display_name}: {message.clean_content}"
            send_to_minecraft_chat(text)
            logger.info(f"💬 Relayed to Minecraft: {text}")
        except Exception as e:
            logger.error(f"❌ Failed to relay message to Minecraft: {e}")

# ---------------------- Slash Commands ----------------------

# /mcstatus
@bot.tree.command(name="mcstatus", description="Check if the Minecraft server is online")
async def mcstatus(interaction: discord.Interaction):
    logger.info(f"📥 /mcstatus used by {interaction.user} ({interaction.user.id})")
    await interaction.response.defer(thinking=True)

    server_ip = CONFIG.get("server_ip", "unknown")
    server_port = CONFIG.get("server_port", 25565)
    rcon_port = CONFIG.get("rcon_port", 25575)
    rcon_password = CONFIG.get("rcon_password", "")

    try:
        server = JavaServer(server_ip, server_port)
        status = server.status()
        latency = round(status.latency)
    except Exception as e:
        logger.warning(f"❌ Server ping failed: {e}")
        return await interaction.followup.send(
            embed=discord.Embed(
                title="🚫 Server Offline",
                description=f"🧯 Error: `{e}`\n_The gates remain sealed..._",
                color=discord.Color.red()
            ).set_footer(text=f"IP: {server_ip}:{server_port}")
        )

    # MOTD + Favicon
    try:
        motd_raw = str(status.description)
        motd = strip_minecraft_formatting(motd_raw).strip()
        icon_url = None
        if hasattr(status, "favicon") and status.favicon.startswith("data:image/png;base64,"):
            base64_data = status.favicon.split(",", 1)[1]
            icon_url = f"data:image/png;base64,{base64_data}"
    except Exception as e:
        logger.warning(f"⚠️ Failed to extract MOTD or favicon: {e}")
        motd = "Welcome to the server!"
        icon_url = None

    # Player list
    try:
        with MCRcon(server_ip, rcon_password, port=rcon_port) as m:
            response = m.command("list")
            match = re.search(r"There are (\d+) of a max of (\d+) players online(?:: (.*))?", response)
            if match:
                count = int(match.group(1))
                max_players = int(match.group(2))
                names_raw = match.group(3) or ""
                name_list = [n.strip() for n in names_raw.split(",") if n.strip()]
                max_display = 10
                names_text = (
                    ", ".join(name_list[:max_display]) + f", and {len(name_list) - max_display} more..."
                    if len(name_list) > max_display else
                    ", ".join(name_list) if name_list else "None"
                )

                # Capacity bar
                blocks = 10
                fill_ratio = count / max_players if max_players > 0 else 0
                filled_blocks = int(fill_ratio * blocks)
                partial_block = "▰" if 0 < (fill_ratio * blocks - filled_blocks) < 1 else ""
                empty_blocks = blocks - filled_blocks - (1 if partial_block else 0)

                # Choose color emoji prefix (static emoji instead of filling every block)
                if fill_ratio > 0.9:
                    color_emoji = "🔴"
                elif fill_ratio > 0.6:
                    color_emoji = "🟠"
                elif fill_ratio > 0.3:
                    color_emoji = "🟡"
                else:
                    color_emoji = "🟢"

                # Use consistent full/empty character blocks
                bar = "█" * filled_blocks + partial_block + "░" * empty_blocks
                capacity_bar = f"{color_emoji} `{bar}` `{count}/{max_players}`"

            else:
                count = 0
                names_text = "None"
                capacity_bar = "❓ Capacity data unavailable"
    except Exception as e:
        logger.warning(f"⚠️ RCON failed: {e}")
        count = "?"
        names_text = f"⚠️ Could not retrieve names: {e}"
        capacity_bar = "❌ Error getting capacity"
        max_players = 0

    # Status description
    status_description = (
        random.choice([
            "🛌 The world slumbers, awaiting its heroes...",
            "🌌 The land is quiet... for now.",
            "📜 No adventurers stir. The story awaits.",
            "🌿 All is calm. Not a soul in sight..."
        ]) if count == 0 or count == "?" else random.choice([
            "⚔️ The world hums with life and purpose!",
            "🧭 Brave souls wander the wilderness...",
            "🔥 The battle rages on. Glory awaits!",
            "📦 The overworld stirs with movement!"
        ])
    )

    # Uptime
    if BotState.server_start_time:
        elapsed = int(time.time() - BotState.server_start_time)
        hours = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        if elapsed < 60:
            uptime_text = "Just awakened from the void..."
        elif hours == 0:
            uptime_text = f"For **{minutes} minute(s)**, the realm has held steady."
        elif minutes == 0:
            uptime_text = f"For **{hours} hour(s)**, the world has persisted."
        else:
            uptime_text = f"The world has stood for **{hours} hour(s)** and **{minutes} minute(s)**."
    else:
        uptime_text = "⏳ Uptime data unavailable."

    # Embed color by load
    if isinstance(count, int) and isinstance(max_players, int) and max_players > 0:
        load_ratio = count / max_players
        embed_color = (
            discord.Color.green()  if load_ratio <= 0.3 else
            discord.Color.gold()   if load_ratio <= 0.6 else
            discord.Color.orange() if load_ratio <= 0.9 else
            discord.Color.red()
        )
        load_label = (
            "🟢 Low" if load_ratio <= 0.3 else
            "🟡 Moderate" if load_ratio <= 0.6 else
            "🟠 High" if load_ratio <= 0.9 else
            "🔴 Full"
        )
    else:
        embed_color = discord.Color.dark_gray()
        load_label = "❔ Unknown"

    # Build embed
    embed = discord.Embed(
        title="📜 Server Status Report",
        description=status_description,
        color=embed_color
    )
    embed.add_field(name="🟢 Status", value="**Online**", inline=True)
    embed.add_field(name="👥 Players Online", value=str(count), inline=True)
    embed.add_field(name="📊 Load Level", value=load_label, inline=True)
    embed.add_field(name="🧑 Names", value=names_text, inline=False)
    embed.add_field(name="📊 Capacity", value=capacity_bar, inline=False)
    embed.add_field(name="🏓 Latency", value=f"**{latency}ms**", inline=True)
    embed.add_field(name="🕰️ Uptime", value=uptime_text, inline=False)
    if motd:
        embed.add_field(name="📢 MOTD", value=motd, inline=False)
    embed.set_footer(text=f"IP: {server_ip}:{server_port}")
    if icon_url:
        embed.set_thumbnail(url=icon_url)

    await interaction.followup.send(embed=embed)

# /statushere
@bot.tree.command(name="statushere", description="Set this channel for Minecraft updates and chat")
async def statushere(interaction: discord.Interaction):
    logger.info(f"📍 /statushere used by {interaction.user} in #{interaction.channel.name} ({interaction.channel.id})")

    BotState.status_channel_id = interaction.channel.id
    save_config()

    embed = discord.Embed(
        title="📍 Status Channel Set",
        description=f"This channel (`#{interaction.channel.name}`) will now receive Minecraft updates and chat relays.",
        color=discord.Color.blue()
    )
    embed.set_footer(text="You can move this later with /statushere in another channel.")

    await interaction.response.send_message(embed=embed, ephemeral=True)

# /howtojoin
@bot.tree.command(name="howtojoin", description="Get instructions on how to join the Minecraft server")
async def howtojoin(interaction: discord.Interaction):
    logger.info(f"📨 /howtojoin used by {interaction.user} ({interaction.user.id})")
    thread_id = CONFIG.get("thread_id")
    message_id = CONFIG.get("message_id")

    if not message_id:
        return await interaction.response.send_message(
            "❌ The join instructions message ID hasn't been configured yet.\nAsk an admin to use `/setserverconfig`.",
            ephemeral=True
        )

    try:
        # Determine source channel
        message = None
        if thread_id:
            thread = await bot.fetch_channel(thread_id)
            message = await thread.fetch_message(message_id)
        elif BotState.status_channel_id:
            channel = bot.get_channel(BotState.status_channel_id) or await bot.fetch_channel(BotState.status_channel_id)
            message = await channel.fetch_message(message_id)
        else:
            raise ValueError("No thread or fallback status channel defined.")

        if not message:
            raise ValueError("Message not found or failed to fetch.")

        embed = discord.Embed(
            title="🧭 How to Join the Minecraft Server",
            description=message.content or "*No text content found.*",
            color=discord.Color.blurple()
        )

        # Try to extract embed fields if the original message has one
        if message.embeds:
            original_embed = message.embeds[0]
            if original_embed.description:
                embed.description = original_embed.description
            if original_embed.fields:
                for f in original_embed.fields:
                    embed.add_field(name=f.name, value=f.value, inline=f.inline)
            if original_embed.image:
                embed.set_image(url=original_embed.image.url)

        embed.set_footer(text="Let the adventure begin!")

        # Send DM
        await interaction.user.send(embed=embed)
        await interaction.response.send_message("📬 I've sent you a DM with the join instructions!", ephemeral=True)

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I couldn't DM you. Please enable DMs from server members.",
            ephemeral=True
        )
    except Exception as e:
        logger.warning(f"⚠️ Failed to send join instructions: {e}")
        await interaction.response.send_message(
            f"⚠️ Failed to fetch instructions: `{e}`",
            ephemeral=True
        )

@bot.tree.command(name="setserverconfig", description="Set Minecraft server connection details and timezone")
@app_commands.describe(
    server_ip="Server IP address",
    server_port="Minecraft server port",
    rcon_port="RCON port",
    rcon_password="RCON password",
    guild_id="Discord server ID for syncing slash commands",
    timezone="Timezone (e.g., Asia/Manila)",
    server_check_interval="(Optional) Server polling interval in seconds",
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
    server_check_interval: Optional[int] = None,
    thread_id: Optional[str] = None,
    message_id: Optional[str] = None
):
    logger.info(f"⚙️ /setserverconfig used by {interaction.user} ({interaction.user.id})")

    # ⏰ Validate timezone
    if timezone not in available_timezones():
        logger.warning(f"❌ Invalid timezone attempted: {timezone}")
        await interaction.response.send_message(
            f"❌ Invalid timezone: `{timezone}`\n"
            f"Refer to: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones",
            ephemeral=True
        )
        return

    # 🔍 Store previous config snapshot
    previous_config = CONFIG.copy()

    # 📝 Prepare updates
    updates = {
        "server_ip": server_ip,
        "server_port": server_port,
        "rcon_port": rcon_port,
        "rcon_password": rcon_password,
        "guild_id": int(guild_id),
        "timezone": timezone,
    }

    if server_check_interval is not None:
        updates["server_check_interval"] = server_check_interval
    elif "server_check_interval" not in CONFIG:
        updates["server_check_interval"] = 5  # default fallback

    if thread_id:
        updates["thread_id"] = int(thread_id)
    else:
        updates["thread_id"] = None

    if message_id:
        updates["message_id"] = int(message_id)
    else:
        updates["message_id"] = None

    # 🧾 Apply and log differences
    for key, new_value in updates.items():
        old_value = previous_config.get(key)
        if new_value != old_value:
            CONFIG[key] = new_value if new_value is not None else CONFIG.pop(key, None)
            logger.info(f"🔄 Config change: `{key}` updated → {old_value!r} → {new_value!r}")

    # 🧩 Sync to guild
    try:
        await bot.tree.sync(guild=discord.Object(id=CONFIG["guild_id"]))
        response = f"✅ Configuration saved and commands synced to guild `{guild_id}`."
        logger.info("✅ Slash commands synced successfully.")
    except Exception as e:
        response = f"⚠️ Config saved, but sync failed: `{e}`"
        logger.warning(f"⚠️ Slash command sync failed: {e}")

    save_config()
    await interaction.response.send_message(response, ephemeral=True)

@bot.tree.command(name="daily", description="Claim your daily Minecraft login reward!")
async def daily(interaction: discord.Interaction):
    logger.info(f"🔔 /daily triggered by {interaction.user} ({interaction.user.id})")
    await interaction.response.defer(ephemeral=True)

    if interaction.channel.id != BotState.status_channel_id:
        logger.warning("❌ /daily used in wrong channel")
        await interaction.followup.send("❌ Please use this command in the Minecraft status channel.", ephemeral=True)
        return

    username = get_linked_username(interaction.user.id)
    if not username:
        await interaction.followup.send("❌ You haven't linked your Minecraft username yet. Use `/linkmc`.", ephemeral=True)
        return

    can_claim, streak, now, last_claim = get_streak_info(username)
    logger.info(f"🧾 Claim check — Can Claim: {can_claim}, Streak: {streak}, Last Claim: {last_claim}")

    tz_name = CONFIG.get("timezone", "UTC")
    tz = ZoneInfo(tz_name)
    now_local = now.astimezone(tz)
    formatted_reset_time = now_local.replace(hour=6, minute=0, second=0, microsecond=0).strftime('%I:%M %p %Z')

    if not can_claim:
        last_local = last_claim.astimezone(tz) if last_claim else None
        next_reset = now_local.replace(hour=6, minute=0, second=0, microsecond=0)
        if now_local >= next_reset:
            next_reset += timedelta(days=1)

        remaining = next_reset - now_local
        hours, minutes = divmod(int(remaining.total_seconds()) // 60, 60)

        msg = (
            f"🕒 You last claimed your daily reward on **{last_local.strftime('%Y-%m-%d %I:%M %p %Z')}**.\n"
            f"⏳ You can claim again in **{hours}h {minutes}m**.\n"
            f"⏰ Daily resets at **{formatted_reset_time}**."
        ) if last_local else f"🕒 You've already claimed your reward recently.\n⏰ Daily resets at **{formatted_reset_time}**."

        await interaction.followup.send(msg, ephemeral=True)
        return

    rewards = load_daily_data()
    reward_day = min(streak, 7)
    reward = rewards.get(str(reward_day))

    if not reward:
        logger.error(f"⚠️ No reward configured for Day {reward_day}")
        await interaction.followup.send("⚠️ No reward configured for this day.", ephemeral=True)
        return

    item_id = reward["item"]
    amount = reward["amount"]
    sound = STREAK_SOUNDS.get(reward_day, "minecraft:entity.player.levelup")

    # Optional: Build a simple streak progress bar
    streak_visual = "".join("🟩" if i < min(streak, 7) else "⬜" for i in range(7))

    embed = discord.Embed(
        title="🎁 Daily Reward Claimed!",
        description=f"**{amount}x `{item_id}`**\nfor your **Day {streak}** login streak.",
        color=discord.Color.gold()
    )
    embed.add_field(name="📅 Streak Progress", value=streak_visual, inline=False)

    # Add streak & reset info
    embed.add_field(
        name="⏰ Reset & Streak Info",
        value=(
            f"• Rewards reset daily at **{formatted_reset_time}**.\n"
            "• Streaks continue past Day 7 — but rewards cycle back to Day 1.\n"
            "• Missing a day resets your streak."
        ),
        inline=False
    )

    # Show next reward preview if applicable
    next_day = (streak % 7) + 1
    next_reward = rewards.get(str(next_day))
    if next_reward:
        next_item = next_reward["item"].split(":")[-1].replace("_", " ").title()
        embed.set_footer(
            text=f"🎁 Tomorrow: {next_reward['amount']}x {next_item} • Resets at {formatted_reset_time}"
        )
    else:
        embed.set_footer(text=f"⏰ Daily resets at {formatted_reset_time}")

    try:
        with MCRcon(CONFIG["server_ip"], CONFIG["rcon_password"], port=CONFIG["rcon_port"]) as m:
            logger.info("🔌 RCON connected")

            rcon_output = m.command("list")
            rcon_players = parse_rcon_list_output(rcon_output)["names"]
            logger.debug(f"🧍 Online players: {rcon_players}")

            if username.lower() not in [n.lower() for n in rcon_players]:
                await interaction.followup.send(
                    f"❌ You are not online in Minecraft as **{username}**.\nPlease join the server first.",
                    ephemeral=True
                )
                return

            m.command("gamerule sendCommandFeedback false")
            m.command(f"execute as {username} run give {username} {item_id} {amount}")
            m.command(f"execute as {username} at {username} run playsound {sound} player {username} ~ ~ ~ 1 1")

            for cmd in get_fancy_particle_commands(username):
                m.command(cmd)

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
                {"text": ")", "color": "dark_gray"},
                {"text": f"\n⏰ Daily resets at {formatted_reset_time}", "color": "gray"}
            ])
            m.command(f'tellraw @a {message_json}')
            m.command("gamerule sendCommandFeedback true")

        logger.info(f"🎉 {username} claimed Day {streak} reward: {amount}x {item_id}")
        await interaction.followup.send(embed=embed, ephemeral=True)
        update_streak_info(username, now, streak)

    except Exception as e:
        logger.exception(f"❌ Failed to issue reward for {username}: {e}")
        await interaction.followup.send(f"❌ Failed to issue reward: `{e}`", ephemeral=True)


# /linkmc
@bot.tree.command(name="linkmc", description="Link your Discord account to your Minecraft username.")
@app_commands.describe(username="Your Minecraft username")
async def linkmc(interaction: discord.Interaction, username: str):
    await interaction.response.defer(ephemeral=True)
    logger.info(f"🔗 /linkmc triggered by {interaction.user} ({interaction.user.id}) → {username}")

    filepath = "data/linked_users.json"
    os.makedirs("data", exist_ok=True)

    # Load or initialize file
    if not os.path.exists(filepath):
        with open(filepath, "w") as f:
            json.dump({}, f)

    with open(filepath, "r", encoding="utf-8") as f:
        linked_users = json.load(f)

    discord_id_str = str(interaction.user.id)
    username = username.strip().lower()
    prev = linked_users.get(discord_id_str)

    # Update and save
    linked_users[discord_id_str] = username
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(linked_users, f, indent=2, ensure_ascii=False)

    # Feedback
    if prev and prev != username:
        msg = f"🔁 Updated your linked Minecraft username from **{prev}** to **{username}**."
    elif prev == username:
        msg = f"🔗 You are already linked to **{username}**."
    else:
        msg = f"✅ Your Discord account is now linked to **{username}**!"

    logger.info(f"📝 {interaction.user} is now linked to Minecraft username: {username}")
    await interaction.followup.send(msg, ephemeral=True)

# /rewards
@bot.tree.command(name="rewards", description="View the 7-day daily reward schedule.")
async def rewards(interaction: discord.Interaction):
    logger.info(f"🎁 /rewards used by {interaction.user} ({interaction.user.id})")
    await interaction.response.defer(ephemeral=True)

    try:
        rewards_data = load_daily_data()
    except Exception as e:
        logger.exception(f"❌ Failed to load daily rewards: {e}")
        await interaction.followup.send("❌ Failed to load reward data. Please try again later.", ephemeral=True)
        return

    tz_name = CONFIG.get("timezone", "UTC")
    tz = ZoneInfo(tz_name)
    reset_hour = 6
    # Format reset time nicely e.g. "06:00 AM PST"
    reset_time_dt = datetime.now(tz).replace(hour=reset_hour, minute=0, second=0, microsecond=0)
    formatted_reset_time = reset_time_dt.strftime('%I:%M %p %Z')

    embed = discord.Embed(
        title="🎁 Daily Reward Schedule",
        description="Use `/daily` every day while online in Minecraft to claim your reward!",
        color=discord.Color.orange()
    )

    for day in range(1, 8):
        reward = rewards_data.get(str(day))
        if reward:
            item = reward["item"].replace("numismatic-overhaul:", "")
            amount = reward["amount"]
            embed.add_field(
                name=f"Day {day}",
                value=f"• **{amount}x** `{item}`",
                inline=True
            )
        else:
            embed.add_field(
                name=f"Day {day}",
                value="⚠️ *Not configured*",
                inline=True
            )

    embed.add_field(
        name="⏰ Reset & Streak Info",
        value=(
            f"• Rewards reset daily at **{formatted_reset_time}**.\n"
            "• Streaks continue past Day 7 — but rewards cycle back to Day 1.\n"
            "• Missing a day **resets your streak**."
        ),
        inline=False
    )

    embed.set_footer(text="✨ Stay consistent to maintain your streak and maximize your rewards!")

    await interaction.followup.send(embed=embed, ephemeral=True)

# /helpme
@bot.tree.command(name="helpme", description="List all Wanderbot commands")
async def helpme(interaction: discord.Interaction):
    logger.info(f"📘 /helpme used by {interaction.user} ({interaction.user.id})")
    await interaction.response.defer(ephemeral=True)

    embed = discord.Embed(
        title="🎮 Wanderbot Command Guide",
        description="Here's a list of everything I can help you with:",
        color=discord.Color.gold()
    )

    # 🧍 General Player Commands
    embed.add_field(
        name="🧍 Player Commands",
        value=(
            "• **`/linkmc <username>`** — Link your Minecraft username to your Discord.\n"
            "• **`/daily`** — Claim your daily reward *(must be online in Minecraft)*.\n"
            "• **`/rewards`** — View the 7-day daily reward schedule.\n"
            "• **`/howtojoin`** — Get instructions on how to join the Minecraft server."
        ),
        inline=False
    )

    # 📊 Server Info
    embed.add_field(
        name="📊 Server Info",
        value=(
            "• **`/mcstatus`** — Check if the Minecraft server is online.\n"
            "• **`/motd`** — View the server's current message of the day (MOTD)."
        ),
        inline=False
    )

    # 🛠️ Admin Commands
    embed.add_field(
        name="🛠️ Admin Commands",
        value=(
            "• **`/setserverconfig`** — Configure IP, port, RCON, timezone, and guild ID.\n"
            "• **`/statushere`** — Set this channel to receive status updates."
        ),
        inline=False
    )

    # 📘 Help
    embed.add_field(
        name="📘 Help",
        value="• **`/helpme`** — Display this help message anytime.",
        inline=False
    )

    embed.set_footer(text="✨ Some commands require admin rights or a linked Minecraft account.")

    await interaction.followup.send(embed=embed, ephemeral=True)

# ---------------------- Run ----------------------

async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
