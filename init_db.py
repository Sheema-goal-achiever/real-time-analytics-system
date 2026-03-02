import mysql.connector

# 1. PASTE YOUR AIVEN DETAILS HERE
db_config = {
    "host": "mysql-f0d7079-realtime-data-analytics.j.aivencloud.com",
    "port": "16060",
    "user": "avnadmin",
    "password": "AVNS_cKq5YoRFgPSrC4t9CGn",
    "database": "defaultdb"
}

def create_tables():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # Create Tables
        tables = [
            """
            CREATE TABLE IF NOT EXISTS CLIENT_CONFIG (
                COMPANY_NAME VARCHAR(255) PRIMARY KEY,
                PASSWORD VARCHAR(255),
                DATA_SOURCE_URL TEXT,
                CATEGORY_MAP JSON
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS REALTIME_PURCHASES (
                ID INT AUTO_INCREMENT PRIMARY KEY,
                PRODUCT_ID VARCHAR(50),
                PRICE DECIMAL(20, 8),
                QUANTITY DECIMAL(20, 8),
                REVENUE DECIMAL(20, 8),
                EVENT_TIME DATETIME,
                REGION VARCHAR(100)
            )
            """
        ]
        
        for table_sql in tables:
            cursor.execute(table_sql)
            
        print("✅ Tables created successfully in Aiven!")
        conn.commit()
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    create_tables()