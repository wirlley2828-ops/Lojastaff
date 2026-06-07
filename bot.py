import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import sqlite3

import discord
from discord import app_commands
from discord.ext import commands
import discord.ui

# =========================
# HTTP SERVER (Render)
# =========================

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot online!")

def run_web():
    port = int(os.environ.get("PORT"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()

threading.Thread(target=run_web, daemon=True).start()

# =========================
# BOT
# =========================

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# BANCO DE DADOS
# =========================

conn = sqlite3.connect("staffcoins.db", check_same_thread=False)
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

# =========================
# LOJA PADRÃO
# =========================

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
# FUNÇÕES
# =========================

def get_coins(user_id):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, coins) VALUES (?, 0)", (user_id,))
    conn.commit()

    cursor.execute("SELECT coins FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone()[0]


def add_coins(user_id, amount):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, coins) VALUES (?, 0)", (user_id,))
    cursor.execute("UPDATE users SET coins = coins + ? WHERE user_id=?", (amount, user_id))
    conn.commit()


def remove_coins(user_id, amount):
    cursor.execute("UPDATE users SET coins = coins - ? WHERE user_id=?", (amount, user_id))
    conn.commit()


def is_admin(interaction: discord.Interaction):
    return interaction.user.guild_permissions.administrator

# =========================
# READY
# =========================

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot online como {bot.user}")

# =========================
# SALDO
# =========================

@bot.tree.command(name="saldo")
async def saldo(interaction: discord.Interaction):
    coins = get_coins(interaction.user.id)
    await interaction.response.send_message(
        f"🪙 Você tem **{coins} Staff Coins**",
        ephemeral=True
    )

# =========================
# BOTÃO DA LOJA
# =========================

class ShopButton(discord.ui.Button):
    def __init__(self, item, price):
        super().__init__(
            label=f"{item} - {price}",
            style=discord.ButtonStyle.green
        )
        self.item = item
        self.price = price

    async def callback(self, interaction: discord.Interaction):

        user_id = interaction.user.id
        coins = get_coins(user_id)

        if coins < self.price:
            return await interaction.response.send_message(
                "❌ Você não tem Staff Coins suficientes.",
                ephemeral=True
            )

        remove_coins(user_id, self.price)

        cursor.execute(
            "INSERT INTO logs VALUES (?, ?, ?, ?, ?)",
            (user_id, "COMPRA", self.item, self.price, str(datetime.now()))
        )
        conn.commit()

        await interaction.response.send_message(
            f"✅ Compra realizada!\n\n🏷️ {self.item}\n💰 {self.price} Coins",
            ephemeral=True
        )

# =========================
# VIEW DA LOJA
# =========================

class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        cursor.execute("SELECT item, price FROM shop")
        items = cursor.fetchall()

        for item, price in items:
            self.add_item(ShopButton(item, price))

# =========================
# LOJA (COM BOTÕES)
# =========================

@bot.tree.command(name="loja")
async def loja(interaction: discord.Interaction):

    embed = discord.Embed(
        title="🛒 LOJA STAFF",
        description="Clique nos botões abaixo para comprar itens:",
        color=discord.Color.green()
    )

    await interaction.response.send_message(
        embed=embed,
        view=ShopView(),
        ephemeral=True
    )

# =========================
# COMPRAR (mantido)
# =========================

@bot.tree.command(name="comprar")
@app_commands.describe(item="Nome do item exatamente como na loja")
async def comprar(interaction: discord.Interaction, item: str):

    cursor.execute("SELECT price FROM shop WHERE item=?", (item,))
    result = cursor.fetchone()

    if not result:
        return await interaction.response.send_message("❌ Item não encontrado na loja.", ephemeral=True)

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
        f"✅ Compra realizada!\n\n🏷️ Item: {item}\n💰 Preço: {price} Coins\n\nAguarde entrega manual da staff.",
        ephemeral=True
    )

# =========================
# ADD MOEDAS
# =========================

@bot.tree.command(name="addmoedas")
async def addmoedas(interaction: discord.Interaction, member: discord.Member, amount: int):

    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

    add_coins(member.id, amount)

    await interaction.response.send_message(
        f"✅ {amount} moedas adicionadas para {member.mention}",
        ephemeral=True
    )

# =========================
# REMOVE MOEDAS
# =========================

@bot.tree.command(name="removemoedas")
async def removemoedas(interaction: discord.Interaction, member: discord.Member, amount: int):

    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

    remove_coins(member.id, amount)

    await interaction.response.send_message(
        f"🗑️ {amount} moedas removidas de {member.mention}",
        ephemeral=True
    )

# =========================
# LOGS
# =========================

@bot.tree.command(name="logs")
async def logs(interaction: discord.Interaction):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

    cursor.execute("SELECT user_id, item, price, time FROM logs ORDER BY time DESC LIMIT 10")
    data = cursor.fetchall()

    if not data:
        return await interaction.response.send_message("📭 Nenhum log encontrado.", ephemeral=True)

    msg = "📜 **ÚLTIMAS COMPRAS**\n\n"

    for user_id, item, price, time in data:
        user = await bot.fetch_user(user_id)
        msg += f"👤 {user.name}\n🏷️ {item} - {price} Coins\n🕒 {time}\n\n"

    await interaction.response.send_message(msg, ephemeral=True)

# =========================
# START BOT
# =========================

bot.run(TOKEN)
