import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text
import os
import json
import time
import subprocess

# --- 1. INITIAL SETUP & DATABASE REPAIR ---
st.set_page_config(page_title="Crypto Live Terminal 2026", layout="wide")

def get_conn():
    # This uses the 'sql' connection defined in your Secrets
    return st.connection("sql")

def initialize_database():
    conn = get_conn()
    try:
        with conn.session as s:
            # Fix: Create tables if they don't exist in Aiven
            s.execute(text("""
                CREATE TABLE IF NOT EXISTS CLIENT_CONFIG (
                    ID INT AUTO_INCREMENT PRIMARY KEY,
                    COMPANY_NAME VARCHAR(255) NOT NULL UNIQUE,
                    PASSWORD VARCHAR(255) NOT NULL,
                    DATA_SOURCE_URL TEXT,
                    CATEGORY_MAP JSON
                );
            """))
            s.execute(text("""
                CREATE TABLE IF NOT EXISTS REALTIME_PURCHASES (
                    ID INT AUTO_INCREMENT PRIMARY KEY,
                    EVENT_TIME TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRODUCT_ID VARCHAR(50),
                    REVENUE DECIMAL(18, 2),
                    REGION VARCHAR(100)
                );
            """))
            s.commit()
    except Exception as e:
        st.error(f"Database Setup Error: {e}")

initialize_database()

# --- 2. SESSION STATE ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_company' not in st.session_state:
    st.session_state.user_company = None

# --- 3. AUTHENTICATION LOGIC ---
def login_user(name, pwd):
    conn = get_conn()
    query = text("SELECT * FROM CLIENT_CONFIG WHERE COMPANY_NAME = :n AND PASSWORD = :p")
    result = conn.query(query, params={"n": name, "p": pwd}, ttl=0)
    if not result.empty:
        st.session_state.logged_in = True
        st.session_state.user_company = name
        return True
    return False

def register_user(name, pwd, url):
    conn = get_conn()
    try:
        with conn.session as s:
            s.execute(text("""
                INSERT INTO CLIENT_CONFIG (COMPANY_NAME, PASSWORD, DATA_SOURCE_URL, CATEGORY_MAP) 
                VALUES (:n, :p, :u, :m)
            """), {"n": name, "p": pwd, "u": url, "m": json.dumps({})})
            s.commit()
        return True
    except Exception as e:
        st.error(f"Registration Failed: {e}")
        return False

# --- 4. THE UI ---
if not st.session_state.logged_in:
    tab1, tab2 = st.tabs(["Login", "Register New Company"])
    
    with tab1:
        with st.form("login_form"):
            u = st.text_input("Company Name")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                if login_user(u, p):
                    st.rerun()
                else:
                    st.error("Invalid Credentials")

    with tab2:
        with st.form("reg_form"):
            new_u = st.text_input("New Company Name")
            new_p = st.text_input("Set Password", type="password")
            new_url = st.text_input("Binance WS Link", value="wss://stream.binance.com:9443/stream?streams=btcusdt@trade/ethusdt@trade/solusdt@trade")
            if st.form_submit_button("Create Account"):
                if register_user(new_u, new_p, new_url):
                    st.success("Account Created! Use the Login tab.")

else:
    # --- 5. THE DASHBOARD (LOGGED IN) ---
    st.sidebar.title(f"Welcome, {st.session_state.user_company}")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    st.title("🚀 Real-Time Crypto Analytics")
    
    # Start the Binance Worker in the background if not running
    if 'worker_started' not in st.session_state:
        subprocess.Popen(["python", "test_ws.py"])
        st.session_state.worker_started = True
        st.info("Live data worker started...")

    # Layout for charts
    col1, col2 = st.columns(2)

    # Fetch Data from Aiven for Charts
    conn = get_conn()
    df = conn.query("SELECT * FROM REALTIME_PURCHASES ORDER BY EVENT_TIME DESC LIMIT 100", ttl=0)

    if not df.empty:
        with col1:
            st.subheader("Live Price/Revenue Stream")
            fig = px.line(df, x="EVENT_TIME", y="REVENUE", color="PRODUCT_ID", title="Incoming Market Data")
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("Market Share by Region")
            fig2 = px.pie(df, values="REVENUE", names="REGION", title="Global Trade Distribution")
            st.plotly_chart(fig2, use_container_width=True)
            
        st.subheader("Recent Activity Log")
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("Waiting for data from Binance... (ensure test_ws.py is correctly configured with Aiven credentials)")

    # Auto-refresh every 5 seconds
    time.sleep(5)
    st.rerun()
