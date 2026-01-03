import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import asyncio
import edge_tts
import os
import subprocess
import random

# --- PAGE CONFIG ---
st.set_page_config(page_title="🦁 Motivation Empire Admin", layout="wide")

# --- DATABASE CONNECTION (Google Sheets) ---
def get_db_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("Motivation_DB")

# --- HELPER: GET PEXELS VIDEO ---
def get_pexels_video(query):
    headers = {"Authorization": st.secrets["pexels_api_key"]}
    # Search for vertical videos (Portrait)
    url = f"https://api.pexels.com/videos/search?query={query}&orientation=portrait&per_page=5"
    try:
        r = requests.get(url, headers=headers)
        data = r.json()
        if data['videos']:
            # Pick a random video from the top 5 results to keep it fresh
            video = random.choice(data['videos'])
            # Get the best quality link
            video_files = video['video_files']
            # Sort by quality (we want HD but not 4k to save RAM)
            best_video = next((v for v in video_files if v['width'] == 1080), video_files[0])
            return best_video['link']
        return None
    except Exception as e:
        st.error(f"Pexels Error: {e}")
        return None

# --- HELPER: GENERATE AUDIO (EdgeTTS) ---
async def generate_audio(text, voice, output_file="audio_temp.mp3"):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)

# --- HELPER: ASSEMBLE VIDEO (FFmpeg) ---
def assemble_video(video_url, audio_path, output_path="final_output.mp4"):
    # 1. Download the Pexels Video
    st.info("Downloading Stock Footage...")
    v_data = requests.get(video_url).content
    with open("video_temp.mp4", "wb") as f:
        f.write(v_data)

    # 2. Run FFmpeg Command
    st.info("Rendering Video... (This takes 20s)")

    # 👇 UPDATED PATH 👇
    ffmpeg_path = r"C:\Users\varun\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"

    command = [
        ffmpeg_path,
        "-y",
        "-stream_loop", "-1",
        "-i", "video_temp.mp4",
        "-i", audio_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        output_path
    ]
    
    subprocess.run(command, check=True)
    return output_path

# --- UI LAYOUT ---
st.title("🦁 The Motivation Empire")
tab1, tab2, tab3 = st.tabs(["📢 Social Accounts", "🎬 Video Generator", "📜 History"])

# --- TAB 1: ACCOUNTS ---
with tab1:
    st.header("Manage Your Social Media Accounts")
    try:
        sheet = get_db_connection()
        worksheet = sheet.worksheet("Accounts")
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)
    except:
        st.warning("Connect Google Sheets in Secrets first.")

# --- TAB 2: GENERATOR ---
with tab2:
    st.header("Create Viral Short")
    
    col1, col2 = st.columns(2)
    
    with col1:
        topic_input = st.text_input("Topic / Quote", "Discipline is doing what you hate to do like you love it.")
        niche_select = st.selectbox("Visual Vibe", ["Luxury Cars", "Gym Workout", "Nature Storm", "City Night", "Money"])
        voice_select = st.selectbox("Voice", ["en-US-ChristopherNeural", "en-GB-RyanNeural", "en-US-GuyNeural"])
    
    with col2:
        st.info("💡 Pro Tip: Keep quotes under 30 seconds.")
        generate_btn = st.button("🚀 Generate Video")

    if generate_btn:
        try:
            # 1. Get Visuals
            video_link = get_pexels_video(niche_select)
            if not video_link:
                st.error("No video found on Pexels.")
                st.stop()
            
            # 2. Make Audio
            audio_path = "audio_temp.mp3"
            asyncio.run(generate_audio(topic_input, voice_select, audio_path))
            
            # 3. Assemble
            final_video = assemble_video(video_link, audio_path)
            
            # 4. Show Result
            st.success("Video Ready!")
            st.video(final_video)
            
            with open(final_video, "rb") as file:
                st.download_button("Download MP4", file, file_name="motivation_short.mp4")
                
        except Exception as e:
            st.error(f"Error: {e}")

# --- TAB 3: HISTORY ---
with tab3:
    st.write("History log coming soon...")