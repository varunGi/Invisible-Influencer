import streamlit as st
import requests
import asyncio
import edge_tts
import subprocess
import random
import google.generativeai as genai
import os
import glob
import shutil
import PIL.Image
import math
from concurrent.futures import ThreadPoolExecutor

# --- CONFIGURATION ---
st.set_page_config(page_title="🦁 Motivation Empire Admin", layout="wide")
TARGET_W = 1080
TARGET_H = 1920

# Suppress warnings
import logging
logging.getLogger("google.generativeai").setLevel(logging.ERROR)

if "gemini_api_key" in st.secrets:
    genai.configure(api_key=st.secrets["gemini_api_key"])

# --- 🛠️ FIX FOR "ANTIALIAS" ERROR ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip

# --- 1. LOGGING ---
def log_status(message):
    print(f"--> {message}")

# --- 2. FONT SETUP ---
def setup_font():
    local_font = "arial.ttf"
    possible_paths = [
        "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ]
    if not os.path.exists(local_font):
        for path in possible_paths:
            if os.path.exists(path):
                shutil.copy(path, local_font)
                break
    return local_font

# --- 3. AI WRITER ---
def generate_quote(topic):
    log_status(f"Generating quote for topic: {topic}")
    try:
        model = genai.GenerativeModel('models/gemini-2.5-flash')
        prompt = (
            f"Write a short motivational speech about {topic} for a viral reel. "
            "It must be exactly 50 to 70 words long. "
            "IMPORTANT: Use simple, everyday English. "
            "Tone: Direct, raw, honest. Short, punchy sentences. "
            "Do not use hashtags."
        )
        response = model.generate_content(prompt)
        text = response.text.strip()
        log_status(f"Quote Generated ({len(text.split())} words)")
        return text
    except Exception as e:
        return f"Error: {e}"

# --- 4. ROBUST AUDIO & SUBTITLES (WITH FALLBACK) ---
def format_vtt_time(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{int(h):02}:{int(m):02}:{s:06.3f}"

async def generate_audio_and_subs(text, voice, audio_path="audio_temp.mp3", subs_path="subs.vtt"):
    log_status(f"Starting TTS for voice: {voice}")
    communicate = edge_tts.Communicate(text, voice)
    word_events = []
    
    # 1. Generate Audio & Try to get timings
    with open(audio_path, "wb") as file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                word_events.append({
                    "offset": chunk["offset"] / 10000000,
                    "duration": chunk["duration"] / 10000000,
                    "text": chunk["text"]
                })

    # 2. IF TIMING FAILED -> USE FALLBACK MATH
    if not word_events:
        log_status("⚠️ API Timings missing. Switching to Mathematical Fallback.")
        
        # Get actual audio duration
        try:
            audio_clip = AudioFileClip(audio_path)
            total_duration = audio_clip.duration
            audio_clip.close()
        except:
            total_duration = 30 # Safe default
            
        words = text.split()
        if not words: return False
        
        # Calculate time per word
        time_per_word = total_duration / len(words)
        
        current_time = 0.0
        for word in words:
            word_events.append({
                "offset": current_time,
                "duration": time_per_word,
                "text": word
            })
            current_time += time_per_word
            
    # 3. Generate VTT (Grouped by 3 words for dynamic feel)
    with open(subs_path, "w", encoding="utf-8") as vtt:
        vtt.write("WEBVTT\n\n")
        buffer_words = []
        start_time = 0
        
        for i, event in enumerate(word_events):
            if not buffer_words:
                start_time = event["offset"]
            
            buffer_words.append(event["text"])
            
            # Logic: Break every 3 words OR punctuation
            txt = event["text"]
            is_punctuation = txt.endswith(('.', '?', '!', ','))
            is_max_len = len(buffer_words) >= 3 
            is_last = (i == len(word_events) - 1)
            
            if is_punctuation or is_max_len or is_last:
                end_time = event["offset"] + event["duration"]
                # Slight buffer ensures text stays on screen long enough to read
                if not is_last: end_time += 0.1 
                
                vtt.write(f"{format_vtt_time(start_time)} --> {format_vtt_time(end_time)}\n")
                vtt.write(f"{' '.join(buffer_words)}\n\n")
                buffer_words = []
    
    log_status(f"Subtitle file saved (Fallback Used: {not word_events})")
    return True

# --- 5. DOWNLOADER ---
def download_video(args):
    url, index = args
    clip_name = f"clip_{index}.mp4"
    try:
        v_data = requests.get(url).content
        with open(clip_name, "wb") as f:
            f.write(v_data)
        return clip_name
    except Exception:
        return None

def get_mixed_pexels_videos(vibe_list, count=4):
    headers = {"Authorization": st.secrets["pexels_api_key"]}
    video_urls = []
    log_status("Searching Pexels...")
    
    for i in range(count):
        current_vibe = vibe_list[i % len(vibe_list)]
        page_num = random.randint(1, 10) 
        url = f"https://api.pexels.com/videos/search?query={current_vibe}&orientation=portrait&per_page=1&page={page_num}"
        try:
            r = requests.get(url, headers=headers)
            data = r.json()
            if data.get('videos'):
                video = data['videos'][0]
                video_files = video['video_files']
                best = min(video_files, key=lambda x: abs(x['width'] - TARGET_W))
                video_urls.append(best['link'])
                print(f"   [Pexels] Found clip for '{current_vibe}'")
        except Exception as e:
            print(f"   [Pexels Error]: {e}")
            
    return video_urls

# --- 6. ASSEMBLER ---
def assemble_video(video_files, audio_path, subs_path, burn_captions, output_path="final_output.mp4"):
    log_status("Starting Video Assembly...")
    
    try:
        audio = AudioFileClip(audio_path)
        target_duration = max(15, min(audio.duration, 58)) # Reels limit < 60s
    except:
        return None

    video_clips = []
    avg_clip_duration = (target_duration / len(video_files)) + 1
    
    for v_file in video_files:
        try:
            clip = VideoFileClip(v_file)
            if clip.h != TARGET_H: clip = clip.resize(height=TARGET_H)
            if clip.w != TARGET_W: clip = clip.crop(x1=clip.w/2 - (TARGET_W/2), width=TARGET_W, height=TARGET_H)
            
            if clip.duration < avg_clip_duration: clip = clip.loop(duration=avg_clip_duration)
            else: clip = clip.subclip(0, avg_clip_duration)
            
            clip = clip.crossfadein(0.5)
            video_clips.append(clip)
        except Exception as e:
            print(f"Clip Error: {e}")

    final_video = concatenate_videoclips(video_clips, method="compose", padding=-0.5)
    final_video = final_video.subclip(0, target_duration)
    final_video = final_video.set_audio(audio)

    # Render Temp
    temp_file = "temp_no_text.mp4"
    log_status("Rendering Base Video...")
    final_video.write_videofile(temp_file, fps=24, codec='libx264', audio_codec='aac', preset='ultrafast', threads=4, logger=None)
    
    for c in video_clips: c.close()
    final_video.close()
    audio.close()

    if not burn_captions:
        if os.path.exists(output_path): os.remove(output_path)
        os.rename(temp_file, output_path)
        return output_path

    # Burn Text
    log_status("Burning Subtitles with FFmpeg...")
    font_file = setup_font()
    ffmpeg_path = r"C:\Users\varun\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
    
    abs_subs = os.path.abspath(subs_path).replace("\\", "/").replace(":", "\\:")
    style = f"Fontname={font_file},FontSize=40,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,Outline=3,Shadow=2,Alignment=2,MarginV=90"
    vf_chain = f"eq=brightness=-0.3,subtitles='{abs_subs}':force_style='{style}'"

    command = [
        ffmpeg_path, "-y", "-i", temp_file, "-vf", vf_chain,
        "-c:v", "libx264", "-crf", "28", "-preset", "ultrafast", "-c:a", "copy", output_path
    ]

    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        log_status(f"❌ FFmpeg Failed: {e.stderr.decode()}")
        if os.path.exists(output_path): os.remove(output_path)
        os.rename(temp_file, output_path)
    
    if os.path.exists(temp_file): os.remove(temp_file)
    return output_path

# --- UI LAYOUT ---
with st.container():
    st.title("🦁 Motivation Empire Admin")
    
    col1, col2 = st.columns(2)
    with col1:
        topic = st.text_input("Topic", "Discipline")
        
        # VIBES
        st.write("### 🎨 Select Vibes")
        default_vibes = ["Luxury Cars", "Gym", "Money", "Nature", "City", "Lion", "Samurai", "Vikings"]
        selected_vibes = st.multiselect("Presets", default_vibes, default=["Luxury Cars"])
        custom_vibe_raw = st.text_input("Custom Vibes (comma separated)")
        
        final_vibe_list = selected_vibes.copy()
        if custom_vibe_raw:
            final_vibe_list.extend([v.strip() for v in custom_vibe_raw.split(',') if v.strip()])
        if not final_vibe_list: final_vibe_list = ["Motivation"]

        # VOICE
        voice = st.selectbox("Voice", ["en-US-AriaNeural", "en-US-ChristopherNeural", "en-GB-RyanNeural"])
        burn_captions = st.checkbox("🔥 Burn Text?", value=True)
    
    with col2:
        st.write("### ⚙️ Actions")
        if st.button("🎲 1. Generate Quote"):
            st.session_state['quote'] = generate_quote(topic)

    if 'quote' in st.session_state:
        st.write("### 📝 Script")
        final_text = st.text_area("Script:", st.session_state['quote'], height=150)
        
        if st.button("🚀 2. Create Viral Reel"):
            status_container = st.empty()
            clip_gallery = st.empty()
            
            # 1. DOWNLOAD
            status_container.info("⬇️ Downloading Clips...")
            video_urls = get_mixed_pexels_videos(final_vibe_list, count=4)
            if not video_urls: st.stop()
            
            downloaded_clips = []
            with ThreadPoolExecutor(max_workers=4) as executor:
                args = [(url, i) for i, url in enumerate(video_urls)]
                results = executor.map(download_video, args)
                for res in results:
                    if res: downloaded_clips.append(res)
            
            # VISUAL LOADER
            with clip_gallery.container():
                st.write("### 🎬 Footage Preview")
                cols = st.columns(4)
                for i, clip in enumerate(downloaded_clips):
                    with cols[i]:
                        st.video(clip)
            
            # 2. AUDIO & SUBS
            status_container.info("🎙️ Generating Audio...")
            audio_file = "audio_temp.mp3"
            subs_file = "subs.vtt"
            
            success = asyncio.run(generate_audio_and_subs(final_text, voice, audio_file, subs_file))
            
            # 3. ASSEMBLE
            status_container.info("🔥 Rendering Final Video...")
            out = assemble_video(downloaded_clips, audio_file, subs_file, burn_captions)
            
            # CLEANUP UI
            clip_gallery.empty()
            status_container.empty()
            
            if out:
                st.success("✅ Reel Created Successfully!")
                c1, c2, c3 = st.columns([1, 1, 1])
                with c2:
                    st.caption("Final Output")
                    st.video(out)
                
                if st.button("🧹 Clean Up Temp Files"):
                    for f in glob.glob("clip_*.mp4") + ["audio_temp.mp3", "subs.vtt", "temp_no_text.mp4"]:
                        try: os.remove(f)
                        except: pass
                    st.info("Cleaned.")