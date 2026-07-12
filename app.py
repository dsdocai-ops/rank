"""Mobile Video Ranker — 9:16 ranking-countdown video generator.

Layout (modelled on the reference Short)
----------------------------------------
+------------------------------+
|   TITLE (black bar, words    |  <- constant, words can be coloured
|     individually coloured)   |
+------------------------------+
| 1. Word |                    |
| 2. Word |  full-width clip   |  <- clips play as a 6 -> 1 countdown,
| 3. Word :  (list overlaps)   |     filling the width; the ranking
| 6. Word :                    |     list is overlaid on the left edge
| 4. Word |                    |
| 5. Word |                    |
+------------------------------+

Behaviour
---------
* A constant background layer runs for the whole video.
* Every rank NUMBER ("1." ... "6.") is visible at full opacity from the
  first frame, in its configured colour.
* Each LABEL pops in at 100% opacity on the exact frame its clip
  starts; the moment the clip ends the whole row (number + label)
  drops to a translucent state (it never fully disappears).
* An optional glitch image + sound plays between consecutive clips.
* Optional background music is mixed underneath the clip audio.
* Audio stays in sync because every layer's start time is derived from
  the same cumulative timeline.

Requires moviepy >= 2.0 (Pillow-based TextClip, no ImageMagick needed).
"""

import os
import tempfile

import streamlit as st
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoFileClip,
)
from moviepy.audio.fx import AudioLoop

# ======================================================================
# CONFIGURATION — edit this block to reuse the script as a template
# ======================================================================

# Canvas (9:16 vertical)
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
BACKGROUND_COLOR = (0, 0, 0)          # constant background layer (RGB)

# Regions
HEADER_HEIGHT = 200                   # black title bar height at the top
ROW_HEIGHT = 160                      # vertical spacing between entries
ROW_TOP_PADDING = 60                  # offset of first row below header
ROW_LEFT_PADDING = 40                 # x offset of the overlaid list
NUMBER_LABEL_GAP = 4                  # px between "3." and its label

# Clips & ordering
CLIP_COUNT = 6
PLAYBACK_ORDER = [6, 5, 4, 3, 2, 1]   # ranks in the order their clips play
SIDEBAR_ORDER = [1, 2, 3, 6, 4, 5]    # ranks top-to-bottom (as reference)

# Opacity states
ACTIVE_OPACITY = 1.0                  # while an entry's clip is playing
FINISHED_OPACITY = 0.4                # after the entry's clip has ended

# Text styling
TITLE_FONT_SIZE = 52
TITLE_SIDE_PADDING = 40               # min gap between title and edges
TITLE_LINE_SPACING = 1.3              # line height multiplier
LABEL_FONT_SIZE = 42
TEXT_COLOR = "white"
LABEL_STROKE_COLOR = "black"          # outline keeps text readable on video
LABEL_STROKE_WIDTH = 2
TEXT_MARGIN = 20                      # padding so descenders aren't clipped
NUMBER_COLORS = {                     # per-rank number colours
    1: "#FFD400",                     # yellow
    2: "#FF7A00",                     # orange
    3: "#FF2E2E",                     # red
}                                     # ranks not listed fall back to white
TITLE_WORD_COLORS = {                 # colour title words (lowercase key,
    # "funniest": "#FF2E2E",          #  punctuation ignored); others are
    # "tortilla": "#00E5FF",          #  rendered in TEXT_COLOR
    # "challenge": "#00E5FF",
}
FONT_CANDIDATES = [                   # first existing path wins
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

# Transition (glitch image + sound between consecutive clips)
TRANSITION_DURATION = 0.5             # seconds

# Background music
MUSIC_VOLUME = 0.15                   # 0..1, mixed under the clip audio

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


def make_text(text: str, font: str, font_size: int, color: str) -> TextClip:
    """Outlined text clip with margins so descenders aren't clipped."""
    return TextClip(
        font=font,
        text=text,
        font_size=font_size,
        color=color,
        stroke_color=LABEL_STROKE_COLOR,
        stroke_width=LABEL_STROKE_WIDTH,
        margin=(TEXT_MARGIN, TEXT_MARGIN),
    )


def build_title_layers(title: str, font: str, duration: float) -> list:
    """Word-by-word title layout: centred lines, per-word colours."""
    words = title.split()
    if not words:
        return []

    space_width = TITLE_FONT_SIZE * 0.35
    max_line_width = VIDEO_WIDTH - 2 * TITLE_SIDE_PADDING
    line_height = TITLE_FONT_SIZE * TITLE_LINE_SPACING

    rendered = []
    for word in words:
        color = TITLE_WORD_COLORS.get(
            word.lower().strip(".,!?:;"), TEXT_COLOR
        )
        clip = make_text(word, font, TITLE_FONT_SIZE, color)
        rendered.append((clip, clip.w - 2 * TEXT_MARGIN))

    # Greedy wrap into lines.
    lines, current, current_width = [], [], 0.0
    for clip, width in rendered:
        needed = width if not current else current_width + space_width + width
        if current and needed > max_line_width:
            lines.append((current, current_width))
            current, current_width = [(clip, width)], width
        else:
            current.append((clip, width))
            current_width = needed
    lines.append((current, current_width))

    block_top = (HEADER_HEIGHT - len(lines) * line_height) / 2
    layers = []
    for line_index, (line, line_width) in enumerate(lines):
        x = (VIDEO_WIDTH - line_width) / 2
        y = block_top + line_index * line_height
        for clip, width in line:
            layers.append(
                clip.with_position((x - TEXT_MARGIN, y - TEXT_MARGIN))
                .with_duration(duration)
            )
            x += width + space_width
    return layers


def cover_canvas(clip):
    """Scale a clip to cover the full canvas, centred (overflow crops)."""
    scale = max(VIDEO_WIDTH / clip.w, VIDEO_HEIGHT / clip.h)
    fitted = clip.resized(scale)
    return fitted.with_position(
        ((VIDEO_WIDTH - fitted.w) / 2, (VIDEO_HEIGHT - fitted.h) / 2)
    )


def build_ranking_video(
    title: str,
    entries: list[dict],
    output_path: str,
    transition_image: str | None = None,
    transition_sound: str | None = None,
    music: str | None = None,
) -> None:
    """Render the composite video.

    ``entries`` is a list of {"rank": int, "label": str, "path": str}
    in playback order. ``transition_image``/``transition_sound`` play
    between consecutive clips; ``music`` loops underneath everything.
    """
    font = resolve_font()
    stage_height = VIDEO_HEIGHT - HEADER_HEIGHT

    to_close: list = []
    final = None
    try:
        for entry in entries:
            clip = VideoFileClip(entry["path"])
            to_close.append(clip)
            entry["clip"] = clip

        transition_count = len(entries) - 1 if transition_image else 0
        total_duration = (
            sum(entry["clip"].duration for entry in entries)
            + transition_count * TRANSITION_DURATION
        )

        background = ColorClip(
            size=(VIDEO_WIDTH, VIDEO_HEIGHT),
            color=BACKGROUND_COLOR,
            duration=total_duration,
        )

        # Black title bar layered ABOVE the video so full-height clips
        # slide underneath it instead of covering the title.
        header_bar = ColorClip(
            size=(VIDEO_WIDTH, HEADER_HEIGHT),
            color=BACKGROUND_COLOR,
            duration=total_duration,
        )
        title_layers = build_title_layers(title, font, total_duration)

        video_layers = []
        text_layers = []
        transition_layers = []
        cursor = 0.0

        for index, entry in enumerate(entries):
            clip = entry["clip"]
            start_time = cursor
            end_time = start_time + clip.duration

            # Full-width clip, centred vertically below the header
            # (overflow is cropped / hidden behind the header bar).
            fitted = clip.resized(width=VIDEO_WIDTH)
            y = HEADER_HEIGHT + (stage_height - fitted.h) / 2
            video_layers.append(
                fitted.with_start(start_time).with_position((0, y))
            )

            # Row geometry.
            row_index = SIDEBAR_ORDER.index(entry["rank"])
            row_y = HEADER_HEIGHT + ROW_TOP_PADDING + row_index * ROW_HEIGHT

            # Number ("3."): visible from frame 0, dims when its clip
            # ends. Rendered once, reused for both opacity states.
            number = make_text(
                f"{entry['rank']}.",
                font,
                LABEL_FONT_SIZE,
                NUMBER_COLORS.get(entry["rank"], TEXT_COLOR),
            ).with_position((ROW_LEFT_PADDING - TEXT_MARGIN, row_y - TEXT_MARGIN))
            text_layers.append(
                number.with_start(0).with_duration(end_time)
            )
            if end_time < total_duration:
                text_layers.append(
                    number.with_opacity(FINISHED_OPACITY)
                    .with_start(end_time)
                    .with_duration(total_duration - end_time)
                )

            # Label: pops in on the exact frame its clip starts, dims
            # the frame the clip ends.
            label_x = (
                ROW_LEFT_PADDING
                + (number.w - 2 * TEXT_MARGIN)
                + NUMBER_LABEL_GAP
            )
            label = make_text(
                entry["label"], font, LABEL_FONT_SIZE, TEXT_COLOR
            ).with_position((label_x - TEXT_MARGIN, row_y - TEXT_MARGIN))
            text_layers.append(
                label.with_opacity(ACTIVE_OPACITY)
                .with_start(start_time)
                .with_duration(clip.duration)
            )
            if end_time < total_duration:
                text_layers.append(
                    label.with_opacity(FINISHED_OPACITY)
                    .with_start(end_time)
                    .with_duration(total_duration - end_time)
                )

            cursor = end_time

            # Glitch transition between consecutive clips, covering the
            # whole canvas (above every other layer, like the reference).
            if transition_image and index < len(entries) - 1:
                glitch = ImageClip(transition_image).with_duration(
                    TRANSITION_DURATION
                )
                glitch = cover_canvas(glitch).with_start(cursor)
                if transition_sound:
                    sound = AudioFileClip(transition_sound)
                    to_close.append(sound)
                    if sound.duration > TRANSITION_DURATION:
                        sound = sound.subclipped(0, TRANSITION_DURATION)
                    glitch = glitch.with_audio(sound)
                transition_layers.append(glitch)
                cursor += TRANSITION_DURATION

        final = CompositeVideoClip(
            [
                background,
                *video_layers,
                header_bar,
                *title_layers,
                *text_layers,
                *transition_layers,
            ],
            size=(VIDEO_WIDTH, VIDEO_HEIGHT),
        ).with_duration(total_duration)

        if music:
            music_clip = AudioFileClip(music)
            to_close.append(music_clip)
            if music_clip.duration < total_duration:
                music_clip = music_clip.with_effects(
                    [AudioLoop(duration=total_duration)]
                )
            else:
                music_clip = music_clip.subclipped(0, total_duration)
            music_clip = music_clip.with_volume_scaled(MUSIC_VOLUME)
            mixed = (
                CompositeAudioClip([final.audio, music_clip])
                if final.audio is not None
                else music_clip
            )
            final = final.with_audio(mixed)

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
        for clip in to_close:
            clip.close()


# ======================================================================
# STREAMLIT UI
# ======================================================================


def _save_upload(upload, workdir: str, stem: str) -> str:
    """Persist a Streamlit upload to disk, keeping its extension."""
    extension = os.path.splitext(upload.name)[1] or ".bin"
    path = os.path.join(workdir, f"{stem}{extension}")
    with open(path, "wb") as handle:
        handle.write(upload.getbuffer())
    return path


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
            f"Short Description for Rank {rank}",
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

    st.write("### Optional Extras")
    glitch_image = st.file_uploader(
        "Glitch transition image (shown between clips)",
        type=["png", "jpg", "jpeg", "webp"],
        key="glitch_image",
    )
    glitch_sound = st.file_uploader(
        "Glitch transition sound",
        type=["mp3", "wav", "m4a", "aac", "ogg"],
        key="glitch_sound",
    )
    music = st.file_uploader(
        "Background music (looped under the clips)",
        type=["mp3", "wav", "m4a", "aac", "ogg"],
        key="music",
    )

    if st.button("🚀 Render Layout & Video"):
        if any(upload is None for upload in uploads.values()):
            st.error(f"Please upload all {CLIP_COUNT} video clips before rendering.")
        else:
            with st.spinner("Rendering video… this may take a few minutes."):
                try:
                    with tempfile.TemporaryDirectory() as workdir:
                        entries = [
                            {
                                "rank": rank,
                                "label": labels[rank],
                                "path": _save_upload(
                                    uploads[rank], workdir, f"rank_{rank}"
                                ),
                            }
                            for rank in PLAYBACK_ORDER
                        ]

                        output_path = os.path.join(workdir, "output.mp4")
                        build_ranking_video(
                            title,
                            entries,
                            output_path,
                            transition_image=(
                                _save_upload(glitch_image, workdir, "glitch")
                                if glitch_image
                                else None
                            ),
                            transition_sound=(
                                _save_upload(glitch_sound, workdir, "glitch_sfx")
                                if glitch_sound
                                else None
                            ),
                            music=(
                                _save_upload(music, workdir, "music")
                                if music
                                else None
                            ),
                        )

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

