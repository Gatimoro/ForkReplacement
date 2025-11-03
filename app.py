#!/usr/bin/env python3
"""
Restaurant Reservation System - Backend API
Handles reservations and SMS confirmations via MensaTek API v7
"""

import os
import base64
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import requests
from contextlib import contextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Timezone configuration
TIMEZONE = ZoneInfo('Europe/Madrid')

def now():
    """Get current time in Spanish timezone"""
    return datetime.now(TIMEZONE)

# Flask app
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
    Check if booking is allowed based on opening times
    Morning service: 12:00 PM
    Evening service: 19:00 (7 PM)
    
    Returns: (allowed: bool, reason: str)
    """
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        hora = datetime.strptime(hora_str, '%H:%M').time()
        current = now()
        today = current.date()
        
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
        
        # Future dates always allowed
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

# ============================================================================
# API ENDPOINTS
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
        
        # Check for duplicate reservations (only active, user-confirmed ones count)
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
        import secrets
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
                 confirmation_token)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['nombre'],
                clean_phone,
                personas,
                data['fecha'],
                data['hora'],
                0,  # user_confirmed = False (MUST click SMS link first)
                0 if is_large else 1,  # restaurant_confirmed based on group size
                confirmation_token
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
                f"Hola {data['nombre']}! "
                f"Reserva para {personas} personas el {fecha_display} a las {data['hora']}. "
                f"Confirma aquí: {confirmation_link} "
                f"Revisaremos disponibilidad pronto. "
                f"- {RESTAURANT_NAME}"
            )
        else:
            sms_message = (
                f"Hola {data['nombre']}! "
                f"Reserva {RESTAURANT_NAME} el {fecha_display} a las {data['hora']} ({personas} personas). "
                f"Confirma aquí: {confirmation_link}"
            )
        
        # Send SMS
        sms_sent = send_sms(clean_phone, sms_message)
        
        if not sms_sent:
            logger.warning(f"SMS failed for reservation {reservation_id}")
        
        logger.info(f"✅ Reservation created: ID={reservation_id}, Token={confirmation_token}")
        
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
                
                # Look for ANY non-cancelled reservation with this token
                cursor.execute('''
                    SELECT * FROM reservations 
                    WHERE confirmation_token = ? 
                    AND cancelled = 0
                ''', (token,))
                
                reservation = cursor.fetchone()
                
                # Invalid token or cancelled
                if not reservation:
                    logger.warning(f"Invalid token or cancelled: {token}")
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
                                <p>Esta reserva no existe o ya fue cancelada.</p>
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
                                <p>Esta reserva ya fue confirmada o el enlace no es válido.</p>
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
                        f"Gracias por confirmar {reservation['nombre']}! "
                        f"Tu solicitud para {reservation['personas']} personas está registrada. "
                        f"Te contactaremos pronto para confirmar disponibilidad. "
                        f"Puedes cancelar con este enlace si es necesario."
                    )
                    logger.info(f"Large group {reservation['id']} SMS-confirmed, awaiting restaurant approval")
                else:
                    # SMS for small group - confirmed! Mention cancellation link
                    message = (
                        f"¡Perfecto {reservation['nombre']}! "
                        f"Reserva confirmada el {fecha_display} a las {reservation['hora']}. "
                        f"Les esperamos! Puedes cancelar con este mismo enlace si es necesario."
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
                
                # Send confirmation SMS
                send_sms(reservation['telefono'], message)
                
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
                WHERE confirmation_token = ? AND cancelled = 0
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
            
            logger.info(f"Reservation {reservation['id']} cancelled by customer")
            
            # Send cancellation SMS
            cancel_message = (
                f"Hola {reservation['nombre']}, "
                f"tu reserva para {reservation['personas']} personas "
                f"el {fecha_display} a las {reservation['hora']} ha sido cancelada. "
                f"Esperamos verte pronto. - {RESTAURANT_NAME}"
            )
            send_sms(reservation['telefono'], cancel_message)
            
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

@app.route('/')
def home():
    """Serve the main reservation page"""
    try:
        try:
            with open('templates/index.html', 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            with open('index.html', 'r', encoding='utf-8') as f:
                return f.read()
    except FileNotFoundError:
        return "index.html not found", 404

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

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    # Initialize database on startup
    init_database()
    
    # Log configuration
    logger.info("=" * 70)
    logger.info("Starting Restaurant Reservation System")
    logger.info("=" * 70)
    logger.info(f"SMS Enabled: {SMS_ENABLED}")
    logger.info(f"Large Group Threshold: >{LARGE_GROUP_THRESHOLD} people")
    logger.info(f"Domain: {DOMAIN}")
    logger.info(f"Restaurant: {RESTAURANT_NAME}")
    logger.info(f"Database: {DB_PATH}")
    logger.info("=" * 70)
    
    # Start server
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )
