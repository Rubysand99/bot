import discord
from discord.ext import commands
import os

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print("Bot online")

@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

bot.run(os.getenv("MTQ1OTUyMDk5NjIwOTA3MDIzNw.G1IJnQ.85hQrPiw7L1ZnprpjR0XTbgADeCNqq2r7TjO4A"))
