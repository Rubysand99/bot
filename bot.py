import discord
from discord.ext import commands
import aiohttp
import os
import json

TOKEN = os.getenv("TOKEN")

ADMIN_ID = 846332174734983219
LOG_ADMIN_CHANNEL = 1464524557657440396

API = "https://website-kiemtien.onrender.com"
CODE_CHANNEL_ID = 1464428982857634044

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ================= GLOBAL SESSION =================

session = None

@bot.event
async def on_ready():
    global session
    session = aiohttp.ClientSession()
    print("Bot online:", bot.user)

# ================= API =================

async def api_get(url):
    try:
        async with session.get(url) as res:
            return await res.json()
    except:
        return None

async def api_post(url, data):
    try:
        async with session.post(url, json=data) as res:
            return await res.json()
    except:
        return None

# ================= POINT =================

async def get_points(user_id):
    return await api_get(f"{API}/points/{user_id}")

async def add_points(user_id, amount):
    return await api_post(f"{API}/add-point", {
        "discordId": str(user_id),
        "amount": amount
    })

async def remove_points(user_id, amount=None):
    return await api_post(f"{API}/remove-point", {
        "discordId": str(user_id),
        "amount": amount
    })

# ================= FIND USER =================

def find_member(guild, username):
    username = username.lower()
    for member in guild.members:
        if member.name.lower() == username:
            return member
    return None

# ================= COMMAND =================

@bot.command()
async def point(ctx, member: discord.Member = None):
    member = member or ctx.author

    data = await get_points(member.id)

    if not data:
        return await ctx.send("❌ Lỗi server")

    await ctx.send(f"💰 {member.mention}: {data.get('points', 0)} point")

# ================= ON MESSAGE =================

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    content = message.content.strip()

    # ===== ADMIN TEXT COMMAND =====
    if content.startswith("gp ") or content.startswith("xp "):

        if message.author.id != ADMIN_ID:
            return await message.reply("❌ Bạn không có quyền")

        parts = content.split()

        if len(parts) < 2:
            return await message.reply("❌ Sai cú pháp")

        cmd = parts[0]
        username = parts[1]

        member = find_member(message.guild, username)

        if not member:
            return await message.reply("❌ Không tìm thấy user")

        log_channel = bot.get_channel(LOG_ADMIN_CHANNEL)

        # ===== GP =====
        if cmd == "gp":

            if len(parts) < 3:
                return await message.reply("❌ Thiếu số point")

            try:
                amount = int(parts[2])
            except:
                return await message.reply("❌ Số không hợp lệ")

            await add_points(member.id, amount)

            await message.reply(f"✅ +{amount} point cho {member.mention}")

            if log_channel:
                await log_channel.send(
                    f"➕ {message.author} → {member} (+{amount})"
                )

        # ===== XP =====
        elif cmd == "xp":

            amount = None

            if len(parts) >= 3:
                try:
                    amount = int(parts[2])
                except:
                    return await message.reply("❌ Số không hợp lệ")

            await remove_points(member.id, amount)

            if amount is None:
                await message.reply(f"🗑️ Xoá hết point {member.mention}")
            else:
                await message.reply(f"🗑️ -{amount} point {member.mention}")

            if log_channel:
                if amount is None:
                    await log_channel.send(
                        f"🗑️ {message.author} → {member} (xoá hết)"
                    )
                else:
                    await log_channel.send(
                        f"➖ {message.author} → {member} (-{amount})"
                    )

    # ===== EARN CODE =====
    if message.channel.id == CODE_CHANNEL_ID:

        code = content

        if not code.startswith("EP-"):
            return await message.reply("❌ code không hợp lệ")

        data = await api_post(f"{API}/check-code", {
            "code": code,
            "discordId": str(message.author.id)
        })

        if not data:
            return await message.reply("❌ lỗi server")

        if data["status"] == "ok":
            await message.reply(
                f"✅ +1 point | Tổng: {data['points']}"
            )
        elif data["status"] == "expired":
            await message.reply("⏱️ code hết hạn")
        else:
            await message.reply("❌ code không hợp lệ")

    await bot.process_commands(message)

# ================= CLOSE SESSION =================

@bot.event
async def on_close():
    if session:
        await session.close()

# ================= RUN =================

bot.run(TOKEN)
