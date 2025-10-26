"""
Discord Bot for Restaurant Reservation Management
Channels:
- #reservas-confirmadas: Shows confirmed reservations with cancel button
- #pendientes-aprobacion: Shows pending restaurant approval with accept button
- #log-acciones: Action log for last month
"""

import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import sqlite3
import os
import asyncio
from datetime import datetime, timedelta
from contextlib import contextmanager
from collections import defaultdict
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Bot setup
intents = discord.Intents.default()

async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get reservation
            cursor.execute('SELECT * FROM reservations WHERE id = ?', (self.reservation_id,))
            res = cursor.fetchone()
            
            if not res:
                await interaction.followup.send("âŒ Reserva no encontrada", ephemeral=True)
                return
            
            if res['cancelled']:
                await interaction.followup.send("âš ï¸ Esta reserva ya estÃ¡ cancelada", ephemeral=True)
                return
            
            # Mark as cancelled
            cursor.execute('''
                UPDATE reservations 
                SET cancelled = 1, 
                    cancelled_at = CURRENT_TIMESTAMP,
                    cancelled_by = ?
                WHERE id = ?
            ''', (str(interaction.user), self.reservation_id))
            conn.commit()
            
            # Log action
            await log_action(
                self.reservation_id,
                'cancelled',
                str(interaction.user),
                self.reason.value or "Sin motivo especificado"
            )
            
            # Send SMS to customer
            message = (
                f"Hola {res['nombre']}, "
                f"lamentamos informarte que tu reserva para {res['personas']} personas "
                f"el {res['fecha']} a las {res['hora']} ha sido cancelada. "
                f"Por favor, contÃ¡ctanos al 965 78 57 31. - Les Monges"
            )
            send_sms(res['telefono'], message)
            
            # Delete the message immediately
            try:
                await interaction.message.delete()
            except:
                pass  # Message might already be deleted
            
            await interaction.followup.send(
                f"âœ… Reserva #{self.reservation_id} cancelada y cliente notificado por SMS",
                ephemeral=True
            )#!/usr/bin/env python3
# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Configuration
DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
DB_PATH = 'reservations.db'

# Channel IDs (set these after creating channels)
CONFIRMED_CHANNEL_ID = int(os.getenv('CONFIRMED_CHANNEL_ID', '0'))
PENDING_CHANNEL_ID = int(os.getenv('PENDING_CHANNEL_ID', '0'))
LOG_CHANNEL_ID = int(os.getenv('LOG_CHANNEL_ID', '0'))

@contextmanager
def get_db():
    """Database connection context manager"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def send_sms(phone, message):
    """Send SMS (import from app.py or duplicate the function)"""
    # TODO: Import from app.py or duplicate SMS logic
    import sys
    sys.path.append('.')
    from app import send_sms as app_send_sms
    return app_send_sms(phone, message)

async def log_action(reservation_id, action_type, performed_by, details=None):
    """Log action to database and Discord"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO action_log (reservation_id, action_type, performed_by, details)
            VALUES (?, ?, ?, ?)
        ''', (reservation_id, action_type, performed_by, details))
        conn.commit()
    
    # Send to Discord log channel
    if LOG_CHANNEL_ID:
        channel = bot.get_channel(LOG_CHANNEL_ID)
        if channel:
            # Get reservation details
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM reservations WHERE id = ?', (reservation_id,))
                res = cursor.fetchone()
            
            if res:
                embed = discord.Embed(
                    title=f"ðŸ“ {action_type.upper()}",
                    color=discord.Color.blue() if action_type == 'confirmed' else discord.Color.red(),
                    timestamp=datetime.utcnow()
                )
                embed.add_field(name="ID", value=str(reservation_id), inline=True)
                embed.add_field(name="Nombre", value=res['nombre'], inline=True)
                embed.add_field(name="Personas", value=str(res['personas']), inline=True)
                embed.add_field(name="Fecha/Hora", value=f"{res['fecha']} {res['hora']}", inline=False)
                embed.add_field(name="Realizado por", value=performed_by, inline=False)
                if details:
                    embed.add_field(name="Detalles", value=details, inline=False)
                
                await channel.send(embed=embed)

class ConfirmButton(Button):
    """Accept button for pending reservations"""
    def __init__(self, reservation_id):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="âœ… Aceptar Reserva",
            custom_id=f"confirm_{reservation_id}"
        )
        self.reservation_id = reservation_id
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get reservation
            cursor.execute('SELECT * FROM reservations WHERE id = ?', (self.reservation_id,))
            res = cursor.fetchone()
            
            if not res:
                await interaction.followup.send("âŒ Reserva no encontrada", ephemeral=True)
                return
            
            if res['restaurant_confirmed']:
                await interaction.followup.send("âš ï¸ Esta reserva ya estÃ¡ confirmada", ephemeral=True)
                return
            
            # Update to confirmed
            cursor.execute('''
                UPDATE reservations 
                SET restaurant_confirmed = 1, restaurant_confirmed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (self.reservation_id,))
            conn.commit()
            
            # Log action
            await log_action(
                self.reservation_id,
                'restaurant_confirmed',
                str(interaction.user),
                f"Confirmado por {interaction.user.name}"
            )
            
            # Send SMS to customer
            message = (
                f"Â¡Buenas noticias {res['nombre']}! "
                f"Tu reserva para {res['personas']} personas el {res['fecha']} "
                f"a las {res['hora']} estÃ¡ CONFIRMADA. Â¡Te esperamos! - Les Monges"
            )
            send_sms(res['telefono'], message)
            
            # Delete the message immediately
            try:
                await interaction.message.delete()
            except:
                pass  # Message might already be deleted
            
            await interaction.followup.send(
                f"âœ… Reserva #{self.reservation_id} confirmada y cliente notificado por SMS",
                ephemeral=True
            )

class CancelButton(Button):
    """Cancel button for confirmed reservations"""
    def __init__(self, reservation_id):
        super().__init__(
            style=discord.ButtonStyle.danger,
            label="âŒ Cancelar",
            custom_id=f"cancel_{reservation_id}"
        )
        self.reservation_id = reservation_id
    
    async def callback(self, interaction: discord.Interaction):
        # Create confirmation modal
        await interaction.response.send_modal(CancelModal(self.reservation_id))

class CancelModal(discord.ui.Modal, title="Confirmar CancelaciÃ³n"):
    """Modal to confirm cancellation"""
    reason = discord.ui.TextInput(
        label="Motivo (opcional)",
        style=discord.TextStyle.paragraph,
        required=False,
        placeholder="Ej: Cliente cancelÃ³, mesa no disponible..."
    )
    
    def __init__(self, reservation_id):
        super().__init__()
        self.reservation_id = reservation_id
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get reservation
            cursor.execute('SELECT * FROM reservations WHERE id = ?', (self.reservation_id,))
            res = cursor.fetchone()
            
            if not res:
                await interaction.followup.send("âŒ Reserva no encontrada", ephemeral=True)
                return
            
            if res['cancelled']:
                await interaction.followup.send("âš ï¸ Esta reserva ya estÃ¡ cancelada", ephemeral=True)
                return
            
            # Mark as cancelled
            cursor.execute('''
                UPDATE reservations 
                SET cancelled = 1, 
                    cancelled_at = CURRENT_TIMESTAMP,
                    cancelled_by = ?
                WHERE id = ?
            ''', (str(interaction.user), self.reservation_id))
            conn.commit()
            
            # Log action
            await log_action(
                self.reservation_id,
                'cancelled',
                str(interaction.user),
                self.reason.value or "Sin motivo especificado"
            )
            
            # Send SMS to customer
            message = (
                f"Hola {res['nombre']}, "
                f"lamentamos informarte que tu reserva para {res['personas']} personas "
                f"el {res['fecha']} a las {res['hora']} ha sido cancelada. "
                f"Por favor, contÃ¡ctanos al 965 78 57 31. - Les Monges"
            )
            send_sms(res['telefono'], message)
            
            # Sync channels to update display
            await sync_all_channels()
            
            await interaction.followup.send(
                f"âœ… Reserva #{self.reservation_id} cancelada y cliente notificado por SMS",
                ephemeral=True
            )

def create_reservation_embed(res, status_type):
    """Create Discord embed for a reservation"""
    # Determine color based on status
    if status_type == 'confirmed':
        color = discord.Color.green()
        title = "âœ… Reserva Confirmada"
    elif status_type == 'pending':
        color = discord.Color.orange()
        title = "â³ Pendiente de AprobaciÃ³n"
    else:
        color = discord.Color.red()
        title = "âŒ Cancelada"
    
    embed = discord.Embed(
        title=f"{title} - ID #{res['id']}",
        color=color,
        timestamp=datetime.fromisoformat(res['created_at'])
    )
    
    # Main info
    embed.add_field(name="ðŸ‘¤ Nombre", value=res['nombre'], inline=True)
    embed.add_field(name="ðŸ“ž TelÃ©fono", value=res['telefono'], inline=True)
    embed.add_field(name="ðŸ‘¥ Personas", value=str(res['personas']), inline=True)
    
    # Date/Time
    embed.add_field(name="ðŸ“… Fecha", value=res['fecha'], inline=True)
    embed.add_field(name="ðŸ• Hora", value=res['hora'], inline=True)
    embed.add_field(name="â° Creada", value=res['created_at'], inline=True)
    
    # Confirmation status
    user_check = "âœ…" if res['user_confirmed'] else "âŒ"
    restaurant_check = "âœ…" if res['restaurant_confirmed'] else "âŒ"
    embed.add_field(
        name="ðŸ“Š Estado",
        value=f"Cliente: {user_check}\nRestaurante: {restaurant_check}",
        inline=False
    )
    
    if res['notes']:
        embed.add_field(name="ðŸ“ Notas", value=res['notes'], inline=False)
    
    return embed

async def get_channel_state(channel_id):
    """
    Get current state of a channel
    Returns: dict with date -> list of reservation IDs
    """
    channel = bot.get_channel(channel_id)
    if not channel:
        return None
    
    current_state = {}
    current_date = None
    
    async for message in channel.history(limit=200, oldest_first=True):
        # Check if it's a date header
        if message.embeds and message.embeds[0].title and message.embeds[0].title.startswith("ðŸ“…"):
            # Extract date from header (parse it back)
            # We'll use a simpler approach: just track which reservation IDs we see
            current_date = message.embeds[0].title
            current_state[current_date] = []
        # Check if it's a reservation card
        elif message.embeds and message.embeds[0].title and "ID #" in message.embeds[0].title:
            # Extract reservation ID from title
            try:
                res_id = int(message.embeds[0].title.split("#")[1].split()[0])
                if current_date:
                    current_state[current_date].append(res_id)
            except:
                pass
    
    return current_state

async def get_database_state(status_type):
    """
    Get what the channel SHOULD look like based on database
    Returns: dict with date string -> list of reservation IDs
    """
    with get_db() as conn:
        cursor = conn.cursor()
        
        if status_type == 'confirmed':
            query = '''
                SELECT * FROM reservations 
                WHERE user_confirmed = 1 
                AND restaurant_confirmed = 1 
                AND cancelled = 0
                AND date(fecha) >= date('now')
                ORDER BY fecha, hora
            '''
        elif status_type == 'pending':
            query = '''
                SELECT * FROM reservations 
                WHERE user_confirmed = 1 
                AND restaurant_confirmed = 0 
                AND cancelled = 0
                ORDER BY fecha, hora
            '''
        else:
            return None
        
        cursor.execute(query)
        reservations = cursor.fetchall()
        
        # Group by date
        db_state = defaultdict(list)
        for res in reservations:
            fecha_obj = datetime.strptime(res['fecha'], '%Y-%m-%d')
            weekdays = ['Lunes', 'Martes', 'MiÃ©rcoles', 'Jueves', 'Viernes', 'SÃ¡bado', 'Domingo']
            months = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 
                     'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
            
            weekday = weekdays[fecha_obj.weekday()]
            day = fecha_obj.day
            month = months[fecha_obj.month - 1]
            date_header = f"ðŸ“… {weekday}, {day} de {month}"
            
            db_state[date_header].append(res['id'])
        
        return dict(db_state)

def states_match(channel_state, db_state):
    """Compare channel state with database state"""
    if channel_state is None or db_state is None:
        return False
    
    # Check if same dates
    if set(channel_state.keys()) != set(db_state.keys()):
        return False
    
    # Check if same reservations per date
    for date_header in db_state:
        channel_ids = set(channel_state.get(date_header, []))
        db_ids = set(db_state[date_header])
        if channel_ids != db_ids:
            return False
    
    return True

async def sync_channel_with_headers(channel_id, status_type):
    """Sync a specific channel with database, only if needed"""
    # Check if sync is needed
    channel_state = await get_channel_state(channel_id)
    db_state = await get_database_state(status_type)
    
    if states_match(channel_state, db_state):
        logger.info(f"Channel {status_type} is up to date, skipping rebuild")
        return
    
    logger.info(f"Channel {status_type} is out of sync, rebuilding...")
    
    channel = bot.get_channel(channel_id)
    if not channel:
        return
    
    # Clear entire channel
    await channel.purge(limit=200)
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        if status_type == 'confirmed':
            query = '''
                SELECT * FROM reservations 
                WHERE user_confirmed = 1 
                AND restaurant_confirmed = 1 
                AND cancelled = 0
                AND date(fecha) >= date('now')
                ORDER BY fecha, hora
            '''
        elif status_type == 'pending':
            query = '''
                SELECT * FROM reservations 
                WHERE user_confirmed = 1 
                AND restaurant_confirmed = 0 
                AND cancelled = 0
                ORDER BY fecha, hora
            '''
        else:
            return
        
        cursor.execute(query)
        reservations = cursor.fetchall()
        
        if not reservations:
            await channel.send("ðŸ“­ No hay reservas en este momento")
            return
        
        # Group reservations by date
        reservations_by_date = defaultdict(list)
        for res in reservations:
            reservations_by_date[res['fecha']].append(res)
        
        # Post reservations with date headers
        for fecha in sorted(reservations_by_date.keys()):
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d')
            
            weekdays = ['Lunes', 'Martes', 'MiÃ©rcoles', 'Jueves', 'Viernes', 'SÃ¡bado', 'Domingo']
            months = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 
                     'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
            
            weekday = weekdays[fecha_obj.weekday()]
            day = fecha_obj.day
            month = months[fecha_obj.month - 1]
            
            # Create date header
            header_embed = discord.Embed(
                title=f"ðŸ“… {weekday}, {day} de {month}",
                color=discord.Color.blue()
            )
            await channel.send(embed=header_embed)
            
            # Post all reservations for this date
            for res in reservations_by_date[fecha]:
                embed = create_reservation_embed(res, status_type)
                view = View(timeout=None)
                
                if status_type == 'confirmed':
                    view.add_item(CancelButton(res['id']))
                elif status_type == 'pending':
                    view.add_item(ConfirmButton(res['id']))
                    view.add_item(CancelButton(res['id']))
                
                message = await channel.send(embed=embed, view=view)
                
                # Track message ID in database
                with get_db() as conn2:
                    cursor2 = conn2.cursor()
                    cursor2.execute('''
                        INSERT INTO discord_messages (reservation_id, channel_type, message_id)
                        VALUES (?, ?, ?)
                    ''', (res['id'], status_type, str(message.id)))
                    conn2.commit()

async def sync_all_channels():
    """Sync all channels with database"""
    if CONFIRMED_CHANNEL_ID:
        await sync_channel_with_headers(CONFIRMED_CHANNEL_ID, 'confirmed')
    if PENDING_CHANNEL_ID:
        await sync_channel_with_headers(PENDING_CHANNEL_ID, 'pending')

async def refresh_channel(channel_id, status_type):
    """Refresh a specific channel with current reservations (legacy - redirects to sync)"""
    await sync_channel_with_headers(channel_id, status_type)

async def refresh_all_channels():
    """Refresh all channels (legacy - redirects to sync)"""
    await sync_all_channels()

@bot.event
async def on_ready():
    print(f'âœ… Bot conectado como {bot.user}')
    print(f'ðŸ“Š Canales configurados:')
    print(f'   - Confirmadas: {CONFIRMED_CHANNEL_ID}')
    print(f'   - Pendientes: {PENDING_CHANNEL_ID}')
    print(f'   - Log: {LOG_CHANNEL_ID}')
    
    # Start periodic refresh
    if not refresh_task.is_running():
        refresh_task.start()

@tasks.loop(minutes=10)
async def refresh_task():
    """
    Periodically check if channels need syncing
    Only rebuilds if channel state doesn't match database
    """
    logger.info("Running periodic sync check...")
    await sync_all_channels()
    logger.info("Sync check complete")

@bot.command()
@commands.has_permissions(administrator=True)
async def sync(ctx):
    """Sync channels with database - chronologically ordered with date headers"""
    await ctx.send("ðŸ”„ Sincronizando canales con base de datos...")
    await sync_all_channels()
    await ctx.send("âœ… Canales sincronizados y ordenados cronolÃ³gicamente")

@bot.command()
@commands.has_permissions(administrator=True)
async def refresh(ctx):
    """Manually refresh all channels (legacy - use !sync instead)"""
    await ctx.send("ðŸ”„ Actualizando canales...")
    await sync_all_channels()
    await ctx.send("âœ… Canales actualizados")

@bot.command()
@commands.has_permissions(administrator=True)
async def stats(ctx):
    """Show reservation statistics"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get counts
        cursor.execute('SELECT COUNT(*) FROM reservations WHERE cancelled = 0')
        total = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COUNT(*) FROM reservations 
            WHERE user_confirmed = 1 AND restaurant_confirmed = 1 AND cancelled = 0
        ''')
        confirmed = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COUNT(*) FROM reservations 
            WHERE user_confirmed = 1 AND restaurant_confirmed = 0 AND cancelled = 0
        ''')
        pending = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM reservations WHERE cancelled = 1')
        cancelled = cursor.fetchone()[0]
        
        embed = discord.Embed(title="ðŸ“Š EstadÃ­sticas de Reservas", color=discord.Color.blue())
        embed.add_field(name="Total Activas", value=str(total), inline=True)
        embed.add_field(name="âœ… Confirmadas", value=str(confirmed), inline=True)
        embed.add_field(name="â³ Pendientes", value=str(pending), inline=True)
        embed.add_field(name="âŒ Canceladas", value=str(cancelled), inline=True)
        
        await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_channels(ctx):
    """Create the required channels"""
    guild = ctx.guild
    
    # Create category
    category = await guild.create_category("ðŸ½ï¸ RESERVAS")
    
    # Create channels
    confirmed_channel = await guild.create_text_channel(
        "reservas-confirmadas",
        category=category,
        topic="Reservas confirmadas - Usa el botÃ³n para cancelar"
    )
    
    pending_channel = await guild.create_text_channel(
        "pendientes-aprobacion",
        category=category,
        topic="Reservas pendientes de aprobaciÃ³n - Usa el botÃ³n para aceptar o cancelar"
    )
    
    log_channel = await guild.create_text_channel(
        "log-acciones",
        category=category,
        topic="Registro de todas las acciones realizadas"
    )
    
    await ctx.send(f"""
âœ… Canales creados:
- {confirmed_channel.mention} (ID: {confirmed_channel.id})
- {pending_channel.mention} (ID: {pending_channel.id})
- {log_channel.mention} (ID: {log_channel.id})

**AÃ±ade estos IDs a tus variables de entorno:**
```
CONFIRMED_CHANNEL_ID={confirmed_channel.id}
PENDING_CHANNEL_ID={pending_channel.id}
LOG_CHANNEL_ID={log_channel.id}
```
    """)

if __name__ == '__main__':
    if not DISCORD_TOKEN:
        print("âŒ Error: DISCORD_BOT_TOKEN no configurado")
        exit(1)
    
    bot.run(DISCORD_TOKEN)
