import streamlit as st
import os
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip

st.set_page_config(page_title="Video Ranker", layout="centered")
st.title("🎬 Mobile Video Ranker")
st.write("Upload 6 clips, add your labels, and render your ranking video directly.")

# 1. Inputs for Title and Words
ranking_title = st.text_input("Ranking Title", value="My Ranking")

st.write("### Enter Descriptions (Clips will play from 6 down to 1)")
words = []
for i in range(6, 0, -1):
    word = st.text_input(f"1-Word Description for Rank {i}", value=f"Label{i}", key=f"word_{i}")
    words.append(word) # Ordered [Word6, Word5, Word4, Word3, Word2, Word1]

# 2. File Uploaders
st.write("### Upload Video Clips")
uploaded_files = []
for i in range(6, 0, -1):
    f = st.file_uploader(f"Upload Clip for Rank {i}", type=["mp4", "mov", "avi"], key=f"file_{i}")
    uploaded_files.append(f)

# 3. Execution Render Logic
if st.button("🚀 Render Layout & Video"):
    # Check if all files are uploaded
    if any(f is None for f in uploaded_files):
        st.error("Please upload all 6 video clips before rendering.")
    else:
        with st.spinner("Processing video... This may take a minute depending on clip sizes."):
            try:
                # Save uploaded files temporarily
                temp_paths = []
                for idx, f in enumerate(uploaded_files):
                    path = f"temp_rank_{6-idx}.mp4"
                    with open(path, "wb") as buffer:
                        buffer.write(f.read())
                    temp_paths.append(path)

                # Layout Variables
                sidebar_order = [1, 2, 3, 6, 4, 5]
                width, height = 1080, 1920
                header_height = 200
                sidebar_width = 320
                
                # Load video clips and determine total duration
                clips_objects = []
                total_duration = 0
                for p in temp_paths:
                    clip = VideoFileClip(p).resize(width=width - sidebar_width)
                    clips_objects.append(clip)
                    total_duration += clip.duration

                # Header construction
                header_bg = TextClip("", size=(width, header_height), bg_color='black')
                header_text = TextClip(f"Ranking: {ranking_title}", fontsize=52, color='white', font='Arial-Bold')
                header_text = header_text.set_position(('center', 'center'))
                header = CompositeVideoClip([header_bg, header_text]).set_duration(total_duration)

                sidebar_clips = []
                processed_clips = []
                running_time = 0

                # Process clips from 6 down to 1
                for i in range(6):
                    clip = clips_objects[i]
                    word = words[i]
                    clip_dur = clip.duration
                    current_rank_num = 6 - i
                    
                    # Compute vertical position based on exact requested list layout (1,2,3,6,4,5)
                    vertical_index = sidebar_order.index(current_rank_num)
                    y_pos = header_height + (vertical_index * 160) + 60
                    
                    # Active text state (100% visible while clip plays)
                    active_txt = TextClip(f"{current_rank_num}. {word}", fontsize=42, color='white', font='Arial-Bold')
                    active_txt = active_txt.set_position((20, y_pos)).set_start(running_time).set_duration(clip_dur)
                    sidebar_clips.append(active_txt)
                    
                    # Translucent text state (40% visible after clip finishes)
                    if (running_time + clip_dur) < total_duration:
                        done_dur = total_duration - (running_time + clip_dur)
                        done_txt = TextClip(f"{current_rank_num}. {word}", fontsize=42, color='white', font='Arial-Bold')
                        done_txt = done_txt.set_position((20, y_pos)).set_opacity(0.4).set_start(running_time + clip_dur).set_duration(done_dur)
                        sidebar_clips.append(done_txt)
                    
                    # Position video next to sidebar
                    playing_clip = clip.set_start(running_time).set_position((sidebar_width, header_height))
                    processed_clips.append(playing_clip)
                    
                    running_time += clip_dur

                # Assemble final master file
                bg_canvas = TextClip("", size=(width, height), bg_color='black').set_duration(total_duration)
                final_video = CompositeVideoClip([bg_canvas, header] + sidebar_clips + processed_clips, size=(width, height))
                
                output_filename = "mobile_output.mp4"
                final_video.write_videofile(output_filename, fps=24, codec="libx264", audio_codec="aac")
                
                # Close files to clean up hooks
                for c in clips_objects:
                    c.close()

                # Present download button directly in mobile browser
                with open(output_filename, "rb") as file:
                    st.download_button(
                        label="📥 Download Finished Video",
                        data=file,
                        file_name="my_ranking_video.mp4",
                        mime="video/mp4"
                    )
                
                # Cleanup temp files
                for p in temp_paths:
                    if os.path.exists(p): os.remove(p)
                if os.path.exists(output_filename): os.remove(output_filename)

            except Exception as e:
                st.error(f"An processing error occurred: {e}")