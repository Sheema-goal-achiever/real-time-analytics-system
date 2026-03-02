import websocket
import json
import mysql.connector
import os
import time
from datetime import datetime
from mysql.connector import Error
from dotenv import load_dotenv

load_dotenv()

# Configuration from Environment / Secrets
DB_SETTINGS = {
    "host": os.getenv("AIVEN_HOST"),
    "port": int(os.getenv("AIVEN_PORT", 3306)),
    "user": os.getenv("AIVEN_USER"),
    "password": os.getenv("AIVEN_PASSWORD"),
    "database": os.getenv("AIVEN_DATABASE"),
    "pool_name": "mypool",
    "pool_size": 5  # Connection pooling handles high-frequency trades better
}

def get_db_connection():
    """Returns a connection from the pool."""
    try:
        return mysql.connector.connect(**DB_SETTINGS, autocommit=True)
    except Error as e:
        print(f"❌ Could not connect to Aiven: {e}")
        return None

def fetch_config():
    """Fetches Binance URL and Category Mapping."""
    conn = get_db_connection()
    if not conn: return None, None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT DATA_SOURCE_URL, CATEGORY_MAP FROM CLIENT_CONFIG LIMIT 1")
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row:
            mapping = row['CATEGORY_MAP']
            return row['DATA_SOURCE_URL'], (json.loads(mapping) if isinstance(mapping, str) else mapping)
    except Exception as e:
        print(f"❌ Config Fetch Error: {e}")
    return None, None

def on_message(ws, message):
    data = json.loads(message)
    if 'data' in data:
        trade = data['data']
        symbol, price, qty = trade['s'], float(trade['p']), float(trade['q'])
        region = CATEGORY_MAP.get(symbol, "Other")
        
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                query = "INSERT INTO REALTIME_PURCHASES (PRODUCT_ID, PRICE, QUANTITY, REVENUE, EVENT_TIME, REGION) VALUES (%s, %s, %s, %s, %s, %s)"
                cursor.execute(query, (symbol, price, qty, price * qty, datetime.now(), region))
                cursor.close()
                conn.close()
                print(f"✅ Stored {symbol} | ${price}")
            except Error as e:
                print(f"❌ Insert Error: {e}")

def on_error(ws, error):
    print(f"🔌 Socket Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("🔌 Connection Closed. Restarting in 5s...")

def start():
    global CATEGORY_MAP
    url, CATEGORY_MAP = fetch_config()
    
    if not url:
        print("⚠️ No URL found. Checking again in 10s...")
        time.sleep(10)
        return

    # The Infinite Reconnect Loop
    while True:
        print(f"🚀 Connecting to Binance: {url}")
        ws = websocket.WebSocketApp(
            url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        ws.run_forever()
        
        # If run_forever returns, it means the connection dropped
        time.sleep(5) 

if __name__ == "__main__":
    
    start()
