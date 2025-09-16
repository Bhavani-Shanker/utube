import streamlit as st
from pytubefix import YouTube
import os
import re
import urllib.error

# Optional: Uncomment to use yt-dlp as fallback
# from yt_dlp import YoutubeDL

# Function to validate YouTube URL
def is_valid_youtube_url(url):
    youtube_regex = (
        r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})')
    return bool(re.match(youtube_regex, url))

# Function to sanitize filenames
def sanitize_filename(filename):
    return re.sub(r'[^\w\s.-]', '', filename)

# Function to download with pytube
def download_with_pytube(url, download_type, resolution=None):
    try:
        yt = YouTube(url)
        if download_type == "Video":
            stream = yt.streams.filter(progressive=True, file_extension='mp4', resolution=resolution).first()
            if not stream:
                return None, f"Selected resolution ({resolution}) not available"
            filename = sanitize_filename(f"{yt.title}.mp4")
        else:  # Audio
            stream = yt.streams.filter(only_audio=True, file_extension='mp4').first()
            if not stream:
                return None, "Audio stream not available"
            filename = sanitize_filename(f"{yt.title}.mp3")
        
        file_path = stream.download(output_path="downloads", filename=filename)
        return file_path, None
    except urllib.error.HTTPError as e:
        return None, f"HTTP Error {e.code}: {e.reason} - Video may be restricted or unavailable"
    except Exception as e:
        return None, f"Error: {str(e)}"




# Main download function
def download_youtube_content(url, download_type, resolution=None):
    # Try pytube first
    file_path, error = download_with_pytube(url, download_type, resolution)
    if file_path:
        return file_path, None
    
    # Optional: Uncomment to enable yt-dlp fallback
    """
    st.warning("pytube failed, trying yt-dlp...")
    file_path, error = download_with_ytdlp(url, download_type, resolution)
    if file_path:
        return file_path, None
    """
    
    return None, error

# Streamlit UI
st.title("YouTube Video/Audio Downloader")

# Input URL
url = st.text_input("Enter YouTube URL:")

# Download type selection
download_type = st.radio("Select download type:", ("Video", "Audio"))

# Resolution selection for video
resolution = None
if download_type == "Video":
    resolution = st.selectbox("Select video resolution:", ["720p", "480p", "360p", "240p", "144p"])

# Create downloads directory
if not os.path.exists("downloads"):
    os.makedirs("downloads")

# Download button
if st.button("Download"):
    if not url:
        st.error("Please enter a YouTube URL")
    elif not is_valid_youtube_url(url):
        st.error("Invalid YouTube URL. Please enter a valid URL (e.g., https://www.youtube.com/watch?v=...)")
    else:
        with st.spinner("Downloading..."):
            file_path, error = download_youtube_content(url, download_type, resolution)
            
            if error:
                st.error(f"Error: {error}")
                if "HTTP Error 400" in error:
                    st.error("This error often occurs due to restricted videos or YouTube API changes. Try a different video or check the URL.")
            else:
                st.success("Download completed!")
                with open(file_path, "rb") as file:
                    file_extension = "mp3" if download_type == "Audio" else "mp4"
                    st.download_button(
                        label="Download File",
                        data=file,
                        file_name=os.path.basename(file_path),
                        mime=f"audio/{file_extension}" if download_type == "Audio" else f"video/{file_extension}"
                    )

