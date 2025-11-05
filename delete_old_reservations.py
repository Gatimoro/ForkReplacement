#!/usr/bin/env python3
"""
Daily cleanup script to remove old reservations
Run this at 2 AM every day via cron
Deletes all reservations from yesterday and older
"""

import sqlite3
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_PATH = 'reservations.db'

def cleanup_old_reservations():
    """
    Remove reservations from yesterday and older
    Keeps today's reservations visible until tomorrow's cleanup
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Get count before cleanup
        cursor.execute("SELECT COUNT(*) FROM reservations WHERE date(fecha) < date('now')")
        old_count = cursor.fetchone()[0]
        
        if old_count == 0:
            logger.info("No old reservations to clean up")
            conn.close()
            return
        
        # Log what we're deleting
        cursor.execute('''
            SELECT id, nombre, telefono, fecha, hora, status 
            FROM reservations 
            WHERE date(fecha) < date('now')
        ''')
        old_reservations = cursor.fetchall()
        
        logger.info(f"Deleting {old_count} old reservations:")
        for res in old_reservations:
            logger.info(f"  ID {res[0]}: {res[1]} ({res[2]}) - {res[3]} {res[4]} [{res[5]}]")
        
        # Delete old reservations
        cursor.execute('''
            DELETE FROM reservations 
            WHERE date(fecha) < date('now')
        ''')
        
        conn.commit()
        logger.info(f"✅ Cleaned up {old_count} old reservations")
        
        # Also clean up orphaned Discord message tracking
        cursor.execute('''
            DELETE FROM discord_messages 
            WHERE reservation_id NOT IN (SELECT id FROM reservations)
        ''')
        deleted_messages = cursor.rowcount
        
        conn.commit()
        logger.info(f"✅ Cleaned up {deleted_messages} orphaned Discord message records")
        
        # Also clean up old action logs (keep last 30 days)
        cursor.execute('''
            DELETE FROM action_log 
            WHERE timestamp < datetime('now', '-30 days')
        ''')
        deleted_logs = cursor.rowcount
        
        conn.commit()
        logger.info(f"✅ Cleaned up {deleted_logs} old action log entries")
        
    except Exception as e:
        logger.error(f"❌ Error during cleanup: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    logger.info("="*60)
    logger.info(f"Starting daily cleanup at {datetime.now()}")
    logger.info("="*60)
    cleanup_old_reservations()
    logger.info("="*60)
    logger.info("Cleanup complete")
    logger.info("="*60)
