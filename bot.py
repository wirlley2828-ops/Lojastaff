import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import discord
from discord.ext import commands

# =========================
# Servidor HTTP para o Render
# =========================

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot online!")

def run_web():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()

threading.Thread(target=run_web, daemon=True).start()

# =========================
# Bot do Discord
# =========================

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot online como {bot.user}")

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

@bot.command()
async def ola(ctx):
    await ctx.send(f"Olá, {ctx.author.mention}! 👋")

bot.run(TOKEN)


import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import os
from datetime import datetime

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# BANCO DE DADOS
# =========================
conn = sqlite3.connect("staffcoins.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    coins INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS shop (
    item TEXT,
    price INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS logs (
    user_id INTEGER,
    action TEXT,
    item TEXT,
    price INTEGER,
    time TEXT
)
""")

# Loja inicial
default_items = [
    ("Desafiante", 150),
    ("Cargo Destaque (7 dias)", 500),
    ("Cargo Personalizado (7 dias)", 800),
    ("Avaliação Prioritária", 1500)
]

cursor.execute("SELECT COUNT(*) FROM shop")
if cursor.fetchone()[0] == 0:
    cursor.executemany("INSERT INTO shop VALUES (?, ?)", default_items)

conn.commit()

# =========================
# FUNÇÕES AUXILIARES
# =========================

def get_coins(user_id):
    cursor.execute("SELECT coins FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    if result is None:
        cursor.execute("INSERT INTO users (user_id, coins) VALUES (?, 0)", (user_id,))
        conn.commit()
        return 0
    return result[0]

def add_coins(user_id, amount):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, coins) VALUES (?, 0)", (user_id,))
    cursor.execute("UPDATE users SET coins = coins + ? WHERE user_id=?", (amount, user_id))
    conn.commit()

def remove_coins(user_id, amount):
    cursor.execute("UPDATE users SET coins = coins - ? WHERE user_id=?", (amount, user_id))
    conn.commit()

def is_admin(interaction: discord.Interaction):
    return interaction.user.guild_permissions.administrator or any(role.name == "Dono" for role in interaction.user.roles)

# =========================
# BOT PRONTO
# =========================

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot online como {bot.user}")

# =========================
# SALDO
# =========================
@bot.tree.command(name="saldo")
async def saldo(interaction: discord.Interaction):
    coins = get_coins(interaction.user.id)
    await interaction.response.send_message(f"🪙 Você tem **{coins} Staff Coins**", ephemeral=True)

# =========================
# LOJA
# =========================
@bot.tree.command(name="loja")
async def loja(interaction: discord.Interaction):
    cursor.execute("SELECT * FROM shop")
    items = cursor.fetchall()

    msg = "🛒 **LOJA STAFF**\n\n"
    for item, price in items:
        msg += f"• {item} — {price} Staff Coins\n"

    await interaction.response.send_message(msg, ephemeral=True)

# =========================
# COMPRAR
# =========================
@bot.tree.command(name="comprar")
@app_commands.describe(item="Nome do item")
async def comprar(interaction: discord.Interaction, item: str):

    cursor.execute("SELECT price FROM shop WHERE item=?", (item,))
    result = cursor.fetchone()

    if not result:
        return await interaction.response.send_message("❌ Item não encontrado.", ephemeral=True)

    price = result[0]
    user_coins = get_coins(interaction.user.id)

    if user_coins < price:
        return await interaction.response.send_message("❌ Você não tem Staff Coins suficientes.", ephemeral=True)

    remove_coins(interaction.user.id, price)

    cursor.execute(
        "INSERT INTO logs VALUES (?, ?, ?, ?, ?)",
        (interaction.user.id, "COMPRA", item, price, str(datetime.now()))
    )
    conn.commit()

    await interaction.response.send_message(
        f"✅ Compra realizada!\n\n🏷️ Item: {item}\n💰 Preço: {price} Staff Coins\n\nAguarde entrega manual da staff.",
        ephemeral=True
    )

# =========================
# ADD COINS
# =========================
@bot.tree.command(name="addmoedas")
async def addmoedas(interaction: discord.Interaction, member: discord.Member, amount: int):

    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

    add_coins(member.id, amount)

    await interaction.response.send_message(
        f"✅ {amount} Staff Coins adicionadas para {member.mention}"
    )

# =========================
# REMOVE COINS
# =========================
@bot.tree.command(name="removemoedas")
async def removemoedas(interaction: discord.Interaction, member: discord.Member, amount: int):

    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

    remove_coins(member.id, amount)

    await interaction.response.send_message(
        f"🗑️ {amount} Staff Coins removidas de {member.mention}"
    )

# =========================
# SET COINS
# =========================
@bot.tree.command(name="setmoedas")
async def setmoedas(interaction: discord.Interaction, member: discord.Member, amount: int):

    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, 0)", (member.id,))
    cursor.execute("UPDATE users SET coins=? WHERE user_id=?", (amount, member.id))
    conn.commit()

    await interaction.response.send_message(
        f"⚙️ {member.mention} agora tem {amount} Staff Coins"
    )

# =========================
# RANKING
# =========================
@bot.tree.command(name="ranking")
async def ranking(interaction: discord.Interaction):

    cursor.execute("SELECT user_id, coins FROM users ORDER BY coins DESC LIMIT 10")
    data = cursor.fetchall()

    msg = "🏆 **RANKING STAFF COINS**\n\n"

    for i, (user_id, coins) in enumerate(data, start=1):
        user = await bot.fetch_user(user_id)
        msg += f"{i}. {user.name} — {coins} Coins\n"

    await interaction.response.send_message(msg, ephemeral=True)

# =========================
bot.run(TOKEN)
