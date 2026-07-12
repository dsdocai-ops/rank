"""Mobile Video Ranker — 9:16 ranking-countdown video generator.

Layout
------
+------------------------------+
|        HEADER (title)        |  <- constant text overlay at the top
+---------+--------------------+
| 01 Word |                    |
| 02 Word |    active clip     |  <- clips play sequentially, centred
| ...     |   (fit to stage)   |     in the stage area
+---------+--------------------+

Behaviour
---------
* A constant background layer runs for the whole video.
* Each sidebar entry ("01 Word") pops in at 100% opacity on the exact
  frame its clip starts, and drops to a translucent state the moment
  the clip ends (it never fully disappears).
* Audio stays in sync because every layer's start time is derived from
  the same cumulative sum of source-clip durations.

Requires moviepy >= 2.0 (Pillow-based TextClip, no ImageMagick needed).
"""

import os
import tempfile

import streamlit as st
from moviepy import ColorClip, CompositeVideoClip, TextClip, VideoFileClip

# ======================================================================
# CONFIGURATION — edit this block to reuse the script as a template
# ======================================================================

# Canvas (9:16 vertical)
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
BACKGROUND_COLOR = (0, 0, 0)          # constant background layer (RGB)

# Regions
HEADER_HEIGHT = 200                   # top strip reserved for the title
SIDEBAR_WIDTH = 320                   # left strip reserved for numbering
ROW_HEIGHT = 160                      # vertical spacing between entries
ROW_TOP_PADDING = 60                  # offset of first row below header
ROW_LEFT_PADDING = 20                 # x offset of sidebar text

# Clips & ordering
CLIP_COUNT = 6
PLAYBACK_ORDER = [6, 5, 4, 3, 2, 1]   # ranks in the order their clips play
SIDEBAR_ORDER = [1, 2, 3, 4, 5, 6]    # ranks top-to-bottom in the sidebar

# Opacity states
ACTIVE_OPACITY = 1.0                  # while an entry's clip is playing
FINISHED_OPACITY = 0.4                # after the entry's clip has ended

# Text styling
TITLE_FONT_SIZE = 52
LABEL_FONT_SIZE = 42
TEXT_COLOR = "white"
TEXT_MARGIN = 20                      # padding so descenders aren't clipped
FONT_CANDIDATES = [                   # first existing path wins
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

# Output
OUTPUT_FPS = 30
OUTPUT_CODEC = "libx264"
OUTPUT_AUDIO_CODEC = "aac"
OUTPUT_PRESET = "medium"              # x264 speed/size trade-off
DOWNLOAD_FILENAME = "my_ranking_video.mp4"

# ======================================================================
# RENDERING
# ======================================================================


def resolve_font() -> str:
    """Return the first available font path from FONT_CANDIDATES."""
    for path in FONT_CANDIDATES:
        if os.path.isfile(path):
            return path
    raise FileNotFoundError(
        "No usable font found. Add a .ttf path to FONT_CANDIDATES."
    )


def build_ranking_video(title: str, entries: list[dict], output_path: str) -> None:
    """Render the composite video.

    ``entries`` is a list of {"rank": int, "label": str, "path": str}
    in playback order.
    """
    font = resolve_font()
    stage_width = VIDEO_WIDTH - SIDEBAR_WIDTH
    stage_height = VIDEO_HEIGHT - HEADER_HEIGHT

    source_clips: list[VideoFileClip] = []
    final = None
    try:
        for entry in entries:
            clip = VideoFileClip(entry["path"])
            source_clips.append(clip)
            entry["clip"] = clip

        total_duration = sum(clip.duration for clip in source_clips)

        background = ColorClip(
            size=(VIDEO_WIDTH, VIDEO_HEIGHT),
            color=BACKGROUND_COLOR,
            duration=total_duration,
        )

        title_clip = (
            TextClip(font=font, text=title, font_size=TITLE_FONT_SIZE,
                     color=TEXT_COLOR, margin=(TEXT_MARGIN, TEXT_MARGIN))
            .with_position(("center", HEADER_HEIGHT // 2 - TITLE_FONT_SIZE // 2))
            .with_duration(total_duration)
        )

        video_layers = []
        label_layers = []
        start_time = 0.0

        for entry in entries:
            clip = entry["clip"]
            duration = clip.duration
            end_time = start_time + duration

            # Fit the clip inside the stage, preserving aspect ratio.
            scale = min(stage_width / clip.w, stage_height / clip.h)
            fitted = clip.resized(scale)
            x = SIDEBAR_WIDTH + (stage_width - fitted.w) / 2
            y = HEADER_HEIGHT + (stage_height - fitted.h) / 2
            video_layers.append(
                fitted.with_start(start_time).with_position((x, y))
            )

            # Sidebar entry: rendered once, reused for both opacity states.
            row_index = SIDEBAR_ORDER.index(entry["rank"])
            row_y = HEADER_HEIGHT + ROW_TOP_PADDING + row_index * ROW_HEIGHT
            label = TextClip(
                font=font,
                text=f"{entry['rank']:02d}  {entry['label']}",
                font_size=LABEL_FONT_SIZE,
                color=TEXT_COLOR,
                margin=(TEXT_MARGIN, TEXT_MARGIN),
            ).with_position((ROW_LEFT_PADDING - TEXT_MARGIN, row_y - TEXT_MARGIN))

            # Active state: pops in on the exact frame the clip starts.
            label_layers.append(
                label.with_opacity(ACTIVE_OPACITY)
                .with_start(start_time)
                .with_duration(duration)
            )

            # Finished state: translucent from the frame the clip ends
            # until the end of the video.
            if end_time < total_duration:
                label_layers.append(
                    label.with_opacity(FINISHED_OPACITY)
                    .with_start(end_time)
                    .with_duration(total_duration - end_time)
                )

            start_time = end_time

        final = CompositeVideoClip(
            [background, title_clip, *label_layers, *video_layers],
            size=(VIDEO_WIDTH, VIDEO_HEIGHT),
        ).with_duration(total_duration)

        final.write_videofile(
            output_path,
            fps=OUTPUT_FPS,
            codec=OUTPUT_CODEC,
            audio_codec=OUTPUT_AUDIO_CODEC,
            preset=OUTPUT_PRESET,
            threads=os.cpu_count() or 2,
        )
    finally:
        if final is not None:
            final.close()
        for clip in source_clips:
            clip.close()


# ======================================================================
# STREAMLIT UI
# ======================================================================


def main() -> None:
    st.set_page_config(page_title="Video Ranker", layout="centered")
    st.title("🎬 Mobile Video Ranker")
    st.write(
        f"Upload {CLIP_COUNT} clips, add your labels, and render your "
        "ranking video directly."
    )

    title = st.text_input("Ranking Title", value="My Ranking")

    st.write(
        f"### Enter Descriptions (Clips play from "
        f"{PLAYBACK_ORDER[0]} to {PLAYBACK_ORDER[-1]})"
    )
    labels = {
        rank: st.text_input(
            f"1-Word Description for Rank {rank}",
            value=f"Label{rank}",
            key=f"word_{rank}",
        )
        for rank in PLAYBACK_ORDER
    }

    st.write("### Upload Video Clips")
    uploads = {
        rank: st.file_uploader(
            f"Upload Clip for Rank {rank}",
            type=["mp4", "mov", "avi"],
            key=f"file_{rank}",
        )
        for rank in PLAYBACK_ORDER
    }

    if st.button("🚀 Render Layout & Video"):
        if any(upload is None for upload in uploads.values()):
            st.error(f"Please upload all {CLIP_COUNT} video clips before rendering.")
        else:
            with st.spinner("Rendering video… this may take a few minutes."):
                try:
                    with tempfile.TemporaryDirectory() as workdir:
                        entries = []
                        for rank in PLAYBACK_ORDER:
                            upload = uploads[rank]
                            extension = os.path.splitext(upload.name)[1] or ".mp4"
                            path = os.path.join(workdir, f"rank_{rank}{extension}")
                            with open(path, "wb") as handle:
                                handle.write(upload.getbuffer())
                            entries.append(
                                {"rank": rank, "label": labels[rank], "path": path}
                            )

                        output_path = os.path.join(workdir, "output.mp4")
                        build_ranking_video(title, entries, output_path)

                        # Keep the bytes in session state so the download
                        # button survives Streamlit reruns.
                        with open(output_path, "rb") as handle:
                            st.session_state["rendered_video"] = handle.read()
                    st.success("Render complete!")
                except Exception as error:  # surface render errors in the UI
                    st.error(f"A processing error occurred: {error}")

    if "rendered_video" in st.session_state:
        st.download_button(
            label="📥 Download Finished Video",
            data=st.session_state["rendered_video"],
            file_name=DOWNLOAD_FILENAME,
            mime="video/mp4",
        )


if __name__ == "__main__":
    main()
