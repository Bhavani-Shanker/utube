import streamlit as st
from pytubefix import YouTube
import os
import re
import tempfile
import urllib.error

# moviepy is used to turn the downloaded audio stream (m4a/aac) into a real .mp3
from moviepy.editor import AudioFileClip

# Server-side scratch space for pytubefix's intermediate download (it has no
# in-memory download API, so it always needs to write to disk first). This
# is anchored to the system temp dir rather than a relative "downloads"
# path, so it always resolves to the same real location regardless of
# which folder you happened to run `streamlit run` from. Every file written
# here is deleted again within the same request, right after its bytes are
# read into memory for the actual browser download below.
SCRATCH_DIR = os.path.join(tempfile.gettempdir(), "yt_downloader_scratch")


def human_size(num_bytes: int) -> str:
    """e.g. 8423812 -> '8.0 MB'"""
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


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
            file_path = stream.download(output_path=SCRATCH_DIR, filename=filename)
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
                output_path=SCRATCH_DIR,
                filename=f"{base_name}_raw.{stream.subtype}",
            )

            mp3_path = os.path.join(SCRATCH_DIR, f"{base_name}.mp3")
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
st.caption(
    "Paste a YouTube link below, click **Fetch**, then use the download link "
    "that appears to save the file to your own device."
)

with st.expander("ℹ️ Where will the file be saved?"):
    st.markdown(
        "This app runs on a server, not on your computer, so it can't open a "
        "\"Save As\" folder picker on your device directly — no website can, "
        "for browser security reasons.\n\n"
        "Instead, the file is handed to **your browser**, which saves it the "
        "same way it saves anything else you download:\n"
        "- By default, most browsers save straight to your **Downloads** folder.\n"
        "- To choose the folder yourself **every time**, turn on "
        "*\"Ask where to save each file before downloading\"* in your "
        "browser's settings (Chrome: Settings → Downloads. Firefox: "
        "Settings → General → Files and Applications. Edge: Settings → "
        "Downloads). Once that's on, this link will pop up a save dialog "
        "like any other download.\n\n"
        "**Note:** while fetching, the app briefly writes a working copy to "
        "a temp folder on the server (so it has something to read into "
        "memory) and deletes it right away. That temp copy is not your "
        "download — the only real download is the button below, which goes "
        "through your browser."
    )

url = st.text_input(
    "Paste the YouTube link here:",
    placeholder="https://www.youtube.com/watch?v=...",
)

download_type = st.radio("Select download type:", ("Video", "Audio"))

resolution = None
if download_type == "Video":
    resolution = st.selectbox("Select video resolution:", ["720p", "480p", "360p", "240p", "144p"])

if not os.path.exists(SCRATCH_DIR):
    os.makedirs(SCRATCH_DIR)

# If the inputs changed since the last successful fetch, clear the stale
# result so we never show a download link for the wrong video.
if "ready_file" in st.session_state:
    last = st.session_state.get("ready_file_inputs", {})
    if last != {"url": url, "type": download_type, "resolution": resolution}:
        st.session_state.pop("ready_file", None)
        st.session_state.pop("ready_file_inputs", None)

if st.button("Fetch", type="primary"):
    if not url:
        st.error("Please enter a YouTube URL")
    elif not is_valid_youtube_url(url):
        st.error("Invalid YouTube URL. Please enter a valid URL (e.g., https://www.youtube.com/watch?v=...)")
    else:
        st.session_state.pop("ready_file", None)
        st.session_state.pop("ready_file_inputs", None)
        with st.spinner("Fetching from YouTube... this can take a moment"):
            file_path, note, error = download_youtube_content(url, download_type, resolution)

            if error:
                st.error(f"Error: {error}")
                if "HTTP Error 400" in error or "HTTP Error 403" in error:
                    st.info(
                        "This often happens because YouTube is rejecting the request "
                        "(bot-detection, or a region/age-restricted video). Try a "
                        "different video, or try again in a moment."
                    )
            else:
                if note:
                    st.warning(note)

                # Read the bytes into memory immediately, then delete the
                # server-side temp file. The download link below is the
                # ONLY place the file exists after this point — there is
                # no separate copy sitting on the server to be confused
                # about, and nothing for the server to clean up later.
                with open(file_path, "rb") as f:
                    file_bytes = f.read()
                os.remove(file_path)

                st.session_state["ready_file"] = {
                    "bytes": file_bytes,
                    "name": os.path.basename(file_path),
                    "mime": "audio/mpeg" if download_type == "Audio" else "video/mp4",
                }
                st.session_state["ready_file_inputs"] = {
                    "url": url, "type": download_type, "resolution": resolution,
                }

# Show the download link whenever a fetched file is waiting in memory, so
# it survives Streamlit's rerun when the download itself is clicked.
if "ready_file" in st.session_state:
    ready = st.session_state["ready_file"]
    size_label = human_size(len(ready["bytes"]))

    st.success(f"**Ready to download:** `{ready['name']}` ({size_label})")

    st.download_button(
        label=f"⬇ Download {ready['name']} ({size_label})",
        data=ready["bytes"],
        file_name=ready["name"],
        mime=ready["mime"],
        type="primary",
        use_container_width=True,
        # Prevents the click from triggering a script rerun. Without this,
        # some Streamlit versions can swallow the click (especially the
        # first one after a Fetch) because the rerun races with the file
        # being served — the button visibly "clicks" but no browser
        # download starts. The data here is already fixed in session_state,
        # so there's nothing that needs to be recomputed on click anyway.
        on_click="ignore",
    )
    st.caption(
        "Clicking the link/button above saves the file through your browser's "
        "own download flow — see the 'Where will the file be saved?' section "
        "above to control which folder it lands in."
    )
