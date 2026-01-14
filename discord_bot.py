#!/usr/bin/env python3
"""
Discord Bot for Restaurant Reservation Management
Channels:
- #reservas-confirmadas: Shows confirmed reservations with cancel & call buttons
- #pendientes-aprobacion: Shows pending restaurant approval with accept, cancel & call buttons
- #log-acciones: Action log for tracking all actions
"""

import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import sqlite3
import os
from datetime import datetime
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
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Configuration
DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
DB_PATH = 'reservations.db'
RESTAURANT_NAME = os.getenv('RESTAURANT_NAME', 'Les Monges')
RESTAURANT_PHONE = os.getenv('RESTAURANT_PHONE', '965 78 57 31')

# Channel IDs (set these after creating channels)
CONFIRMED_CHANNEL_ID = int(os.getenv('CONFIRMED_CHANNEL_ID', '0'))
PENDING_CHANNEL_ID = int(os.getenv('PENDING_CHANNEL_ID', '0'))
TODAY_CHANNEL_ID = int(os.getenv('TODAY_CHANNEL_ID', '0'))
LOG_CHANNEL_ID = int(os.getenv('LOG_CHANNEL_ID', '0'))
CONTACT_CHANNEL_ID = int(os.getenv('CONTACT_CHANNEL_ID', '0'))
last_checked_action_id = 0 #for 'real time' updates
last_checked_contact_id = 0 #for contact form monitoring
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
    """Send SMS (import from app.py)"""
    import sys
    sys.path.append('.')
    from app import send_sms as app_send_sms
    return app_send_sms(phone, message)

def format_date_spanish(fecha_str):
    """Convert YYYY-MM-DD to DD/MM/YYYY for display"""
    fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d')
    return fecha_obj.strftime('%d/%m/%Y')

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
                fecha_display = format_date_spanish(res['fecha'])
                
                embed = discord.Embed(
                    title=f"📝 {action_type.upper()}",
                    color=discord.Color.blue() if action_type == 'confirmed' else discord.Color.red(),
                    timestamp=datetime.utcnow()
                )
                embed.add_field(name="ID", value=str(reservation_id), inline=True)
                embed.add_field(name="Nombre", value=res['nombre'], inline=True)
                embed.add_field(name="Personas", value=str(res['personas']), inline=True)
                embed.add_field(name="Fecha/Hora", value=f"{fecha_display} {res['hora']}", inline=False)
                embed.add_field(name="Realizado por", value=performed_by, inline=False)
                if details:
                    embed.add_field(name="Detalles", value=details, inline=False)
                
                await channel.send(embed=embed)

class CallButton(Button):
    """Call button to display phone number"""
    def __init__(self, phone_number):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="📞 Llamar",
            custom_id=f"call_{phone_number}"
        )
        self.phone_number = phone_number
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"📞 Teléfono: **{self.phone_number}**\n\n"
            f"_Puedes llamar directamente a este número_",
            ephemeral=True
        )

class ConfirmButton(Button):
    """Accept button for pending reservations"""
    def __init__(self, reservation_id):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="✅ Aceptar",
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
                await interaction.followup.send("❌ Reserva no encontrada", ephemeral=True)
                return
            
            if res['restaurant_confirmed']:
                await interaction.followup.send("⚠️ Esta reserva ya está confirmada", ephemeral=True)
                return
            
            # Update to confirmed
            cursor.execute('''
                UPDATE reservations 
                SET restaurant_confirmed = 1, 
                    status = 'confirmed'
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
            
            # Format date for SMS
            fecha_display = format_date_spanish(res['fecha'])
            
            # Send SMS to customer
            message = (
                f"{res['nombre']}, RESERVA APROBADA (approved by restaurant)\n"
                f"{fecha_display} {res['hora']}, {res['personas']} pers.\n"
                f"¡Te esperamos! See you then!\n"
                f"Cancelar: mismo enlace (cancel: same link)"
            )
            send_sms(res['telefono'], message)
            
            # Delete the message from pending channel
            try:
                await interaction.message.delete()
            except:
                pass
            
            # Sync channels to show in confirmed
            await sync_all_channels()
            
            await interaction.followup.send(
                f"✅ Reserva #{self.reservation_id} confirmada y cliente notificado por SMS",
                ephemeral=True
            )

class CancelButton(Button):
    """Cancel button for reservations"""
    def __init__(self, reservation_id):
        super().__init__(
            style=discord.ButtonStyle.danger,
            label="❌ Cancelar",
            custom_id=f"cancel_{reservation_id}"
        )
        self.reservation_id = reservation_id
    
    async def callback(self, interaction: discord.Interaction):
        # Create confirmation modal
        await interaction.response.send_modal(CancelModal(self.reservation_id))

class CancelModal(discord.ui.Modal, title="Confirmar Cancelación"):
    """Modal to confirm cancellation"""
    reason = discord.ui.TextInput(
        label="Motivo (opcional)",
        style=discord.TextStyle.paragraph,
        required=False,
        placeholder="Ej: Cliente canceló, mesa no disponible..."
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
                await interaction.followup.send("❌ Reserva no encontrada", ephemeral=True)
                return
            
            if res['cancelled']:
                await interaction.followup.send("⚠️ Esta reserva ya está cancelada", ephemeral=True)
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
            
            # Log action (sync function, no await)
            await log_action(
                self.reservation_id,
                'cancelled',
                str(interaction.user),
                self.reason.value or "Sin motivo especificado"
            )
            
            # Format date for SMS
            fecha_display = format_date_spanish(res['fecha'])
            
            # Send SMS to customer (sync function, no await)
            message = (
                f"Lamentamos cancelar tu reserva (sorry, reservation cancelled), {res['nombre']}.\n"
                f"{fecha_display} {res['hora']}, {res['personas']} pers.\n"
                f"Motivo: {self.reason.value or 'Sin especificar'}\n"
                f"Llámanos (call us): {RESTAURANT_PHONE}"
            )
            send_sms(res['telefono'], message)
            
            # Delete the message immediately
            try:
                await interaction.message.delete()
            except:
                pass
            
            await interaction.followup.send(
                f"✅ Reserva #{self.reservation_id} cancelada y cliente notificado por SMS",
                ephemeral=True
            )

class CopyEmailButton(Button):
    """Copy email button for contact messages"""
    def __init__(self, email):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="📋 Copiar email",
            custom_id=f"copy_email_{email}"
        )
        self.email = email

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"📋 Email copiado:\n```{self.email}```\n\n"
            f"_Usa Ctrl+C para copiar desde el cuadro de código arriba_",
            ephemeral=True
        )

class MarkReadButton(Button):
    """Mark as read button for contact messages"""
    def __init__(self, contact_id):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="✓ Marcar como leído",
            custom_id=f"mark_read_{contact_id}"
        )
        self.contact_id = contact_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        with get_db() as conn:
            cursor = conn.cursor()

            # Mark as read
            cursor.execute('''
                UPDATE contact_messages
                SET read = 1
                WHERE id = ?
            ''', (self.contact_id,))
            conn.commit()

        # Delete the message
        try:
            await interaction.message.delete()
        except:
            pass

        await interaction.followup.send(
            f"✅ Mensaje #{self.contact_id} marcado como leído",
            ephemeral=True
        )

def create_contact_embed(contact):
    """Create Discord embed for a contact message matching notification.html style"""
    # Orange color from notification.html: #f59e0b = 16162315 decimal
    embed = discord.Embed(
        title="📩 Nuevo contacto de cliente",
        color=16162315,  # Orange (#f59e0b)
        timestamp=datetime.strptime(contact['created_at'], '%Y-%m-%d %H:%M:%S')
    )

    # Cliente field
    embed.add_field(
        name="CLIENTE",
        value=f"**{contact['nombre']}**",
        inline=False
    )

    # Email field with code block for easy copying
    embed.add_field(
        name="EMAIL",
        value=f"```{contact['email']}```",
        inline=False
    )

    # Message field
    mensaje = contact['mensaje']
    if len(mensaje) > 1024:
        mensaje = mensaje[:1021] + "..."

    embed.add_field(
        name="MENSAJE",
        value=mensaje,
        inline=False
    )

    embed.set_footer(text=f"Contacto web • ID #{contact['id']}")

    return embed

def create_reservation_embed(res, status_type):
    """Create Discord embed for a reservation - SIMPLIFIED"""
    # Determine color based on status
    if status_type == 'confirmed':
        color = discord.Color.green()
        icon = "✅"
    elif status_type == 'pending':
        color = discord.Color.orange()
        icon = "⏳"
    else:
        color = discord.Color.blue()
        icon = "📅"
    
    embed = discord.Embed(
        title=f"{icon} {res['hora']} · {res['nombre']} · {res['personas']}p",
        color=color
    )
    
    # Optional: Add phone in footer for quick reference
    embed.set_footer(text=f"📞 {res['telefono']} • ID #{res['id']}")
    
    # Add notes if present
    if res['notes']:
        embed.description = f"📝 {res['notes']}"
    
    return embed

async def get_channel_state(channel_id):
    """Get current state of a channel - returns dict with date -> list of reservation IDs"""
    channel = bot.get_channel(channel_id)
    if not channel:
        return None
    
    current_state = {}
    current_date = None
    
    async for message in channel.history(limit=200, oldest_first=True):
        # Check if it's a date header (NEW format: ═══ Lunes · 23 ═══)
        if message.embeds and message.embeds[0].title and "═══" in message.embeds[0].title:
            current_date = message.embeds[0].title
            current_state[current_date] = []
        # Check if it's a TODAY header
        elif message.embeds and message.embeds[0].title and "🌟" in message.embeds[0].title:
            current_date = message.embeds[0].title
            current_state[current_date] = []
        # Check if it's a reservation card (NEW format: ID in footer)
        elif message.embeds and message.embeds[0].footer and message.embeds[0].footer.text:
            # Extract ID from footer: "📞 +34... • ID #5"
            try:
                footer_text = message.embeds[0].footer.text
                if "ID #" in footer_text:
                    res_id = int(footer_text.split("ID #")[1].split()[0])
                    if current_date:
                        current_state[current_date].append(res_id)
            except:
                pass
    
    return current_state

async def get_database_state(status_type):
    """Get what the channel SHOULD look like based on database"""
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
        elif status_type == 'today':
            query = '''
                SELECT * FROM reservations 
                WHERE user_confirmed = 1 
                AND restaurant_confirmed = 1 
                AND cancelled = 0
                AND date(fecha) = date('now')
                ORDER BY hora
            '''
        else:
            return None
        
        cursor.execute(query)
        reservations = cursor.fetchall()
        
        # Group by date
        db_state = defaultdict(list)
        
        # Special handling for TODAY channel
        if status_type == 'today':
            if reservations:
                # Create the big TODAY header
                today = datetime.now()
                weekdays = ['LUNES', 'MARTES', 'MIÉRCOLES', 'JUEVES', 'VIERNES', 'SÁBADO', 'DOMINGO']
                months = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 
                         'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
                
                weekday = weekdays[today.weekday()]
                day = today.day
                month = months[today.month - 1]
                
                date_header = f"🌟 {weekday} {day} DE {month.upper()} 🌟"
                db_state[date_header] = [res['id'] for res in reservations]
            return dict(db_state)
        
        # For confirmed/pending channels
        for res in reservations:
            fecha_obj = datetime.strptime(res['fecha'], '%Y-%m-%d')
            weekdays = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
            months = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 
                     'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
            
            weekday = weekdays[fecha_obj.weekday()]
            day = fecha_obj.day
            month = months[fecha_obj.month - 1]
            
            # MUST match the format in sync_channel_with_headers EXACTLY
            date_header = f"═══ {weekday} · {day:02d} {month} ═══"
            
            db_state[date_header].append(res['id'])
        
        return dict(db_state)

def states_match(channel_state, db_state):
    """Compare channel state with database state"""
    if channel_state is None or db_state is None:
        return False
    
    if set(channel_state.keys()) != set(db_state.keys()):
        return False
    
    for date_header in db_state:
        channel_ids = set(channel_state.get(date_header, []))
        db_ids = set(db_state[date_header])
        if channel_ids != db_ids:
            return False
    
    return True

async def sync_channel_with_headers(channel_id, status_type):
    """Sync a specific channel with database, only if needed"""
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
        elif status_type == 'today':
            query = '''
                SELECT * FROM reservations 
                WHERE user_confirmed = 1 
                AND restaurant_confirmed = 1 
                AND cancelled = 0
                AND date(fecha) = date('now')
                ORDER BY hora
            '''
        else:
            return
        
        cursor.execute(query)
        reservations = cursor.fetchall()
        
        if not reservations:
            await channel.send("🔭 No hay reservas en este momento")
            return
        
        # Special header for TODAY channel
        if status_type == 'today':
            today = datetime.now()
            weekdays = ['LUNES', 'MARTES', 'MIÉRCOLES', 'JUEVES', 'VIERNES', 'SÁBADO', 'DOMINGO']
            months = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 
                     'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
            
            weekday = weekdays[today.weekday()]
            day = today.day
            month = months[today.month - 1]
            
            # BIG TODAY HEADER
            header_embed = discord.Embed(
                title=f"🌟 {weekday} {day} DE {month.upper()} 🌟",
                description=f"Total: {len(reservations)} reservas hoy",
                color=discord.Color.gold()
            )
            await channel.send(embed=header_embed)
            
            # Post all today's reservations
            for res in reservations:
                embed = create_reservation_embed(res, 'today')
                view = View(timeout=None)
                view.add_item(CallButton(res['telefono']))
                view.add_item(CancelButton(res['id']))
                
                await channel.send(embed=embed, view=view)
            
            return
        
        # Group reservations by date for confirmed/pending channels
        reservations_by_date = defaultdict(list)
        for res in reservations:
            reservations_by_date[res['fecha']].append(res)
        
        # Post reservations with date headers
        for fecha in sorted(reservations_by_date.keys()):
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d')
            
            weekdays = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
            months = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 
                     'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
            
            weekday = weekdays[fecha_obj.weekday()]
            day = fecha_obj.day
            month = months[fecha_obj.month - 1]
            
            # Create aesthetic date header
            header_embed = discord.Embed(
                title=f"═══ {weekday} · {day:02d} {month} ═══",
                color=discord.Color.blue()
            )
            await channel.send(embed=header_embed)
            
            # Post all reservations for this date
            for res in reservations_by_date[fecha]:
                embed = create_reservation_embed(res, status_type)
                view = View(timeout=None)
                
                # Add buttons based on channel type
                if status_type == 'confirmed':
                    view.add_item(CallButton(res['telefono']))
                    view.add_item(CancelButton(res['id']))
                elif status_type == 'pending':
                    view.add_item(ConfirmButton(res['id']))
                    view.add_item(CallButton(res['telefono']))
                    view.add_item(CancelButton(res['id']))
                
                message = await channel.send(embed=embed, view=view)
                
                # Track message ID in database
                with get_db() as conn2:
                    cursor2 = conn2.cursor()
                    cursor2.execute('''
                        INSERT OR REPLACE INTO discord_messages (reservation_id, channel_type, message_id)
                        VALUES (?, ?, ?)
                    ''', (res['id'], status_type, str(message.id)))
                    conn2.commit()

async def sync_all_channels():
    """Sync all channels with database"""
    if TODAY_CHANNEL_ID:
        await sync_channel_with_headers(TODAY_CHANNEL_ID, 'today')
    if CONFIRMED_CHANNEL_ID:
        await sync_channel_with_headers(CONFIRMED_CHANNEL_ID, 'confirmed')
    if PENDING_CHANNEL_ID:
        await sync_channel_with_headers(PENDING_CHANNEL_ID, 'pending')

@bot.event
async def on_ready():
    global last_checked_action_id, last_checked_contact_id

    print(f'✅ Bot conectado como {bot.user}')
    print(f'📊 Canales configurados:')
    print(f'   - Hoy: {TODAY_CHANNEL_ID}')
    print(f'   - Confirmadas: {CONFIRMED_CHANNEL_ID}')
    print(f'   - Pendientes: {PENDING_CHANNEL_ID}')
    print(f'   - Log: {LOG_CHANNEL_ID}')
    print(f'   - Contacto: {CONTACT_CHANNEL_ID}')

    # Initialize last_checked_action_id to latest action in DB
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT MAX(id) as max_id FROM action_log')
        result = cursor.fetchone()
        last_checked_action_id = result['max_id'] if result['max_id'] else 0

        # Initialize last_checked_contact_id to latest contact message in DB
        cursor.execute('SELECT MAX(id) as max_id FROM contact_messages')
        result = cursor.fetchone()
        last_checked_contact_id = result['max_id'] if result['max_id'] else 0

    print(f'🔄 Iniciando sync en tiempo real desde action_log ID: {last_checked_action_id}')
    print(f'📧 Iniciando monitor de contactos desde ID: {last_checked_contact_id}')

    # Start periodic refresh (every 10 min as backup)
    if not refresh_task.is_running():
        refresh_task.start()

    # Start real-time sync (every 5 seconds)
    if not realtime_sync_task.is_running():
        realtime_sync_task.start()

    # Start contact monitor (every 5 seconds)
    if CONTACT_CHANNEL_ID and not contact_monitor_task.is_running():
        contact_monitor_task.start()
        print(f'📩 Monitor de contactos iniciado')


#SYNC LOOPS
@tasks.loop(minutes=10)
async def refresh_task():
    """Periodically check if channels need syncing"""
    logger.info("Running periodic sync check...")
    await sync_all_channels()
    logger.info("Sync check complete")
@tasks.loop(seconds=5)
async def realtime_sync_task():
    """Check for new reservations every 5 seconds and sync immediately"""
    global last_checked_action_id
    
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get latest action log entries since last check
            cursor.execute('''
                SELECT id, reservation_id, action_type, timestamp
                FROM action_log
                WHERE id > ?
                ORDER BY id ASC
            ''', (last_checked_action_id,))
            
            new_actions = cursor.fetchall()
            
            if new_actions:
                logger.info(f"Found {len(new_actions)} new actions, syncing channels...")
                
                # Update last checked ID
                last_checked_action_id = new_actions[-1]['id']
                
                # Sync channels immediately
                await sync_all_channels()
                
                logger.info("Real-time sync complete")
    
    except Exception as e:
        logger.error(f"Error in real-time sync: {str(e)}")

@tasks.loop(seconds=5)
async def contact_monitor_task():
    """Monitor for new contact messages and post to Discord"""
    global last_checked_contact_id

    if not CONTACT_CHANNEL_ID:
        return

    try:
        with get_db() as conn:
            cursor = conn.cursor()

            # Get new unread contact messages since last check
            cursor.execute('''
                SELECT * FROM contact_messages
                WHERE id > ? AND read = 0
                ORDER BY id ASC
            ''', (last_checked_contact_id,))

            new_contacts = cursor.fetchall()

            if new_contacts:
                logger.info(f"Found {len(new_contacts)} new contact messages")

                channel = bot.get_channel(CONTACT_CHANNEL_ID)
                if not channel:
                    logger.error(f"Contact channel {CONTACT_CHANNEL_ID} not found!")
                    return

                for contact in new_contacts:
                    # Create embed matching notification.html style
                    embed = create_contact_embed(contact)

                    # Create view with buttons
                    view = View(timeout=None)
                    view.add_item(CopyEmailButton(contact['email']))
                    view.add_item(MarkReadButton(contact['id']))

                    # Send to Discord
                    await channel.send(embed=embed, view=view)

                    logger.info(f"📩 Posted contact message #{contact['id']} to Discord")

                    # Update last checked ID
                    last_checked_contact_id = contact['id']

    except Exception as e:
        logger.error(f"Error in contact monitor: {str(e)}")

@bot.command()
@commands.has_permissions(administrator=True)
async def sync(ctx):
    """Sync channels with database - chronologically ordered with date headers"""
    await ctx.send("🔄 Sincronizando canales con base de datos...")
    await sync_all_channels()
    await ctx.send("✅ Canales sincronizados y ordenados cronológicamente")

@bot.command()
@commands.has_permissions(administrator=True)
async def stats(ctx):
    """Show reservation statistics"""
    with get_db() as conn:
        cursor = conn.cursor()
        
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
        
        embed = discord.Embed(title="📊 Estadísticas de Reservas", color=discord.Color.blue())
        embed.add_field(name="Total Activas", value=str(total), inline=True)
        embed.add_field(name="✅ Confirmadas", value=str(confirmed), inline=True)
        embed.add_field(name="⏳ Pendientes", value=str(pending), inline=True)
        embed.add_field(name="❌ Canceladas", value=str(cancelled), inline=True)
        
        await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_channels(ctx):
    """Create the required channels"""
    guild = ctx.guild
    
    # Create category
    category = await guild.create_category("🍽️ RESERVAS")
    
    # Create channels
    today_channel = await guild.create_text_channel(
        "📅-hoy",
        category=category,
        topic="Reservas de HOY - Vista rápida del día"
    )
    
    confirmed_channel = await guild.create_text_channel(
        "✅-confirmadas",
        category=category,
        topic="Reservas confirmadas - Usa los botones para llamar o cancelar"
    )
    
    pending_channel = await guild.create_text_channel(
        "⏳-pendientes",
        category=category,
        topic="Pendientes de aprobación - Usa los botones para aceptar, llamar o cancelar"
    )
    
    log_channel = await guild.create_text_channel(
        "📋-log",
        category=category,
        topic="Registro de todas las acciones realizadas"
    )
    
    await ctx.send(f"""
✅ Canales creados:
- {today_channel.mention} (ID: {today_channel.id})
- {confirmed_channel.mention} (ID: {confirmed_channel.id})
- {pending_channel.mention} (ID: {pending_channel.id})
- {log_channel.mention} (ID: {log_channel.id})

**Añade estos IDs a tu archivo `.env`:**
```
TODAY_CHANNEL_ID={today_channel.id}
CONFIRMED_CHANNEL_ID={confirmed_channel.id}
PENDING_CHANNEL_ID={pending_channel.id}
LOG_CHANNEL_ID={log_channel.id}
```

Luego reinicia el bot y usa `!sync` para cargar las reservas.
    """)

if __name__ == '__main__':
    if not DISCORD_TOKEN:
        print("❌ Error: DISCORD_BOT_TOKEN no configurado")
        exit(1)
    
    bot.run(DISCORD_TOKEN)
