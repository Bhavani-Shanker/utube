import streamlit as st
from pytubefix import YouTube
import os
import re
import urllib.error

# moviepy is used to turn the downloaded audio stream (m4a/aac) into a real .mp3
from moviepy.editor import AudioFileClip


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def is_valid_youtube_url(url: str) -> bool:
    """Accepts standard youtube.com, youtu.be, music.youtube.com and
    youtube-nocookie.com links, with or without scheme/www."""
    youtube_regex = (
        r'^(https?://)?(www\.|music\.)?(youtube|youtu|youtube-nocookie)\.'
        r'(com|be)/'
        r'(watch\?v=|embed/|v/|shorts/|.+[?&]v=)?'
        r'([A-Za-z0-9_-]{11})'
    )
    return bool(re.match(youtube_regex, url.strip()))


def sanitize_filename(filename: str) -> str:
    """Strip characters that are unsafe for filenames, but keep it non-empty."""
    cleaned = re.sub(r'[^\w\s.-]', '', filename).strip()
    return cleaned if cleaned else "youtube_download"


# ---------------------------------------------------------------------------
# Download logic
# ---------------------------------------------------------------------------

def _best_progressive_stream(yt, resolution):
    """
    Progressive (audio+video combined) MP4 is only available at limited
    resolutions (often capped at 720p, sometimes only up to 360p depending
    on the video). If the exact resolution the user asked for isn't
    available as a progressive stream, fall back to the closest one that
    is, instead of failing outright.
    """
    streams = yt.streams.filter(progressive=True, file_extension='mp4')
    exact = streams.filter(resolution=resolution).first()
    if exact:
        return exact, None

    # Fall back to the highest progressive resolution actually available.
    fallback = streams.order_by('resolution').desc().first()
    if fallback:
        note = (
            f"{resolution} isn't available as a combined audio+video stream "
            f"for this video. Downloaded the closest available quality "
            f"({fallback.resolution}) instead."
        )
        return fallback, note

    return None, None


def download_with_pytube(url, download_type, resolution=None):
    try:
        # use_po_token helps avoid the 403/400 errors YouTube now throws
        # for many requests that don't pass its bot-detection challenge.
        yt = YouTube(url, use_po_token=True)

        if download_type == "Video":
            stream, note = _best_progressive_stream(yt, resolution)
            if not stream:
                return None, None, "No downloadable MP4 video stream was found for this video."
            filename = sanitize_filename(f"{yt.title}.mp4")
            file_path = stream.download(output_path="downloads", filename=filename)
            return file_path, note, None

        else:  # Audio
            stream = (
                yt.streams.filter(only_audio=True)
                .order_by('abr')
                .desc()
                .first()
            )
            if not stream:
                return None, None, "Audio stream not available"

            # Pytube/pytubefix audio streams are AAC/Opus in an m4a/webm
            # container, NOT actual MP3 data. Download the raw stream
            # first, then transcode it to a genuine .mp3 with moviepy.
            base_name = sanitize_filename(yt.title)
            raw_path = stream.download(
                output_path="downloads",
                filename=f"{base_name}_raw.{stream.subtype}",
            )

            mp3_path = os.path.join("downloads", f"{base_name}.mp3")
            try:
                clip = AudioFileClip(raw_path)
                clip.write_audiofile(mp3_path, logger=None)
                clip.close()
            finally:
                if os.path.exists(raw_path):
                    os.remove(raw_path)

            return mp3_path, None, None

    except urllib.error.HTTPError as e:
        return None, None, f"HTTP Error {e.code}: {e.reason} - Video may be restricted or unavailable"
    except Exception as e:
        return None, None, f"Error: {str(e)}"


def download_youtube_content(url, download_type, resolution=None):
    return download_with_pytube(url, download_type, resolution)


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

st.title("YouTube Video/Audio Downloader")

url = st.text_input("Enter YouTube URL:")

download_type = st.radio("Select download type:", ("Video", "Audio"))

resolution = None
if download_type == "Video":
    resolution = st.selectbox("Select video resolution:", ["720p", "480p", "360p", "240p", "144p"])

if not os.path.exists("downloads"):
    os.makedirs("downloads")

if st.button("Download"):
    if not url:
        st.error("Please enter a YouTube URL")
    elif not is_valid_youtube_url(url):
        st.error("Invalid YouTube URL. Please enter a valid URL (e.g., https://www.youtube.com/watch?v=...)")
    else:
        with st.spinner("Downloading..."):
            file_path, note, error = download_youtube_content(url, download_type, resolution)

            if error:
                st.error(f"Error: {error}")
                if "HTTP Error 400" in error or "HTTP Error 403" in error:
                    st.info(
                        "This often happens because YouTube is rejecting the request "
                        "(bot-detection or a region/age restriction). Try a different "
                        "video, or try again in a moment."
                    )
            else:
                if note:
                    st.warning(note)
                st.success("Download completed!")
                with open(file_path, "rb") as file:
                    file_extension = "mp3" if download_type == "Audio" else "mp4"
                    st.download_button(
                        label="Download File",
                        data=file,
                        file_name=os.path.basename(file_path),
                        mime=f"audio/{file_extension}" if download_type == "Audio" else f"video/{file_extension}"
                    )
