import streamlit as st
from pytubefix import YouTube
from moviepy.editor import AudioFileClip
import os
import re

# Create download directory
directory = 'downloads/'
if not os.path.exists(directory):
    os.makedirs(directory)

# Streamlit page setup
st.set_page_config(page_title="YTD", page_icon="🚀", layout="wide")
st.markdown(f"""
    <style>
    .stApp {{
        background-image: url("https://images.unsplash.com/photo-1516557070061-c3d1653fa646?ixlib=rb-4.0.3&ixid=MnwxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8&auto=format&fit=crop&w=2070&q=80"); 
        background-attachment: fixed;
        background-size: cover;
    }}
    </style>
    """, unsafe_allow_html=True)

# Function to fetch video details
@st.cache_resource
def get_info(url):
    try:
        yt = YouTube(url)
        streams = yt.streams.filter(progressive=True, type='video')
        if not streams:
            raise ValueError("No progressive streams available for this video.")
        details = {
            "image": yt.thumbnail_url,
            "streams": streams,
            "title": yt.title,
            "length": yt.length
        }
        itag, resolutions, vformat, frate = ([] for _ in range(4))
        for i in streams:
            res = re.search(r'(\d+)p', str(i))
            typ = re.search(r'video/(\w+)', str(i))
            fps = re.search(r'(\d+)fps', str(i))
            tag = re.search(r'itag="(\d+)"', str(i))
            itag.append(tag.group(1) if tag else "0")
            resolutions.append(res.group(0) if res else "N/A")
            vformat.append(typ.group(1) if typ else "N/A")
            frate.append(fps.group(1) if fps else "N/A")
        details["resolutions"] = resolutions
        details["itag"] = itag
        details["fps"] = frate
        details["format"] = vformat
        return details
    except Exception as e:
        st.error(f"Error fetching video info: {str(e)}", icon="🚨")
        return None

# UI
st.title("YouTube Downloader 🚀")
url = st.text_input("Paste URL here 👇", placeholder='https://www.youtube.com/')

if url:
    try:
        yt = YouTube(url)
        st.image(yt.thumbnail_url)
        format_choice = st.radio("Choose Download Format", ["Video (MP4)", "Audio (MP3)"])

        if format_choice == "Video (MP4)":
            v_info = get_info(url)
            if v_info:
                col1, col2 = st.columns([1, 1.5], gap="small")
                with col1:
                    st.image(v_info["image"])
                with col2:
                    st.subheader("Video Details ⚙️")
                    res_inp = st.selectbox('__Select Resolution__', v_info["resolutions"])
                    id = v_info["resolutions"].index(res_inp)
                    st.write(f"__Title:__ {v_info['title']}")
                    st.write(f"__Length:__ {v_info['length']} sec")
                    st.write(f"__Resolution:__ {v_info['resolutions'][id]}")
                    st.write(f"__Frame Rate:__ {v_info['fps'][id]}")
                    st.write(f"__Format:__ {v_info['format'][id]}")
                    file_name = st.text_input('__Save as 🎯__', placeholder=v_info['title'])
                    if not file_name.endswith(".mp4"):
                        file_name += ".mp4"

                if st.button("Download Video ⚡️"):
                    with st.spinner('Downloading video...'):
                        try:
                            ds = v_info["streams"].get_by_itag(v_info['itag'][id])
                            ds.download(filename=file_name, output_path=directory)
                            st.success('Download Complete ✅')
                            st.balloons()
                        except Exception as e:
                            st.error(f'Error: {str(e)}', icon="🚨")

        elif format_choice == "Audio (MP3)":
            st.subheader("Audio Download 🎵")
            st.write(f"__Title:__ {yt.title}")
            file_name = st.text_input('__Save as 🎯__', placeholder=yt.title)
            if not file_name.endswith(".mp3"):
                file_name += ".mp3"
            if st.button("Download Audio 🎧"):
                with st.spinner("Downloading audio..."):
                    try:
                        audio_stream = yt.streams.filter(only_audio=True).first()
                        temp_file = audio_stream.download(output_path=directory, filename="temp_audio.mp4")
                        mp3_path = os.path.join(directory, file_name)
                        clip = AudioFileClip(temp_file)
                        clip.write_audiofile(mp3_path)
                        clip.close()
                        os.remove(temp_file)
                        st.success("Audio downloaded successfully! 🎧")
                        st.balloons()
                    except Exception as e:
                        st.error(f"Audio download failed: {e}", icon="🚨")
    except Exception as e:
        st.error(f"Error initializing video: {str(e)}", icon="🚨")
