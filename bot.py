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
    is_owner_role = any(role.name == "Dono" for role in interaction.user.roles)
    return interaction.user.guild_permissions.administrator or is_owner_role

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

@bot.tree.command(name="saldo", description="Ver suas coins")
async def saldo(interaction: discord.Interaction):
    coins = get_coins(interaction.user.id)
    await interaction.response.send_message(
        f"🪙 {interaction.user.mention} tem **{coins} Staff Coins**"
    )

# =========================
# CHECKOUT
# =========================

class CheckoutView(discord.ui.View):
    def __init__(self, item, price, user_id):
        super().__init__(timeout=30)
        self.item = item
        self.price = price
        self.user_id = user_id

    @discord.ui.button(label="Confirmar Compra", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):

        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Não é seu checkout.", ephemeral=True)

        coins = get_coins(self.user_id)

        if coins < self.price:
            return await interaction.response.send_message("❌ Sem coins suficientes.", ephemeral=True)

        remove_coins(self.user_id, self.price)

        cursor.execute(
            "INSERT INTO logs VALUES (?, ?, ?, ?, ?)",
            (self.user_id, "COMPRA", self.item, self.price, str(datetime.now()))
        )
        conn.commit()

        await interaction.response.edit_message(
            content=f"✅ COMPRA CONFIRMADA!\n🏷️ {self.item}\n💰 {self.price} Coins",
            view=None
        )

        # LOG PÚBLICO
        await interaction.channel.send(
            f"🛒 {interaction.user.mention} comprou **{self.item}** por {self.price} coins!"
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):

        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Não é seu checkout.", ephemeral=True)

        await interaction.response.edit_message(
            content="❌ Compra cancelada.",
            view=None
        )

# =========================
# LOJA
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

        view = CheckoutView(self.item, self.price, interaction.user.id)

        embed = discord.Embed(
            title="🧾 CHECKOUT",
            description=f"""
🏷️ **Item:** {self.item}
💰 **Preço:** {self.price}
🪙 **Seu saldo:** {get_coins(interaction.user.id)}

Deseja confirmar a compra?
            """,
            color=discord.Color.orange()
        )

        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )

class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        cursor.execute("SELECT item, price FROM shop")
        items = cursor.fetchall()

        for item, price in items:
            self.add_item(ShopButton(item, price))

@bot.tree.command(name="loja", description="Abrir loja staff")
async def loja(interaction: discord.Interaction):

    embed = discord.Embed(
        title="🛒 LOJA"
    )
