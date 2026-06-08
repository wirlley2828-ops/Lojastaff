import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import sqlite3
import traceback
import sys
import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands
import discord.ui

# =========================
# LOG SYSTEM (ANTI CRASH DEBUG)
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# =========================
# HTTP SERVER (Render FIX)
# =========================

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot online!")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()

def run_web():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()

threading.Thread(target=run_web, daemon=True).start()

# =========================
# BOT
# =========================

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    print("❌ TOKEN não configurado no ambiente!")
    sys.exit(1)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# ANTI CRASH GLOBAL
# =========================

@bot.event
async def on_error(event, *args, **kwargs):
    print("❌ ERRO GLOBAL:")
    traceback.print_exc()

# =========================
# BANCO
# =========================

conn = sqlite3.connect("staffcoins.db", check_same_thread=False)
cursor = conn.cursor()

lock = asyncio.Lock()

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
    try:
        cursor.execute("INSERT OR IGNORE INTO users (user_id, coins) VALUES (?, 0)", (user_id,))
        conn.commit()
        cursor.execute("SELECT coins FROM users WHERE user_id=?", (user_id,))
        return cursor.fetchone()[0]
    except Exception:
        traceback.print_exc()
        return 0


def add_coins(user_id, amount):
    try:
        cursor.execute("INSERT OR IGNORE INTO users (user_id, coins) VALUES (?, 0)", (user_id,))
        cursor.execute("UPDATE users SET coins = coins + ? WHERE user_id=?", (amount, user_id))
        conn.commit()
    except Exception:
        traceback.print_exc()


def remove_coins(user_id, amount):
    try:
        cursor.execute("UPDATE users SET coins = coins - ? WHERE user_id=?", (amount, user_id))
        conn.commit()
    except Exception:
        traceback.print_exc()


def is_admin(interaction: discord.Interaction):
    is_owner_role = any(role.name == "Dono" for role in interaction.user.roles)
    return interaction.user.guild_permissions.administrator or is_owner_role

# =========================
# READY (ANTI CRASH SYNC)
# =========================

@bot.event
async def on_ready():
    try:
        await bot.wait_until_ready()
        await bot.tree.sync()
        print(f"✅ Bot online como {bot.user}")
    except Exception:
        print("❌ ERRO AO SINCRONIZAR:")
        traceback.print_exc()

# =========================
# SALDO
# =========================

@bot.tree.command(name="saldo", description="Ver suas coins")
async def saldo(interaction: discord.Interaction):
    try:
        await interaction.response.defer()

        coins = get_coins(interaction.user.id)

        await interaction.followup.send(
            f"🪙 {interaction.user.mention} tem **{coins} Staff Coins**"
        )
    except Exception:
        traceback.print_exc()

# =========================
# LOJA
# =========================

class CheckoutView(discord.ui.View):
    def __init__(self, item, price, user_id):
        super().__init__(timeout=30)
        self.item = item
        self.price = price
        self.user_id = user_id

    @discord.ui.button(label="Confirmar Compra", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
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

            await interaction.channel.send(
                f"🛒 {interaction.user.mention} comprou **{self.item}** por {self.price} coins!"
            )

        except Exception:
            traceback.print_exc()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("❌ Não é seu checkout.", ephemeral=True)

            await interaction.response.edit_message(
                content="❌ Compra cancelada.",
                view=None
            )
        except Exception:
            traceback.print_exc()


class ShopButton(discord.ui.Button):
    def __init__(self, item, price):
        super().__init__(label=f"{item} - {price}", style=discord.ButtonStyle.green)
        self.item = item
        self.price = price

    async def callback(self, interaction: discord.Interaction):
        try:
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

            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        except Exception:
            traceback.print_exc()


class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        cursor.execute("SELECT item, price FROM shop")
        items = cursor.fetchall()

        for item, price in items:
            self.add_item(ShopButton(item, price))


@bot.tree.command(name="loja", description="Abrir loja staff")
async def loja(interaction: discord.Interaction):
    try:
        embed = discord.Embed(
            title="🛒 LOJA STAFF",
            description="Clique nos botões abaixo para comprar itens.",
            color=discord.Color.green()
        )

        await interaction.response.send_message(embed=embed, view=ShopView())

    except Exception:
        traceback.print_exc()

# =========================
# ADD MOEDAS
# =========================

@bot.tree.command(name="addmoedas", description="Adicionar coins")
async def addmoedas(interaction: discord.Interaction, member: discord.Member, amount: int):
    try:
        if not is_admin(interaction):
            return await interaction.response.send_message("❌ Sem permissão.")

        add_coins(member.id, amount)

        await interaction.response.send_message(
            f"✅ {amount} moedas adicionadas para {member.mention}"
        )
    except Exception:
        traceback.print_exc()

# =========================
# REMOVE MOEDAS
# =========================

@bot.tree.command(name="removemoedas", description="Remover coins")
async def removemoedas(interaction: discord.Interaction, member: discord.Member, amount: int):
    try:
        if not is_admin(interaction):
            return await interaction.response.send_message("❌ Sem permissão.")

        remove_coins(member.id, amount)

        await interaction.response.send_message(
            f"🗑️ {amount} moedas removidas de {member.mention}"
        )
    except Exception:
        traceback.print_exc()

# =========================
# LOGS
# =========================

@bot.tree.command(name="logs", description="Ver logs de compras")
async def logs(interaction: discord.Interaction):
    try:
        is_owner_role = any(role.name == "Dono" for role in interaction.user.roles)

        if not interaction.user.guild_permissions.administrator and not is_owner_role:
            return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

        cursor.execute("SELECT user_id, item, price, time FROM logs ORDER BY time DESC LIMIT 10")
        data = cursor.fetchall()

        if not data:
            return await interaction.response.send_message("📭 Nenhum log encontrado.", ephemeral=True)

        embed = discord.Embed(
            title="📜 LOGS DO SISTEMA STAFF COINS",
            description="Últimas ações registradas no sistema",
            color=discord.Color.dark_blue(),
            timestamp=datetime.now()
        )

        embed.set_footer(text="Sistema de auditoria - Staff Coins")

        for user_id, item, price, time in data:
            embed.add_field(
                name=f"👤 Usuário: <@{user_id}>",
                value=(
                    f"🛒 **Ação:** COMPRA\n"
                    f"🏷️ **Item:** {item}\n"
                    f"💰 **Valor:** {price} coins\n"
                    f"🕒 **Data:** {time}"
                ),
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    except Exception:
        traceback.print_exc()

# =========================
# START (ANTI CRASH LOOP)
# =========================

while True:
    try:
        bot.run(TOKEN)
    except Exception:
        print("❌ BOT CAIU - REINICIANDO...")
        traceback.print_exc()
