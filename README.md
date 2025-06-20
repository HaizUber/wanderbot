# 🌍 Wanderbot — Minecraft Discord Companion

**Wanderbot** is a custom-built Discord bot designed for managing and enhancing the experience of players in the *Wanderlust Unbound* Minecraft server. It connects Discord and Minecraft together with features like daily login rewards, live server status, and more — all powered by RCON and Discord’s slash command API.

---

## ✨ Features

### 🎁 Daily Rewards System
- Players can claim a **daily reward** via `/daily`.
- Supports **streaks up to 7 days**, looping back to the first reward.
- Plays unique sounds and spawns particle effects in Minecraft upon claim.
- Sends stylish Minecraft announcements using `tellraw`.

### 📡 Server Monitoring
- `/mcstatus` - See if the Minecraft server is online and who's playing.
- `/motd` - View the server’s current message of the day.
- Real-time status channel updates (automated).

### 📬 Player Onboarding
- `/howtojoin` - Sends players instructions on how to join the server via DM.
- Instructions are pulled from a specific thread/message you define.

### 🔗 Account Linking
- `/linkmc <username>` - Link your Minecraft username to your Discord account.
- Required for daily rewards and integrations.

### ⚙️ Admin Tools
- `/setserverconfig` - Set RCON credentials, server info, timezone, and more.
- `/statushere` - Designate the current channel as the server status channel.
- `/purge <days>` - Clean up messages older than X days.
- Full config persistence via `bot_config.json`.

---

## 🛠 Setup

### 🔧 Configuration
Ensure the following are set via `/setserverconfig`:
- Server IP, port, RCON port/password
- Discord Guild ID (for command sync)
- Timezone (e.g., `Asia/Manila`)
- Optional: Thread/message IDs for join instructions

### 📦 Install Requirements
pip install -r requirements.txt

or install these one by one via pip install

- discord.py
- mcstatus
- python-dotenv
- mcrcon
- tzdata>=2024.1

🧾 Create your Environment Variables
- .env should contain DISCORD_TOKEN=your-bot-token-here           

### 🧠 Tech Stack
    Discord.py (v2) – Slash commands, embeds
    MCRCON – Interfacing with the Minecraft server
    JSON – Lightweight data storage

### 📣 Contributions
- This is a private project, but you’re welcome to suggest improvements or request features. PRs are welcome with context.

### 🧭 Future Ideas
- Event-based rewards (like birthdays or holidays!)
- /discord in Minecraft for server invite
- Weekly claim leaderboards
- More optimizations!
- Integrate the player more with the bot!
- Dashboard GUI?

---

### 🏁 License
- MIT — Feel free to use, fork, or extend for your own server.

### Built with ❤️ for the Wanderlust Unbound Family of Minecraft Modpacks.
