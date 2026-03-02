import websocket
import json
import mysql.connector
import os
import time
from datetime import datetime
from dotenv import load_dotenv

# --- 1. LOAD CONFIGURATION ---
# This loads variables from your .env file locally.
# On Streamlit Cloud, it will automatically pull from the "Secrets" you defined.
load_dotenv()

AIVEN_HOST = os.getenv("AIVEN_HOST")
AIVEN_PORT = os.getenv("AIVEN_PORT")
AIVEN_USER = os.getenv("AIVEN_USER")
AIVEN_PASSWORD = os.getenv("AIVEN_PASSWORD")
AIVEN_DATABASE = os.getenv("AIVEN_DATABASE")

# --- 2. DATABASE LOGIC ---
def get_db_connection():
    """Connects to the Aiven MySQL Cloud Database."""
    try:
        return mysql.connector.connect(
            host=AIVEN_HOST,
            port=int(AIVEN_PORT) if AIVEN_PORT else 3306,
            user=AIVEN_USER,
            password=AIVEN_PASSWORD,
            database=AIVEN_DATABASE,
            autocommit=True
        )
    except Exception as e:
        print(f"❌ Database Connection Error: {e}")
        return None

def fetch_client_config():
    """Retrieves the Binance URL and Category Mapping from the DB."""
    conn = get_db_connection()
    if not conn:
        return None, None
    
    try:
        cursor = conn.cursor(dictionary=True)
        # We fetch the most recent config. Adjust the query if you want a specific company.
        cursor.execute("SELECT DATA_SOURCE_URL, CATEGORY_MAP FROM CLIENT_CONFIG ORDER BY COMPANY_NAME DESC LIMIT 1")
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if row:
            # Handle JSON mapping (converts string to dict if necessary)
            mapping = row['CATEGORY_MAP']
            if isinstance(mapping, str):
                mapping = json.loads(mapping)
            return row['DATA_SOURCE_URL'], mapping
    except Exception as e:
        print(f"❌ Error fetching config: {e}")
    return None, None

# --- 3. WEBSOCKET LOGIC ---
def on_message(ws, message):
    data = json.loads(message)
    if 'data' in data:
        trade = data['data']
        symbol = trade['s'] # e.g., BTCUSDT
        price = float(trade['p'])
        quantity = float(trade['q'])
        event_time = datetime.fromtimestamp(trade['E'] / 1000.0)
        
        # Determine the Category (Region) from our mapping
        region = CATEGORY_MAP.get(symbol, "Other")
        revenue = price * quantity

        # Insert into Aiven
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                query = """
                    INSERT INTO REALTIME_PURCHASES 
                    (PRODUCT_ID, PRICE, QUANTITY, REVENUE, EVENT_TIME, REGION)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (symbol, price, quantity, revenue, event_time, region))
                conn.commit()
                cursor.close()
                conn.close()
                print(f"✅ Stored: {symbol} | ${price:.2f} | Region: {region}")
            except Exception as e:
                print(f"❌ Insert Fail: {e}")

def on_error(ws, error):
    print(f"🔌 Connection Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("🔌 WebSocket Closed. Retrying in 5 seconds...")
    time.sleep(5)
    start_websocket()

# --- 4. EXECUTION ---
def start_websocket():
    global CATEGORY_MAP
    binance_url, CATEGORY_MAP = fetch_client_config()
    
    if not binance_url:
        print("⚠️ No configuration found in CLIENT_CONFIG table. Please register via Dashboard.")
        return

    print(f"🚀 Connecting to Binance: {binance_url}")
    ws = websocket.WebSocketApp(
        binance_url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever()

if __name__ == "__main__":
    start_websocket()