#!/usr/bin/env python3
"""
Restaurant Reservation System - Backend API
Handles reservations and MS confirmations via MensaTek API v7
"""

# Standard library
import os
import base64
import logging
import secrets  
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from contextlib import contextmanager

# Third-party
from flask import Flask, request, jsonify, make_response, abort, send_from_directory, render_template
from flask_cors import CORS
import sqlite3
import requests
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, ReplyTo
from urllib.parse import quote
# Load environment variables
load_dotenv()

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# METRICS LOGGING HELPERS
# ============================================================================
def log_metric(event_type, **kwargs):
    """Log structured metrics for easy parsing and analysis"""
    parts = [f"{k}={v}" for k, v in kwargs.items()]
    logger.info(f"METRIC|{event_type}|{'|'.join(parts)}")


# ============================================================================
# TIMEZONE & TIME HELPERS
# ============================================================================

TIMEZONE = ZoneInfo('Europe/Madrid')

def now():
    """Get current time in Spanish timezone"""
    return datetime.now(TIMEZONE)

# ============================================================================
# FLASK APP INITIALIZATION
# ============================================================================

app = Flask(__name__)
CORS(app)

# ============================================================================
# CONFIGURATION - All configurable values from environment variables
# ============================================================================

# SMS Configuration
SMS_ENABLED = os.getenv('SMS_ENABLED', 'false').lower() == 'true'
MENSATEK_API_USER = os.getenv('MENSATEK_API_USER', '')
MENSATEK_API_TOKEN = os.getenv('MENSATEK_API_TOKEN', '')

# Business Logic
LARGE_GROUP_THRESHOLD = int(os.getenv('LARGE_GROUP_THRESHOLD', '4'))
DOMAIN = os.getenv('DOMAIN', 'http://localhost:5000/')

# Restaurant Info (for SMS messages)
RESTAURANT_NAME = os.getenv('RESTAURANT_NAME', 'Les Monges')
RESTAURANT_PHONE = os.getenv('RESTAURANT_PHONE', '965 78 57 31')

# Database
DB_PATH = os.getenv('DB_PATH', 'reservations.db')

# Default hours (mutated by load_default_hours_from_file())
DEFAULT_HOURS = ['13:00', '13:30', '14:00','14:30', '20:30', '21:00', '21:30','22:00']

# ============================================================================
# DATABASE SETUP
# ============================================================================

def init_database():
    """Initialize the database with all required tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Main reservations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            telefono TEXT NOT NULL,
            personas INTEGER NOT NULL,
            fecha DATE NOT NULL,
            hora TIME NOT NULL,
            
            -- Confirmation tracking (double verification)
            user_confirmed BOOLEAN DEFAULT 0,
            restaurant_confirmed BOOLEAN DEFAULT 0,
            
            -- Cancellation
            cancelled BOOLEAN DEFAULT 0,
            cancelled_at TIMESTAMP,
            cancelled_by TEXT,
            
            -- SMS confirmation token
            confirmation_token TEXT UNIQUE,
            
            -- Timestamps
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            -- Optional notes
            notes TEXT
        )
    ''')
    
    # Action log for Discord bot
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS action_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            performed_by TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            details TEXT,
            FOREIGN KEY (reservation_id) REFERENCES reservations(id)
        )
    ''')
    
    # Discord message tracking (for bot to update/delete messages)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS discord_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INTEGER NOT NULL,
            channel_type TEXT NOT NULL,
            message_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reservation_id) REFERENCES reservations(id)
        )
    ''')

    # Blocked hours table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blocked_hours (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATE NOT NULL,
            hora TIME NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(fecha, hora)
        )
    ''')
    
    # Create index for fast lookups
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_blocked_hours_fecha ON blocked_hours(fecha)')
    
    # Create indexes for performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_confirmation_token ON reservations(confirmation_token)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_confirmed ON reservations(user_confirmed)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_restaurant_confirmed ON reservations(restaurant_confirmed)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cancelled ON reservations(cancelled)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fecha ON reservations(fecha)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_action_log_timestamp ON action_log(timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_discord_messages_reservation ON discord_messages(reservation_id)')
    
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")

@contextmanager
def get_db():
    """Database connection context manager"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def send_sms(phone, message):
    """Send SMS via MensaTek API v7"""
    if not SMS_ENABLED:
        logger.info(f"📱 SMS SIMULATION to {phone}:")
        logger.info(f"   Message: {message}")
        return True
    
    if not MENSATEK_API_USER or not MENSATEK_API_TOKEN:
        logger.error("SMS credentials not configured!")
        return False
    
    try:
        url = "https://api.mensatek.com/v7/EnviarSMS"
        
        # Create basic auth header
        auth_string = f"{MENSATEK_API_USER}:{MENSATEK_API_TOKEN}"
        auth_encoded = base64.b64encode(auth_string.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {auth_encoded}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        # Clean phone number
        clean_phone = phone.replace(' ', '').replace('-', '')
        logger.debug(f"Sending SMS to: {clean_phone}")
        
        data = {
            'Remitente': RESTAURANT_NAME,
            'Destinatarios': f'[{{"Movil":"{clean_phone}"}}]',
            'Mensaje': message,
            'Resp': 'JSON'
        }
        
        response = requests.post(url, data=data, headers=headers, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"MENSATEK RESPONSE: {response.text}")
            result = response.json()
            if isinstance(result, list):
                result = result[0] if result else {}
            
            if result.get('Res') == 1:

                logger.info(f"✅ SMS sent successfully to {phone}")
                return True
            else:
                logger.error(f"SMS failed: {result}")
                return False
        else:
            logger.error(f"SMS HTTP error {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"SMS exception: {str(e)}")
        return False

def save_default_hours_to_file():
    """Save DEFAULT_HOURS to a JSON file"""
    try:
        with open('default_hours.json', 'w') as f:
            json.dump(DEFAULT_HOURS, f)
        logger.info("Default hours saved to file")
    except Exception as e:
        logger.error(f"Error saving default hours to file: {str(e)}")

def load_default_hours_from_file():
    """Load DEFAULT_HOURS from JSON file if it exists"""
    global DEFAULT_HOURS
    try:
        with open('default_hours.json', 'r') as f:
            DEFAULT_HOURS = json.load(f)
        logger.info(f"Default hours loaded from file: {DEFAULT_HOURS}")
    except FileNotFoundError:
        logger.info("No default_hours.json found, using hardcoded defaults")
    except Exception as e:
        logger.error(f"Error loading default hours from file: {str(e)}")
def is_large_group(personas):
    """Check if reservation requires manual confirmation"""
    return int(personas) > LARGE_GROUP_THRESHOLD

def clean_phone_number(phone):
    """Standardize phone number format"""
    clean = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    if not clean.startswith('+'):
        clean = '+' + clean
    return clean

def format_date_spanish(fecha_str):
    """Convert YYYY-MM-DD to DD/MM/YYYY"""
    fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d')
    return fecha_obj.strftime('%d/%m/%Y')

def get_current_timeslot():
    """
    Determine current timeslot for booking restrictions
    Returns: 'before_morning', 'morning', or 'evening'
    """
    current = now()
    hour = current.hour
    
    if hour < 12:
        return 'before_morning'
    elif 12 <= hour < 19:
        return 'morning'
    else:
        return 'evening'

def is_booking_allowed(fecha_str, hora_str):
    """
    Check if booking is allowed based on opening times and blocked hours
    Morning service: 12:00 PM
    Evening service: 19:00 (7 PM)
    
    Returns: (allowed: bool, reason: str)
    """
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        hora = datetime.strptime(hora_str, '%H:%M').time()
        current = now()
        today = current.date()
        
        # Check if hour is blocked
        if not is_hour_available(fecha_str, hora_str):
            return False, "Esta hora no está disponible"
        
        # Determine if booking is for morning or evening
        booking_timeslot = 'morning' if hora.hour < 19 else 'evening'
        
        # Past date check
        if fecha < today:
            return False, "No puedes reservar en una fecha pasada"
        
        # Today's bookings
        if fecha == today:
            current_time = get_current_timeslot()
            
            if current_time == 'before_morning':
                return True, ""
            elif current_time == 'morning':
                if booking_timeslot == 'morning':
                    return False, "Ya estamos sirviendo el almuerzo. Puedes reservar para esta noche o mañana"
                else:
                    return True, ""
            else:  # evening
                return False, "Ya estamos sirviendo la cena. Puedes reservar a partir de mañana"
        
        # Future dates always allowed (if not blocked)
        return True, ""
        
    except Exception as e:
        logger.error(f"Error validating booking time: {str(e)}")
        return False, f"Error al validar fecha/hora: {str(e)}"


def log_action(reservation_id, action_type, performed_by, details=None):
    """Log action to database (for Discord bot to read)"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO action_log (reservation_id, action_type, performed_by, details)
            VALUES (?, ?, ?, ?)
        ''', (reservation_id, action_type, performed_by, details))
        conn.commit()

def get_blocked_hours_for_date(fecha_str):
    """Get list of blocked hours for a specific date"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT hora FROM blocked_hours 
            WHERE fecha = ?
            ORDER BY hora
        ''', (fecha_str,))
        return [row['hora'] for row in cursor.fetchall()]


def get_available_hours_for_date(fecha_str):
    """Get list of available hours for a specific date"""
    blocked = get_blocked_hours_for_date(fecha_str)
    available = set(DEFAULT_HOURS) - set(blocked)
    return sorted(list(available))


def is_hour_available(fecha_str, hora_str):
    """Check if a specific hour is available for booking"""
    blocked = get_blocked_hours_for_date(fecha_str)
    return hora_str not in blocked

def notify_managers(message):
    """Send SMS to manager phone numbers for new reservations/cancellations"""
    manager_phones = os.getenv('MANAGER_PHONES', '').split(',')
    manager_phones = [p.strip() for p in manager_phones if p.strip()]
    
    if not manager_phones:
        logger.warning("No manager phones configured!")
        return
    
    for phone in manager_phones:
        send_sms(phone, message)
        logger.info(f"Manager notification sent to {phone}")


# ============================================================================
# PUBLIC API ENDPOINTS
# ============================================================================

@app.route('/reservar', methods=['POST'])
def create_reservation():
    """Handle reservation form submission"""
    try:
        data = request.json
        logger.info(f"Received reservation: {data}")
        
        # Validate required fields
        required_fields = ['nombre', 'telefono', 'personas', 'fecha', 'hora']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    'success': False,
                    'message': f'Campo requerido: {field}'
                }), 400
        
        # Clean phone number
        clean_phone = clean_phone_number(data['telefono'])
        
        # Check for duplicate reservations (only active, user-confirmed future ones count)
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM reservations 
                WHERE telefono = ? 
                AND user_confirmed = 1
                AND cancelled = 0
                AND date(fecha) >= date('now', 'localtime')
                ORDER BY fecha, hora
                LIMIT 1
            ''', (clean_phone,))
            existing = cursor.fetchone()
            
            if existing:
                fecha_display = format_date_spanish(existing["fecha"])
                return jsonify({
                    'success': False,
                    'message': f'Ya tienes una reserva activa para el {fecha_display} a las {existing["hora"]}. Si necesitas cambiarla, usa el enlace de cancelación que te enviamos por SMS.'
                }), 400
        
        # Validate booking time
        allowed, reason = is_booking_allowed(data['fecha'], data['hora'])
        if not allowed:
            return jsonify({
                'success': False,
                'message': reason
            }), 400
        
        # Generate confirmation token
        confirmation_token = secrets.token_urlsafe(16)
        
        # Check if large group (determines auto-approval)
        personas = int(data['personas'])
        is_large = is_large_group(personas)
        
        # Insert into database
        # Small groups: restaurant pre-approved (restaurant_confirmed=1)
        # Large groups: need approval (restaurant_confirmed=0)
        # BUT user still needs to click SMS link (user_confirmed=0)
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO reservations 
                (nombre, telefono, personas, fecha, hora, 
                 user_confirmed, restaurant_confirmed, 
                 confirmation_token, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['nombre'],
                clean_phone,
                personas,
                data['fecha'],
                data['hora'],
                0,  # user_confirmed = False (MUST click SMS link first)
                0 if is_large else 1,  # restaurant_confirmed based on group size
                confirmation_token,
                data.get('notes','')
            ))
            conn.commit()
            reservation_id = cursor.lastrowid
        
        # Log action
        log_action(reservation_id, 'created', 'web_form', f'Group size: {personas}, Auto-approved: {not is_large}')
        
        # Create confirmation link
        confirmation_link = f"{DOMAIN}confirm/{confirmation_token}"
        
        # Format date for display
        fecha_display = format_date_spanish(data['fecha'])
        
        # Prepare SMS message - MORE NATURAL
        if is_large:
            sms_message = (
                f"{data['nombre']}, CONFIRMA AQUÍ (confirm here):\n"
                f"{confirmation_link}\n"
                f"{fecha_display} {data['hora']} - {personas} pers.\n"
                f"Revisaremos disponibilidad.\n"
                f"Les Monges"
            )
        else:
            sms_message = (
                f"{data['nombre']}, confirma tu reserva (confirm):\n"
                f"{confirmation_link}\n"
                f"{fecha_display} {data['hora']} - {personas} pers.\n"
                f"Les Monges"
            )
        # Send SMS
        sms_sent = send_sms(clean_phone, sms_message)
        
        if not sms_sent:
            logger.warning(f"SMS failed for reservation {reservation_id}")
        
        logger.info(f"✅ Reservation created: ID={reservation_id}, Token={confirmation_token}")
        log_metric('reservation_created', 
                   id=reservation_id,
                   personas=personas,
                   fecha=data['fecha'],
                   hora=data['hora'],
                   large_group=is_large,
                   sms_sent=sms_sent)
        return jsonify({
            'success': True,
            'reservation_id': reservation_id,
            'large_group': is_large,
            'sms_sent': sms_sent,
            'message': 'Reserva registrada. Revisa tu móvil para confirmar.'
        })
        
    except Exception as e:
        logger.error(f"Error creating reservation: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error procesando la reserva. Por favor, intenta de nuevo.'
        }), 500

@app.route('/api/available-hours')
def api_available_hours():
    """Get available hours for a specific date (for frontend)"""
    try:
        # Load fresh hours from file
        load_default_hours_from_file()
        
        fecha = request.args.get('fecha')
        if not fecha:
            return jsonify({'success': False, 'message': 'Fecha requerida'}), 400
        
        # Get available hours (not blocked)
        available = get_available_hours_for_date(fecha)
        
        # Additional filtering for today
        fecha_date = datetime.strptime(fecha, '%Y-%m-%d').date()
        today = now().date()
        
        if fecha_date == today:
            current_hour = now().hour
            
            # Before 7 PM (19:00), only show evening slots (>= 19:00)
            if current_hour < 19:
                available = [h for h in available if datetime.strptime(h, '%H:%M').time().hour >= 19]
            else:
                # After 7 PM, no bookings for today
                available = []
        elif fecha_date < today:
            # No bookings for past dates
            available = []
        
        return jsonify({
            'success': True,
            'hours': available,
            'all_blocked': len(available) == 0
        })
        
    except Exception as e:
        logger.error(f"Error getting available hours: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ============================================================================
# CONFIRMATION & CANCELLATION ENDPOINTS
# ============================================================================

@app.route('/confirm/<token>', methods=['GET', 'POST'])
def confirm_reservation(token):
    """Handle customer confirmation via SMS link"""
    try:
        # Log User-Agent for debugging
        user_agent = request.headers.get('User-Agent', '')
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        logger.info(f"Confirmation attempt - Token: {token}, IP: {client_ip}, Method: {request.method}")
        
        # GET request: Show confirmation button OR show already-confirmed status
        if request.method == 'GET':
            with get_db() as conn:
                cursor = conn.cursor()
                
                # Look for ANY non-cancelled FUTURE reservation with this token
                cursor.execute('''
                    SELECT * FROM reservations 
                    WHERE confirmation_token = ? 
                    AND cancelled = 0
                    AND datetime(fecha || ' ' || hora) >= datetime('now', 'localtime')
                ''', (token,))
                
                reservation = cursor.fetchone()
                
                # Invalid token, cancelled, or past reservation
                # Invalid token, cancelled, or past reservation
                if not reservation:
                    logger.warning(f"Invalid token, cancelled, or past reservation: {token}")
                    return '''
                        <!DOCTYPE html>
                        <html lang="es">
                        <head>
                            <meta charset="UTF-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
                            <title>Error - Les Monges</title>
                            <style>
                                body { font-family: Georgia, serif; display: flex; justify-content: center; 
                                       align-items: center; min-height: 100vh; margin: 0; background: #f5f5f5; }
                                .container { text-align: center; padding: 40px; background: white; 
                                            border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); max-width: 500px; }
                                h1 { color: #dc3545; }
                                p { color: #666; margin: 20px 0; }
                                a { display: inline-block; margin-top: 20px; padding: 10px 20px; 
                                   background: #28a428; color: white; text-decoration: none; border-radius: 5px; }
                            </style>
                        </head>
                        <body>
                            <div class="container">
                                <h1>⚠️ Enlace inválido o expirado</h1>
                                <p>Esta reserva no existe, ya fue cancelada, o ya pasó la fecha.</p>
                                <a href="/">Volver al inicio</a>
                            </div>
                        </body>
                        </html>
                    '''
                
                # Format date for display
                fecha_display = format_date_spanish(reservation['fecha'])
                is_large = is_large_group(reservation['personas'])
                cancel_link = f"{DOMAIN}/cancel/{reservation['confirmation_token']}"
                
                # If NOT confirmed yet (user_confirmed = 0), show confirmation button
                if not reservation['user_confirmed']:
                    logger.info(f"Showing confirmation button for reservation {reservation['id']}")
                    return f'''
                        <!DOCTYPE html>
                        <html lang="es">
                        <head>
                            <meta charset="UTF-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
                            <title>Confirmar Reserva - {RESTAURANT_NAME}</title>
                            <style>
                                body {{ font-family: Georgia, serif; display: flex; justify-content: center;
                                       align-items: center; min-height: 100vh; margin: 0;
                                       background: linear-gradient(135deg, #faf8f3 0%, #fff 100%); }}
                                .container {{ text-align: center; padding: 40px; background: white;
                                            border-radius: 10px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); max-width: 500px; }}
                                h1 {{ color: #2a2523; margin: 20px 0; }}
                                p {{ color: #666; line-height: 1.6; margin: 15px 0; }}
                                .details {{ background: #f9f9f9; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                                .detail-row {{ display: flex; justify-content: space-between; margin: 10px 0; }}
                                .detail-label {{ font-weight: bold; color: #333; }}
                                .detail-value {{ color: #666; }}
                                .confirm-btn {{ display: inline-block; margin-top: 20px; padding: 15px 40px;
                                              background: #32cd32; color: white; text-decoration: none;
                                              border-radius: 8px; font-size: 1.1rem; font-weight: bold;
                                              border: none; cursor: pointer; transition: all 0.3s; }}
                                .confirm-btn:hover {{ background: #28a428; transform: translateY(-2px); }}
                            </style>
                        </head>
                        <body>
                            <div class="container">
                                <h1>📋 Confirma tu Reserva</h1>
                                <div class="details">
                                    <div class="detail-row">
                                        <span class="detail-label">Nombre:</span>
                                        <span class="detail-value">{reservation['nombre']}</span>
                                    </div>
                                    <div class="detail-row">
                                        <span class="detail-label">Fecha:</span>
                                        <span class="detail-value">{fecha_display}</span>
                                    </div>
                                    <div class="detail-row">
                                        <span class="detail-label">Hora:</span>
                                        <span class="detail-value">{reservation['hora']}</span>
                                    </div>
                                    <div class="detail-row">
                                        <span class="detail-label">Personas:</span>
                                        <span class="detail-value">{reservation['personas']}</span>
                                    </div>
                                </div>
                                <form method="POST">
                                    <button type="submit" class="confirm-btn">✓ Confirmar Reserva</button>
                                </form>
                            </div>
                        </body>
                        </html>
                    '''
                
                # Already confirmed (user_confirmed = 1), show info/cancel page
                logger.info(f"User revisiting already confirmed reservation {reservation['id']}")
                
                status_message = (
                    "Tu reserva está confirmada y te esperamos ese día" 
                    if not is_large or reservation['restaurant_confirmed']
                    else "Tu solicitud está pendiente de aprobación del restaurante"
                )
                
                return f'''
                    <!DOCTYPE html>
                    <html lang="es">
                    <head>
                        <meta charset="UTF-8">
                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        <title>Tu Reserva - {RESTAURANT_NAME}</title>
                        <style>
                            body {{ font-family: Georgia, serif; display: flex; justify-content: center;
                                   align-items: center; min-height: 100vh; margin: 0;
                                   background: linear-gradient(135deg, #faf8f3 0%, #fff 100%); }}
                            .container {{ text-align: center; padding: 40px; background: white;
                                        border-radius: 10px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); max-width: 500px; }}
                            .checkmark {{ width: 80px; height: 80px; margin: 0 auto 20px; background: #32cd32;
                                        border-radius: 50%; display: flex; align-items: center;
                                        justify-content: center; font-size: 40px; color: white; }}
                            h1 {{ color: #2a2523; margin: 20px 0; }}
                            p {{ color: #666; line-height: 1.6; margin: 15px 0; }}
                            .details {{ background: #f9f9f9; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                            .detail-row {{ display: flex; justify-content: space-between; margin: 10px 0; }}
                            .detail-label {{ font-weight: bold; color: #333; }}
                            .detail-value {{ color: #666; }}
                            a {{ display: inline-block; margin-top: 20px; padding: 12px 30px;
                                background: transparent; color: #666; text-decoration: none;
                                border: 2px solid #ddd; border-radius: 5px; transition: all 0.3s; }}
                            a:hover {{ background: #32cd32; color: white; border-color: #32cd32; }}
                            .cancel-btn {{ background: #dc3545; color: white; border-color: #dc3545; font-weight: bold; }}
                            .cancel-btn:hover {{ background: #c82333; border-color: #c82333; }}
                            .pending-approval {{ background: #fff3cd; border: 2px solid #ffc107;
                                              padding: 15px; border-radius: 8px; margin: 20px 0; }}
                            .actions {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <div class="checkmark">✓</div>
                            <h1>{'¡Reserva Confirmada!' if not is_large or reservation['restaurant_confirmed'] else '¡Solicitud Recibida!'}</h1>
                            <p>{status_message}</p>
                            {'<div class="pending-approval">⏳ Grupos grandes requieren confirmación del restaurante. Te contactaremos en breve.</div>' if is_large and not reservation['restaurant_confirmed'] else ''}
                            <div class="details">
                                <div class="detail-row">
                                    <span class="detail-label">Nombre:</span>
                                    <span class="detail-value">{reservation['nombre']}</span>
                                </div>
                                <div class="detail-row">
                                    <span class="detail-label">Fecha:</span>
                                    <span class="detail-value">{fecha_display}</span>
                                </div>
                                <div class="detail-row">
                                    <span class="detail-label">Hora:</span>
                                    <span class="detail-value">{reservation['hora']}</span>
                                </div>
                                <div class="detail-row">
                                    <span class="detail-label">Personas:</span>
                                    <span class="detail-value">{reservation['personas']}</span>
                                </div>
                            </div>
                            <div class="actions">
                                <p><small>¿Necesitas cancelar tu reserva?</small></p>
                                <a href="{cancel_link}" class="cancel-btn">✕ Cancelar mi Reserva</a>
                            </div>
                            <a href="/">Volver al inicio</a>
                        </div>
                    </body>
                    </html>
                '''
        
        # POST request: Actually confirm (only real users will POST)
        if request.method == 'POST':
            with get_db() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT * FROM reservations 
                    WHERE confirmation_token = ? 
                    AND user_confirmed = 0 
                    AND cancelled = 0
                    AND datetime(fecha || ' ' || hora) >= datetime('now', 'localtime')
                ''', (token,))
                
                reservation = cursor.fetchone()
                
                if not reservation:
                    logger.warning(f"Invalid token for POST: {token}")
                    return '''
                        <!DOCTYPE html>
                        <html lang="es">
                        <head>
                            <meta charset="UTF-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
                            <title>Error - Les Monges</title>
                            <style>
                                body { font-family: Georgia, serif; display: flex; justify-content: center; 
                                       align-items: center; min-height: 100vh; margin: 0; background: #f5f5f5; }
                                .container { text-align: center; padding: 40px; background: white; 
                                            border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); max-width: 500px; }
                                h1 { color: #dc3545; }
                                p { color: #666; margin: 20px 0; }
                                a { display: inline-block; margin-top: 20px; padding: 10px 20px; 
                                   background: #28a428; color: white; text-decoration: none; border-radius: 5px; }
                            </style>
                        </head>
                        <body>
                            <div class="container">
                                <h1>⚠️ Enlace inválido o expirado</h1>
                                <p>Esta reserva ya fue confirmada, cancelada, o ya pasó la fecha.</p>
                                <a href="/">Volver al inicio</a>
                            </div>
                        </body>
                        </html>
                    '''
                
                # Determine confirmation flow based on group size
                is_large = is_large_group(reservation['personas'])
                
                # Format date for display
                fecha_display = format_date_spanish(reservation['fecha'])
                
                if is_large:
                    # SMS for large group - mention they'll be contacted
                    message = (
                        f"Gracias {reservation['nombre']}!\n"
                        f"Solicitud para {reservation['personas']} pers. recibida.\n"
                        f"Te confirmaremos pronto.\n"
                        f"Cancelar: mismo enlace (cancel: same link)"
                    )
                    logger.info(f"Large group {reservation['id']} SMS-confirmed, awaiting restaurant approval")
                else:
                    # SMS for small group - confirmed! Mention cancellation link
                    message = (
                        f"¡Confirmado {reservation['nombre']}!\n"
                        f"{fecha_display} {reservation['hora']}, {reservation['personas']} pers.\n"
                        f"¡Te esperamos!\n"
                        f"Cancelar: mismo enlace (cancel: same link)"
                    )
                    logger.info(f"Small group {reservation['id']} fully confirmed")
                
                # Update database - mark user as confirmed
                cursor.execute('''
                    UPDATE reservations 
                    SET user_confirmed = 1
                    WHERE id = ?
                ''', (reservation['id'],))
                conn.commit()
                
                # Log action
                log_action(reservation['id'], 'user_confirmed', 'customer', 'Via SMS link')
                # log metric
                log_metric('user_confirmed',
                   id=reservation['id'],
                   personas=reservation['personas'],
                   fecha=reservation['fecha'],
                   hora=reservation['hora'],
                   large_group=is_large)
                # Send confirmation SMS
                send_sms(reservation['telefono'], message)

                # Notify managers of new confirmed/pending reservation
                manager_notif = (
                    f"Nueva reserva {'PENDIENTE' if is_large else 'CONFIRMADA'}: "
                    f"{fecha_display} {reservation['hora']}. "
                    f"{reservation['personas']} personas, {reservation['nombre']}. "
                    f"Tel: {reservation['telefono']}"
                )
                notify_managers(manager_notif)

                # Create cancellation link
                cancel_link = f"{DOMAIN}/cancel/{reservation['confirmation_token']}"
                
                return f'''
                    <!DOCTYPE html>
                    <html lang="es">
                    <head>
                        <meta charset="UTF-8">
                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        <title>Reserva Confirmada - {RESTAURANT_NAME}</title>
                        <style>
                            body {{ font-family: Georgia, serif; display: flex; justify-content: center;
                                   align-items: center; min-height: 100vh; margin: 0;
                                   background: linear-gradient(135deg, #faf8f3 0%, #fff 100%); }}
                            .container {{ text-align: center; padding: 40px; background: white;
                                        border-radius: 10px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); max-width: 500px; }}
                            .checkmark {{ width: 80px; height: 80px; margin: 0 auto 20px; background: #32cd32;
                                        border-radius: 50%; display: flex; align-items: center;
                                        justify-content: center; font-size: 40px; color: white; }}
                            h1 {{ color: #2a2523; margin: 20px 0; }}
                            p {{ color: #666; line-height: 1.6; margin: 15px 0; }}
                            .details {{ background: #f9f9f9; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                            .detail-row {{ display: flex; justify-content: space-between; margin: 10px 0; }}
                            .detail-label {{ font-weight: bold; color: #333; }}
                            .detail-value {{ color: #666; }}
                            a {{ display: inline-block; margin-top: 20px; padding: 12px 30px;
                                background: transparent; color: #666; text-decoration: none;
                                border: 2px solid #ddd; border-radius: 5px; transition: all 0.3s; }}
                            a:hover {{ background: #32cd32; color: white; border-color: #32cd32; }}
                            .cancel-btn {{ background: #dc3545; color: white; border-color: #dc3545; font-weight: bold; }}
                            .cancel-btn:hover {{ background: #c82333; border-color: #c82333; }}
                            .pending-approval {{ background: #fff3cd; border: 2px solid #ffc107;
                                              padding: 15px; border-radius: 8px; margin: 20px 0; }}
                            .actions {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <div class="checkmark">✓</div>
                            <h1>{'¡Reserva Confirmada!' if not is_large else '¡Solicitud Recibida!'}</h1>
                            <p>{message}</p>
                            {'<div class="pending-approval">⏳ Grupos grandes requieren confirmación del restaurante. Te contactaremos en breve.</div>' if is_large else ''}
                            <div class="details">
                                <div class="detail-row">
                                    <span class="detail-label">Fecha:</span>
                                    <span class="detail-value">{fecha_display}</span>
                                </div>
                                <div class="detail-row">
                                    <span class="detail-label">Hora:</span>
                                    <span class="detail-value">{reservation['hora']}</span>
                                </div>
                                <div class="detail-row">
                                    <span class="detail-label">Personas:</span>
                                    <span class="detail-value">{reservation['personas']}</span>
                                </div>
                            </div>
                            <p><small>Te hemos enviado un SMS de confirmación</small></p>
                            <div class="actions">
                                <p><small>¿Necesitas cancelar?</small></p>
                                <a href="{cancel_link}" class="cancel-btn">✕ Cancelar mi Reserva</a>
                            </div>
                            <a href="/">Volver al inicio</a>
                        </div>
                    </body>
                    </html>
                '''
            
    except Exception as e:
        logger.error(f"Error confirming reservation: {str(e)}")
        return "Error procesando la confirmación", 500

@app.route('/cancel/<token>', methods=['GET'])
def cancel_reservation(token):
    """Handle customer cancellation via link"""
    try:
        logger.info(f"Cancellation attempt with token: {token}")
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM reservations 
                WHERE confirmation_token = ? 
                AND cancelled = 0
                AND date(fecha || ' ' || hora) >= datetime('now', 'localtime')
            ''', (token,))
            
            reservation = cursor.fetchone()
            
            if not reservation:
                logger.warning(f"Invalid token or already cancelled: {token}")
                return '''
                    <!DOCTYPE html>
                    <html lang="es">
                    <head>
                        <meta charset="UTF-8">
                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        <title>Error - Les Monges</title>
                        <style>
                            body { font-family: Georgia, serif; display: flex; justify-content: center;
                                   align-items: center; min-height: 100vh; margin: 0; background: #f5f5f5; }
                            .container { text-align: center; padding: 40px; background: white;
                                        border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); max-width: 500px; }
                            h1 { color: #dc3545; }
                            p { color: #666; margin: 20px 0; }
                            a { display: inline-block; margin-top: 20px; padding: 10px 20px;
                               background: #28a428; color: white; text-decoration: none; border-radius: 5px; }
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <h1>⚠️ Enlace inválido</h1>
                            <p>Esta reserva ya fue cancelada o el enlace no es válido.</p>
                            <a href="/">Volver al inicio</a>
                        </div>
                    </body>
                    </html>
                '''
            
            # Format date for display
            fecha_display = format_date_spanish(reservation['fecha'])
            
            # Cancel the reservation
            cursor.execute('''
                UPDATE reservations 
                SET cancelled = 1, 
                    cancelled_at = CURRENT_TIMESTAMP, 
                    cancelled_by = 'customer'
                WHERE id = ?
            ''', (reservation['id'],))
            conn.commit()
            
            # Log action
            log_action(reservation['id'], 'cancelled', 'customer', 'Via cancellation link')
            #and metric
            log_metric('reservation_cancelled',
               id=reservation['id'],
               personas=reservation['personas'],
               fecha=reservation['fecha'],
               hora=reservation['hora'],
               cancelled_by='customer')
            logger.info(f"Reservation {reservation['id']} cancelled by customer")
            
            # Send cancellation SMS
            cancel_message = (
                f"{reservation['nombre']}, reserva cancelada (reservation cancelled)\n"
                f"{fecha_display} {reservation['hora']}, {reservation['personas']} pers.\n"
                f"¡Esperamos verte pronto! Hope to see you soon!"
            )

            send_sms(reservation['telefono'], cancel_message)
            # Notify managers of cancellation
            manager_cancel_notif = (
                f"Cancelación: {reservation['nombre']}, "
                f"{reservation['personas']} personas, "
                f"{fecha_display} {reservation['hora']}. "
                f"Tel: {reservation['telefono']}"
            )
            notify_managers(manager_cancel_notif)
            
            return f'''
                <!DOCTYPE html>
                <html lang="es">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Reserva Cancelada - {RESTAURANT_NAME}</title>
                    <style>
                        body {{ font-family: Georgia, serif; display: flex; justify-content: center;
                               align-items: center; min-height: 100vh; margin: 0;
                               background: linear-gradient(135deg, #fff5f5 0%, #fff 100%); }}
                        .container {{ text-align: center; padding: 40px; background: white;
                                    border-radius: 10px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); max-width: 500px; }}
                        .icon {{ width: 80px; height: 80px; margin: 0 auto 20px; background: #dc3545;
                                border-radius: 50%; display: flex; align-items: center;
                                justify-content: center; font-size: 40px; color: white; }}
                        h1 {{ color: #2a2523; margin: 20px 0; }}
                        p {{ color: #666; line-height: 1.6; margin: 15px 0; }}
                        .details {{ background: #f9f9f9; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                        .detail-row {{ display: flex; justify-content: space-between; margin: 10px 0; }}
                        .detail-label {{ font-weight: bold; color: #333; }}
                        .detail-value {{ color: #666; text-decoration: line-through; }}
                        a {{ display: inline-block; margin-top: 20px; padding: 12px 30px;
                            background: #28a428; color: white; text-decoration: none;
                            border-radius: 5px; transition: all 0.3s; }}
                        a:hover {{ background: #218838; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="icon">✕</div>
                        <h1>Reserva Cancelada</h1>
                        <p>Tu reserva ha sido cancelada exitosamente.</p>
                        <div class="details">
                            <div class="detail-row">
                                <span class="detail-label">Fecha:</span>
                                <span class="detail-value">{fecha_display}</span>
                            </div>
                            <div class="detail-row">
                                <span class="detail-label">Hora:</span>
                                <span class="detail-value">{reservation['hora']}</span>
                            </div>
                            <div class="detail-row">
                                <span class="detail-label">Personas:</span>
                                <span class="detail-value">{reservation['personas']}</span>
                            </div>
                        </div>
                        <p><small>Te hemos enviado un SMS de confirmación de la cancelación</small></p>
                        <p>¡Esperamos verte pronto en {RESTAURANT_NAME}!</p>
                        <a href="/">Hacer una nueva reserva</a>
                    </div>
                </body>
                </html>
            '''
            
    except Exception as e:
        logger.error(f"Error cancelling reservation: {str(e)}")
        return "Error procesando la cancelación", 500



# ============================================================================
# STATIC PAGE ROUTES
# ============================================================================

@app.route('/tasca-les-monges')
def home():
    """Serve the main reservation page"""
    try:
        with open('templates/index.html', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "index.html not found", 404

@app.route('/')
def index():
    return home()

@app.route('/txoco-bar')
def txoco_bar():
    """Serve the Txoco Bar landing page"""
    try:
        with open('templates/txoco.html', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "txoco.html not found", 404

@app.route('/contact', methods=['GET'])
def contact_page():
    try:
        with open('templates/contact.html', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "contact.html not found", 404   

@app.route('/contacto', methods=['POST'])
def contact_form():
    """Handle contact form submission via SendGrid"""
    try:
        data = request.json
        logger.info(f"📧 Received contact form: {data}")
        
        # Validate required fields
        if not data.get('nombre') or not data.get('email') or not data.get('mensaje'):
            return jsonify({
                'success': False,
                'message': 'Por favor completa todos los campos obligatorios'
            }), 400
        
        # Get SendGrid API key
        sendgrid_api_key = os.environ.get('SENDGRID_API_KEY')
        if not sendgrid_api_key:
            logger.error("❌ SENDGRID_API_KEY not configured!")
            return jsonify({
                'success': False,
                'message': 'Error de configuración del servidor'
            }), 500
        
        # Compose email message
        message = Mail(
            from_email=Email('noreply@em9835.email.lesmongesdenia.com', 'Tasca Les Monges'),
            to_emails=[
                To('lesmonges@hotmail.com'),
                To('makarborisov123@gmail.com')
            ],
            subject=f'📧 Consulta web - {data["nombre"]}',
            plain_text_content=f"""
Nueva consulta desde el formulario de contacto:

Nombre: {data['nombre']}
Email: {data['email']}

Mensaje:
{data['mensaje']}

---
Responder: https://lesmongesdenia.com/reply?email={quote(data['email'])}&name={quote(data['nombre'])}&msg={quote(data['mensaje'])}
            """
        )
        
        # Set reply-to so you can just hit "Reply" and it goes to the customer
        message.reply_to = Email(data['email'], data['nombre'])
        
        # Send via SendGrid
        sg = SendGridAPIClient(sendgrid_api_key)
        response = sg.send(message)
        
        logger.info(f"✅ Email sent successfully! Status: {response.status_code}")
        
        return jsonify({
            'success': True,
            'message': '¡Gracias por tu mensaje! Te responderemos pronto.'
        })
        
    except Exception as e:
        logger.error(f"❌ Error processing contact form: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error procesando el mensaje. Por favor, intenta de nuevo.'
        }), 500

@app.route('/reply', methods=['GET', 'POST'])
def reply_form():
    if request.method == 'GET':
        return render_template('reply.html', 
            email=request.args.get('email', ''),
            name=request.args.get('name', ''),
            original_msg=request.args.get('msg', '')
        )
    
    try:
        client_email = request.form.get('email')
        client_name = request.form.get('name', 'Cliente')
        mensaje = request.form.get('mensaje')
        original_msg = request.form.get('original_msg', '')
        
        if not client_email or not mensaje:
            return "Faltan datos", 400
        
        sendgrid_api_key = os.environ.get('SENDGRID_API_KEY')
        if not sendgrid_api_key:
            return "Error de configuracion", 500
        
        message = Mail(
            from_email=Email('noreply@em9835.email.lesmongesdenia.com', 'Tasca Les Monges'),
            to_emails=To(client_email),
            subject='Respuesta de Les Monges',
            plain_text_content=f"Hola {client_name},\n\n{mensaje}\n\n--\nTasca Les Monges\n\n---\n\n Re:{original_msg}"
        )
        
        sg = SendGridAPIClient(sendgrid_api_key)
        sg.send(message)
        logger.info(f"Reply sent to {client_email}")
        
        return """
        <script>
            alert('Enviado correctamente!');
            window.close();
        </script>
        """
        
    except Exception as e:
        logger.error(f"Error sending reply: {str(e)}")
        return """
    <script>
        alert('Error, llama a Makar');
        history.back();
    </script>
    """

@app.route('/success')
def success_page():
    """Serve the success page"""
    try:
        try:
            with open('templates/success.html', 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            with open('success.html', 'r', encoding='utf-8') as f:
                return f.read()
    except FileNotFoundError:
        return "success.html not found", 404

@app.route('/error')
def error_page():
    """Serve the error page"""
    try:
        try:
            with open('templates/error.html', 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            with open('error.html', 'r', encoding='utf-8') as f:
                return f.read()
    except FileNotFoundError:
        return "error.html not found", 404

@app.route('/admin')
def admin_page():
    """Serve the admin panel"""
    try:
        try:
            with open('templates/admin.html', 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            with open('admin.html', 'r', encoding='utf-8') as f:
                return f.read()
    except FileNotFoundError:
        return "admin.html not found", 404

#menu link
@app.route('/la-carta')
def show_menu():
    try:
        return send_from_directory('static', 'menu.pdf')
    except FileNotFoundError:
        abort(404, description="Menu PDF not found")

# ============================================================================
# ADMIN API ENDPOINTS
# ============================================================================
@app.route('/api/admin/calendar')
def admin_calendar():
    """Get calendar data with reservation counts per day"""
    try:
        month = int(request.args.get('month', now().month))
        year = int(request.args.get('year', now().year))
        
        # Get first and last day of month
        first_day = datetime(year, month, 1, tzinfo=TIMEZONE)
        if month == 12:
            last_day = datetime(year + 1, 1, 1, tzinfo=TIMEZONE)
        else:
            last_day = datetime(year, month + 1, 1, tzinfo=TIMEZONE)
        
        # Get day of week for first day (0 = Monday)
        first_weekday = first_day.weekday()
        
        # Calculate days to show before first day
        days_before = first_weekday
        
        # Calculate total days in month
        days_in_month = (last_day - first_day).days
        
        # Calculate days to show after last day to complete grid
        total_cells = days_before + days_in_month
        days_after = (7 - (total_cells % 7)) % 7
        
        # Get reservation counts - separated by status
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Confirmed reservations (both user and restaurant confirmed)
            cursor.execute('''
                SELECT fecha, COUNT(*) as count
                FROM reservations
                WHERE cancelled = 0
                AND user_confirmed = 1
                AND restaurant_confirmed = 1
                AND fecha >= date(?, '-' || ? || ' days')
                AND fecha < date(?, '+' || ? || ' days')
                GROUP BY fecha
            ''', (first_day.strftime('%Y-%m-%d'), days_before, 
                  last_day.strftime('%Y-%m-%d'), days_after))
            
            confirmed_counts = {row['fecha']: row['count'] for row in cursor.fetchall()}
            
            # Pending reservations (user confirmed but not restaurant)
            cursor.execute('''
                SELECT fecha, COUNT(*) as count
                FROM reservations
                WHERE cancelled = 0
                AND user_confirmed = 1
                AND restaurant_confirmed = 0
                AND fecha >= date(?, '-' || ? || ' days')
                AND fecha < date(?, '+' || ? || ' days')
                GROUP BY fecha
            ''', (first_day.strftime('%Y-%m-%d'), days_before, 
                  last_day.strftime('%Y-%m-%d'), days_after))
            
            pending_counts = {row['fecha']: row['count'] for row in cursor.fetchall()}
        
        # Build calendar data
        calendar_days = []
        current = first_day - timedelta(days=days_before)
        today = now().date()
        
        for i in range(days_before + days_in_month + days_after):
            date_str = current.strftime('%Y-%m-%d')
            calendar_days.append({
                'date': date_str,
                'day': current.day,
                'confirmed_count': confirmed_counts.get(date_str, 0),
                'pending_count': pending_counts.get(date_str, 0),
                'otherMonth': current.month != month,
                'isToday': current.date() == today
            })
            current += timedelta(days=1)
        
        return jsonify({
            'success': True,
            'month': month,
            'year': year,
            'days': calendar_days
        })
        
    except Exception as e:
        logger.error(f"Error generating calendar: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/reservations')
def admin_reservations():
    """Get reservations with filtering and sorting"""
    try:
        status = request.args.get('status', 'all')
        sort = request.args.get('sort', 'fecha')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        fecha = request.args.get('fecha')  # Specific date filter
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Build query based on status
            where_clauses = []
            params = []
            
            if status == 'confirmed':
                where_clauses.append('user_confirmed = 1')
                where_clauses.append('restaurant_confirmed = 1')
                where_clauses.append('cancelled = 0')
            elif status == 'pending':
                where_clauses.append('user_confirmed = 1')
                where_clauses.append('restaurant_confirmed = 0')
                where_clauses.append('cancelled = 0')
            elif status == 'active':
                where_clauses.append('cancelled = 0')
            elif status == 'cancelled':
                where_clauses.append('cancelled = 1')
            
            # Date filters
            if fecha:
                where_clauses.append('fecha = ?')
                params.append(fecha)
            else:
                if date_from:
                    where_clauses.append('fecha >= ?')
                    params.append(date_from)
                if date_to:
                    where_clauses.append('fecha <= ?')
                    params.append(date_to)
            
            where_sql = ' AND '.join(where_clauses) if where_clauses else '1=1'
            
            # Determine sort order
            valid_sorts = ['fecha', 'created_at', 'cancelled_at', 'personas', 'hora']
            if sort not in valid_sorts:
                sort = 'fecha'
            
            query = f'''
                SELECT * FROM reservations
                WHERE {where_sql}
                ORDER BY {sort} DESC, hora
            '''
            
            cursor.execute(query, params)
            reservations = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'success': True,
            'reservations': reservations
        })
        
    except Exception as e:
        logger.error(f"Error fetching reservations: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/raw')
def admin_raw():
    """Get raw database dump"""
    try:
        limit = request.args.get('limit', '100')
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            if limit == 'all':
                query = 'SELECT * FROM reservations ORDER BY id DESC'
            else:
                query = f'SELECT * FROM reservations ORDER BY id DESC LIMIT {int(limit)}'
            
            cursor.execute(query)
            reservations = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'success': True,
            'reservations': reservations
        })
        
    except Exception as e:
        logger.error(f"Error fetching raw data: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/cancel/<int:reservation_id>', methods=['POST'])
def admin_cancel_reservation(reservation_id):
    """Cancel a reservation from admin panel"""
    try:
        data = request.json
        reason = data.get('reason', 'Cancelado desde panel admin')
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get reservation
            cursor.execute('SELECT * FROM reservations WHERE id = ?', (reservation_id,))
            reservation = cursor.fetchone()
            
            if not reservation:
                return jsonify({'success': False, 'message': 'Reserva no encontrada'}), 404
            
            if reservation['cancelled']:
                return jsonify({'success': False, 'message': 'Reserva ya cancelada'}), 400
            
            # Cancel it
            cursor.execute('''
                UPDATE reservations 
                SET cancelled = 1,
                    cancelled_at = CURRENT_TIMESTAMP,
                    cancelled_by = ?
                WHERE id = ?
            ''', ('admin', reservation_id))
            conn.commit()
            
            # Log action
            log_action(reservation_id, 'cancelled', 'admin', reason)
            #and metric
            log_metric('reservation_cancelled',
                   id=reservation_id,
                   personas=reservation['personas'],
                   fecha=reservation['fecha'],
                   hora=reservation['hora'],
                   cancelled_by='admin',
                   reason=reason)
            # Send SMS notification
            fecha_display = format_date_spanish(reservation['fecha'])
            message = (
                f"Lamentamos cancelar tu reserva (sorry, reservation cancelled), {reservation['nombre']}.\n"
                f"{fecha_display} {reservation['hora']}, {reservation['personas']} pers.\n"
                f"Motivo: {reason}\n"
                f"Llámanos (call us): {RESTAURANT_PHONE}"
            )
            send_sms(reservation['telefono'], message)
        
        logger.info(f"Admin cancelled reservation {reservation_id}")
        
        return jsonify({
            'success': True,
            'message': 'Reserva cancelada exitosamente'
        })
        
    except Exception as e:
        logger.error(f"Error cancelling reservation: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/approve/<int:reservation_id>', methods=['POST'])
def admin_approve_reservation(reservation_id):
    """Approve a pending reservation (large group)"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get reservation
            cursor.execute('SELECT * FROM reservations WHERE id = ?', (reservation_id,))
            reservation = cursor.fetchone()
            
            if not reservation:
                return jsonify({'success': False, 'message': 'Reserva no encontrada'}), 404
            
            if reservation['cancelled']:
                return jsonify({'success': False, 'message': 'Reserva cancelada'}), 400
            
            if reservation['restaurant_confirmed']:
                return jsonify({'success': False, 'message': 'Reserva ya aprobada'}), 400
            
            # Approve it
            cursor.execute('''
                UPDATE reservations 
                SET restaurant_confirmed = 1
                WHERE id = ?
            ''', (reservation_id,))
            conn.commit()
            
            # Log action
            log_action(reservation_id, 'restaurant_confirmed', 'admin', 'Aprobado desde panel admin')
            #and metric
            log_metric('reservation_approved',
                   id=reservation_id,
                   personas=reservation['personas'],
                   fecha=reservation['fecha'],
                   hora=reservation['hora'])       
            # Send SMS notification
            fecha_display = format_date_spanish(reservation['fecha'])
            message = (
                f"{reservation['nombre']}, RESERVA APROBADA (approved by restaurant)\n"
                f"{fecha_display} {reservation['hora']}, {reservation['personas']} pers.\n"
                f"¡Te esperamos! See you then!\n"
                f"Cancelar: mismo enlace (cancel: same link)"
            )
            send_sms(reservation['telefono'], message)
        
        logger.info(f"Admin approved reservation {reservation_id}")
        
        return jsonify({
            'success': True,
            'message': 'Reserva aprobada exitosamente'
        })
        
    except Exception as e:
        logger.error(f"Error approving reservation: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/default-hours', methods=['GET'])
def admin_get_default_hours():
    """Get current default hours configuration"""
    try:
        # Always read fresh from file
        load_default_hours_from_file()
        
        return jsonify({
            'success': True,
            'hours': DEFAULT_HOURS
        })
        
    except Exception as e:
        logger.error(f"Error getting default hours: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/default-hours', methods=['POST'])
def admin_set_default_hours():
    """Update default hours configuration"""
    try:
        data = request.json
        new_hours = data.get('hours', [])
        
        if not new_hours or len(new_hours) == 0:
            return jsonify({
                'success': False, 
                'message': 'Debes seleccionar al menos un horario'
            }), 400
        
        # Validate hours format
        for hora in new_hours:
            try:
                datetime.strptime(hora, '%H:%M')
            except ValueError:
                return jsonify({
                    'success': False,
                    'message': f'Formato de hora inválido: {hora}'
                }), 400
        
        # Update the global DEFAULT_HOURS variable
        global DEFAULT_HOURS
        DEFAULT_HOURS = sorted(new_hours)
        
        # Optionally: Save to a config file so it persists across restarts
        # For now, it will reset on server restart (which is fine for your use case)

        save_default_hours_to_file()
        logger.info(f"Default hours updated to: {DEFAULT_HOURS}")
        
        return jsonify({
            'success': True,
            'message': f'Horarios actualizados: {len(DEFAULT_HOURS)} horarios configurados',
            'hours': DEFAULT_HOURS
        })
        
    except Exception as e:
        logger.error(f"Error setting default hours: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


#- ADMIN END - ADMIN END - ADMIN END - ADMIN END - ADMIN END - ADMIN END - ADMIN END - ADMIN END - ADMIN END - 




@app.route('/api/admin/blocked-hours/<fecha>')
def admin_get_blocked_hours(fecha):
    """Get blocked hours for a specific date"""
    try:
        load_default_hours_from_file()

        blocked = get_blocked_hours_for_date(fecha)
        available = get_available_hours_for_date(fecha)
        
        # Get reservation counts per hour for this date
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT hora, COUNT(*) as count
                FROM reservations
                WHERE fecha = ? AND cancelled = 0
                GROUP BY hora
            ''', (fecha,))
            reservation_counts = {row['hora']: row['count'] for row in cursor.fetchall()}
        
        return jsonify({
            'success': True,
            'fecha': fecha,
            'default_hours': DEFAULT_HOURS,
            'blocked': blocked,
            'available': available,
            'reservation_counts': reservation_counts
        })
        
    except Exception as e:
        logger.error(f"Error getting blocked hours: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/blocked-hours/<fecha>/<hora>', methods=['POST'])
def admin_block_hour(fecha, hora):
    """Block a specific hour on a specific date"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Check if already blocked
            cursor.execute('''
                SELECT id FROM blocked_hours 
                WHERE fecha = ? AND hora = ?
            ''', (fecha, hora))
            
            if cursor.fetchone():
                return jsonify({'success': False, 'message': 'Ya está bloqueada'}), 400
            
            # Block it
            cursor.execute('''
                INSERT INTO blocked_hours (fecha, hora)
                VALUES (?, ?)
            ''', (fecha, hora))
            conn.commit()
        
        logger.info(f"Blocked {hora} on {fecha}")
        
        return jsonify({
            'success': True,
            'message': f'Hora {hora} bloqueada'
        })
        
    except Exception as e:
        logger.error(f"Error blocking hour: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/blocked-hours/<fecha>/<hora>', methods=['DELETE'])
def admin_unblock_hour(fecha, hora):
    """Unblock a specific hour on a specific date"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM blocked_hours 
                WHERE fecha = ? AND hora = ?
            ''', (fecha, hora))
            
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'No estaba bloqueada'}), 400
            
            conn.commit()
        
        logger.info(f"Unblocked {hora} on {fecha}")
        
        return jsonify({
            'success': True,
            'message': f'Hora {hora} desbloqueada'
        })
        
    except Exception as e:
        logger.error(f"Error unblocking hour: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/blocked-hours/<fecha>/block-all', methods=['POST'])
def admin_block_all_hours(fecha):
    """Block all hours for a specific date"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Delete existing blocks for this date
            cursor.execute('DELETE FROM blocked_hours WHERE fecha = ?', (fecha,))
            
            # Insert all default hours as blocked
            for hora in DEFAULT_HOURS:
                cursor.execute('''
                    INSERT INTO blocked_hours (fecha, hora)
                    VALUES (?, ?)
                ''', (fecha, hora))
            
            conn.commit()
        
        logger.info(f"Blocked all hours on {fecha}")
        
        return jsonify({
            'success': True,
            'message': 'Todas las horas bloqueadas'
        })
        
    except Exception as e:
        logger.error(f"Error blocking all hours: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/blocked-hours/<fecha>/unblock-all', methods=['POST'])
def admin_unblock_all_hours(fecha):
    """Unblock all hours for a specific date"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM blocked_hours WHERE fecha = ?', (fecha,))
            conn.commit()
        
        logger.info(f"Unblocked all hours on {fecha}")
        
        return jsonify({
            'success': True,
            'message': 'Todas las horas desbloqueadas'
        })
        
    except Exception as e:
        logger.error(f"Error unblocking all hours: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# INITIALIZATION - Runs on import (works with gunicorn)
# ============================================================================

# Initialize database on startup
init_database()

# Load default hours from file
load_default_hours_from_file()

# Log configuration with detailed info
logger.info("=" * 70)
logger.info("🍽️  Restaurant Reservation System Starting")
logger.info("=" * 70)
logger.info(f"📱 SMS Enabled: {SMS_ENABLED}")
if SMS_ENABLED:
    logger.info(f"   SMS User: {MENSATEK_API_USER}")
    logger.info(f"   Manager Phones: {os.getenv('MANAGER_PHONES', 'NOT SET')}")
logger.info(f"👥 Large Group Threshold: >{LARGE_GROUP_THRESHOLD} people")
logger.info(f"🌐 Domain: {DOMAIN}")
logger.info(f"🏪 Restaurant: {RESTAURANT_NAME}")
logger.info(f"📞 Restaurant Phone: {RESTAURANT_PHONE}")
logger.info(f"💾 Database: {DB_PATH}")
logger.info(f"🕐 Default Hours: {DEFAULT_HOURS}")
logger.info(f"   Total hours configured: {len(DEFAULT_HOURS)}")

# Show breakdown of lunch vs dinner hours
lunch_hours = [h for h in DEFAULT_HOURS if datetime.strptime(h, '%H:%M').hour < 19]
dinner_hours = [h for h in DEFAULT_HOURS if datetime.strptime(h, '%H:%M').hour >= 19]
logger.info(f"   Lunch slots ({len(lunch_hours)}): {lunch_hours}")
logger.info(f"   Dinner slots ({len(dinner_hours)}): {dinner_hours}")

# Show timezone info
logger.info(f"⏰ Timezone: Europe/Madrid (current time: {now().strftime('%Y-%m-%d %H:%M:%S')})")
logger.info("=" * 70)

# ============================================================================
# MAIN - Only for direct execution (flask run or python app.py)
# ============================================================================

if __name__ == '__main__':
    # Start server (only when running directly, not with gunicorn)
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False
    )
