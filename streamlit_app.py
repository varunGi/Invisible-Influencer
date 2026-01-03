import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- PAGE CONFIG ---
st.set_page_config(page_title="🦁 Motivation Empire Admin", layout="wide")

# --- DATABASE CONNECTION (Google Sheets) ---
def get_db_connection():
    # We will put the JSON key inside Streamlit Secrets later
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    # Open the Sheet
    sheet = client.open("Motivation_DB")
    return sheet

# --- UI LAYOUT ---
st.title("🦁 The Motivation Empire")
st.markdown("### *Zero Cost Automation Hub*")

# TABS
tab1, tab2, tab3 = st.tabs(["📢 Social Accounts", "🎬 Video Generator", "📜 History"])

# --- TAB 1: MANAGE ACCOUNTS ---
with tab1:
    st.header("Manage Your Social Media Accounts")
    
    try:
        sheet = get_db_connection()
        worksheet = sheet.worksheet("Accounts")
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)

        # Show current accounts
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No accounts added yet.")

        # Add New Account Form
        with st.form("add_account_form"):
            st.write("Add New Asset")
            col1, col2 = st.columns(2)
            platform = col1.selectbox("Platform", ["Instagram", "YouTube Shorts", "TikTok", "Reddit", "Telegram"])
            username = col2.text_input("Username / Channel Name")
            niche = st.selectbox("Niche", ["Motivation (Luxury)", "Stoicism", "Gym/Fitness", "Crypto"])
            
            submitted = st.form_submit_button("Add Account")
            if submitted:
                new_row = [platform, username, "Active", niche]
                worksheet.append_row(new_row)
                st.success(f"Added {username} on {platform}!")
                st.rerun()

    except Exception as e:
        st.error(f"Database Error: {e}")
        st.warning("Did you set up your Streamlit Secrets yet?")

# --- TAB 2: GENERATOR (Placeholder for Phase 3) ---
with tab2:
    st.header("Generate Content")
    st.write("This engine will create Luxury Motivation Videos.")
    st.info("Pexels Video API + EdgeTTS + FFmpeg integration coming in next step.")

# --- TAB 3: HISTORY ---
with tab3:
    st.header("Posting History")
    try:
        worksheet_hist = sheet.worksheet("History")
        hist_data = worksheet_hist.get_all_records()
        st.dataframe(pd.DataFrame(hist_data), use_container_width=True)
    except:
        st.write("No history found.")