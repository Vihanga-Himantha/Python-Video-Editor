import json
import os
import requests
import shutil
import math
# Pillow is needed for the resizing method used
from PIL import Image
# Moviepy imports
from moviepy.editor import (ImageClip, concatenate_videoclips, CompositeVideoClip,
                            VideoFileClip, AudioFileClip, TextClip)
# Explicit import for older moviepy compatibility / clarity
from moviepy.audio.AudioClip import concatenate_audioclips, CompositeAudioClip
# Added CompositeAudioClip

# --- Configuration ---
TEMP_ASSET_DIR = "temp_video_assets"
DEFAULT_TRANSITION_DURATION = 1.0
DEFAULT_AUDIO_FADE_SECONDS = 1.0
# Reduce background music volume if voiceovers are present?
DUCK_BG_MUSIC_FACTOR = 0.5 # Set to 1.0 to disable ducking

# --- Mappings ---
RESOLUTION_MAP = {
    "sd": (640, 480), "hd": (1280, 720), "full-hd": (1920, 1080), "4k": (3840, 2160),
}
QUALITY_MAP = {
    "low": {"preset": "ultrafast", "crf": 28}, "medium": {"preset": "medium", "crf": 23},
    "high": {"preset": "slow", "crf": 18}, "production": {"preset": "veryslow", "crf": 16}
}

# --- Helper Functions ---

def check_local_file(path):
    """Checks if a file exists locally."""
    return os.path.isfile(path)

def download_asset(url, download_path):
    """Downloads a file from a URL to a specified path."""
    try:
        print(f"Attempting to download: {url} to {download_path}")
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        with open(download_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Downloaded asset successfully.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error downloading {url}: {e}")
        return False
    except Exception as e:
        print(f"Error saving file {download_path}: {e}")
        return False

def get_ffmpeg_params(quality_str):
    """Gets FFmpeg preset and crf based on quality string."""
    quality_settings = QUALITY_MAP.get(quality_str, QUALITY_MAP["medium"])
    return quality_settings['preset'], ["-crf", str(quality_settings['crf'])]

# --- Main Video Creation Function ---

def create_video_from_json(json_data, output_filename="output_video.mp4"):
    """
    Creates a video from a JSON definition using MoviePy, including background
    music and scene-specific voiceovers.
    """
    global TEMP_ASSET_DIR, DUCK_BG_MUSIC_FACTOR

    # 1. Parse Global Settings
    resolution_str = json_data.get("resolution", "hd")
    quality_str = json_data.get("quality", "medium")
    target_resolution = RESOLUTION_MAP.get(resolution_str, RESOLUTION_MAP["hd"])
    ffmpeg_preset, ffmpeg_extra_params = get_ffmpeg_params(quality_str)
    scenes_data = json_data.get("scenes", [])
    audio_info = json_data.get("audio", {})
    bg_audio_path = audio_info.get("src") # Expecting LOCAL PATH for audio now
    bg_audio_volume = audio_info.get("volume", 1.0)

    has_voiceovers = any(scene.get("voiceover", {}).get("src") for scene in scenes_data)

    if not scenes_data:
        print("Error: No scenes found in JSON data.")
        return

    # 2. Prepare Temporary Directory for Assets (visuals only)
    if os.path.exists(TEMP_ASSET_DIR):
        shutil.rmtree(TEMP_ASSET_DIR)
    os.makedirs(TEMP_ASSET_DIR, exist_ok=True)

    # 3. Process Scenes (Visuals and Collect Audio Info)
    processed_elements = [] # Holds dicts: {"clip": visual_clip, "voiceover_clip": audio_clip|None, "scene_duration": float, "transition_to_this": dict|None}
    download_success = True
    print("--- Processing Scenes (Visuals & Audio Info) ---")

    for i, scene in enumerate(scenes_data):
        print(f"Processing Scene #{i+1}: {scene.get('comment', '')}")
        scene_elements = scene.get("elements", [])
        scene_visual_clips = [] # Visual clips within this scene
        scene_voiceover_clip = None # Voiceover for this scene
        scene_duration = 0 # Calculated visual duration

        if not scene_elements:
            print(f"Warning: Scene #{i+1} has no visual elements. Skipping.")
            continue

        # --- Process visual elements ---
        for j, element in enumerate(scene_elements):
            element_type = element.get("type")
            element_src = element.get("src")
            element_duration = element.get("duration")
            element_text = element.get("text")
            clip = None

            if element_type == "image" and element_src and element_duration:
                asset_filename = f"scene_{i}_elem_{j}_{os.path.basename(element_src)}"
                local_path = os.path.join(TEMP_ASSET_DIR, asset_filename)
                if not download_asset(element_src, local_path):
                    download_success = False; continue
                try:
                    pil_image = Image.open(local_path)
                    img_ratio = pil_image.size[0] / pil_image.size[1]
                    target_h = target_resolution[1]
                    target_w = int(target_h * img_ratio)
                    if target_w > target_resolution[0]:
                        target_w = target_resolution[0]
                        target_h = int(target_w / img_ratio)
                    # Ensure Pillow >= 9.0.0 for Image.Resampling
                    pil_image = pil_image.resize((target_w, target_h), Image.Resampling.LANCZOS)
                    pil_image.save(local_path) # Save resized version

                    clip = ImageClip(local_path, duration=element_duration).set_position('center')
                    scene_duration = max(scene_duration, element_duration)
                except Exception as e: print(f"Error processing image {local_path}: {e}"); continue

            elif element_type == "video" and element_src:
                asset_filename = f"scene_{i}_elem_{j}_{os.path.basename(element_src)}"
                local_path = os.path.join(TEMP_ASSET_DIR, asset_filename)
                if not download_asset(element_src, local_path):
                    download_success = False; continue
                try:
                    clip = VideoFileClip(local_path, target_resolution=target_resolution)
                    element_duration = clip.duration if not element_duration else min(clip.duration, element_duration)
                    clip = clip.subclip(0, element_duration)
                    # Apply resize after subclip
                    clip = clip.resize(height=target_resolution[1])
                    if clip.w > target_resolution[0]: clip = clip.resize(width=target_resolution[0])
                    clip = clip.set_position('center')
                    scene_duration = max(scene_duration, element_duration)
                except Exception as e: print(f"Error processing video {local_path}: {e}"); continue

            elif element_type == "text" and element_text and element_duration:
                try:
                    fontsize = element.get("fontsize", 70)
                    font = element.get("font", "Arial")
                    color = element.get("color", "white")
                    bg_color = element.get("bg_color", "transparent")
                    pos = element.get("position", "center")
                    clip = TextClip(element_text, fontsize=fontsize, font=font, color=color, bg_color=bg_color)
                    clip = clip.set_duration(element_duration).set_position(pos)
                    scene_duration = max(scene_duration, element_duration)
                except Exception as e: print(f"Error creating text clip: {e}"); continue
            else:
                print(f"Warning: Unsupported element type '{element_type}' or missing data in Scene #{i+1}. Skipping.")
                continue

            if clip: scene_visual_clips.append(clip)

        # --- Combine visual elements for the scene ---
        scene_visual_composite = None
        if scene_visual_clips:
            scene_visual_composite = CompositeVideoClip(scene_visual_clips, size=target_resolution).set_duration(scene_duration)
        else:
            print(f"Warning: Scene #{i+1} resulted in no processable visual clips.")
            continue # Skip scene if no visuals

        # --- Process scene voiceover ---
        voiceover_info = scene.get("voiceover")
        if voiceover_info and voiceover_info.get("src"):
            vo_path = voiceover_info["src"] # Assuming LOCAL PATH
            vo_volume = voiceover_info.get("volume", 1.0)
            if check_local_file(vo_path):
                try:
                    print(f"  Loading voiceover: {vo_path}")
                    scene_voiceover_clip = AudioFileClip(vo_path)
                    # Trim voiceover if longer than scene visual duration
                    if scene_voiceover_clip.duration > scene_duration:
                        print(f"  Warning: Voiceover for Scene #{i+1} ({scene_voiceover_clip.duration:.2f}s) is longer than scene duration ({scene_duration:.2f}s). Trimming.")
                        scene_voiceover_clip = scene_voiceover_clip.subclip(0, scene_duration)
                    # Apply volume
                    scene_voiceover_clip = scene_voiceover_clip.volumex(vo_volume)
                except Exception as e:
                    print(f"  Error loading voiceover {vo_path}: {e}")
                    scene_voiceover_clip = None # Ensure it's None on error
            else:
                print(f"  Warning: Voiceover file not found for Scene #{i+1}: {vo_path}")

        # --- Store processed data for assembly ---
        transition_info = scene.get('transition')
        processed_elements.append({
            "clip": scene_visual_composite,
            "voiceover_clip": scene_voiceover_clip, # Store the audio clip object or None
            "scene_duration": scene_duration,
            "transition_to_this": transition_info
        })
        print(f"Scene #{i+1} processed. Visual Duration: {scene_duration:.2f}s")

    # --- Error checks after processing all scenes ---
    if not download_success: print("Error: Failed to download one or more visual assets. Aborting."); cleanup_temp(); return
    if not processed_elements: print("Error: No scenes could be processed successfully. Aborting."); cleanup_temp(); return

    # 4. Assemble Visual Clips with Transitions
    print("--- Assembling Video Visuals with Transitions ---")
    final_clips_to_compose = [] # Holds final timed *visual* clips
    current_timeline_pos = 0.0

    for i, element_data in enumerate(processed_elements):
        clip = element_data["clip"]
        transition_info = element_data["transition_to_this"]
        scene_duration = element_data["scene_duration"]
        transition_duration = 0.0
        clip_start_time = current_timeline_pos

        if i > 0 and transition_info:
            transition_duration = transition_info.get("duration", DEFAULT_TRANSITION_DURATION)
            transition_style = transition_info.get("style", "fade")
            print(f"  Applying transition into Scene #{i+1}: '{transition_style}' (duration: {transition_duration:.2f}s) - Approximated as Crossfade")

            # --- Advanced Transition Logic Placeholder ---
            # if transition_style == "wipeup":
            #     # HERE you would implement logic for a wipe using masking
            #     # e.g., create a mask clip that animates, apply with clip.set_mask()
            #     # This is complex and not implemented here.
            #     clip = clip.crossfadein(transition_duration) # Fallback to crossfade
            # elif transition_style == "circleopen":
            #     # HERE you would implement logic for circle open using masking
            #     clip = clip.crossfadein(transition_duration) # Fallback to crossfade
            # else: # Default to crossfade
            #     clip = clip.crossfadein(transition_duration)
            # --- End Placeholder ---

            # Current implementation: Always use crossfade
            clip_start_time -= transition_duration
            clip = clip.crossfadein(transition_duration)

        clip = clip.set_start(clip_start_time)
        final_clips_to_compose.append(clip) # Add the timed visual clip
        current_timeline_pos += scene_duration

    # 5. Create Final Composite Visual Video
    if not final_clips_to_compose: print("Error: No visual clips for final composition."); cleanup_temp(); return
    last_clip = final_clips_to_compose[-1]
    total_duration = last_clip.start + last_clip.duration
    print(f"Total video duration (estimated): {total_duration:.2f}s")
    final_video = CompositeVideoClip(final_clips_to_compose, size=target_resolution).set_duration(total_duration)

    # 6. Prepare and Composite Audio
    print("--- Preparing and Compositing Audio ---")
    all_audio_clips = [] # List to hold background music and timed voiceovers

    # --- Background Music ---
    actual_bg_volume = bg_audio_volume
    if bg_audio_path:
        if check_local_file(bg_audio_path):
            try:
                print(f"  Loading background music: {bg_audio_path}")
                background_audio = AudioFileClip(bg_audio_path)
                # Duck background music slightly if voiceovers are present
                if has_voiceovers:
                    actual_bg_volume *= DUCK_BG_MUSIC_FACTOR
                    print(f"  Ducking background music volume to {actual_bg_volume:.2f}")
                background_audio = background_audio.volumex(actual_bg_volume)

                if background_audio.duration < total_duration:
                    num_loops = math.ceil(total_duration / background_audio.duration)
                    background_audio = concatenate_audioclips([background_audio] * num_loops)
                    print(f"  Looping background audio {num_loops} times.")
                background_audio = background_audio.subclip(0, total_duration)
                background_audio = background_audio.audio_fadein(DEFAULT_AUDIO_FADE_SECONDS).audio_fadeout(DEFAULT_AUDIO_FADE_SECONDS)
                all_audio_clips.append(background_audio) # Add bg music first
            except Exception as e: print(f"  Error loading background music {bg_audio_path}: {e}")
        else: print(f"  Warning: Background music file not found: {bg_audio_path}")

    # --- Scene Voiceovers ---
    # Need the start times from the *composited* visual clips
    for i, element_data in enumerate(processed_elements):
        vo_clip = element_data["voiceover_clip"]
        if vo_clip:
            visual_clip_start_time = final_clips_to_compose[i].start
            # Ensure start time isn't negative (can happen with transitions)
            actual_vo_start_time = max(0, visual_clip_start_time)
            print(f"  Adding voiceover for Scene #{i+1} at time {actual_vo_start_time:.2f}s")
            vo_clip = vo_clip.set_start(actual_vo_start_time)
            all_audio_clips.append(vo_clip)

    # --- Mix all audio ---
    final_combined_audio = None
    if all_audio_clips:
        print("  Compositing final audio track...")
        try:
            final_combined_audio = CompositeAudioClip(all_audio_clips)
            final_video = final_video.set_audio(final_combined_audio)
            print("  Audio composited successfully.")
        except Exception as e:
            print(f"  Error compositing audio: {e}")
            # Continue without audio if mixing fails
            final_video = final_video.set_audio(None) # Ensure no potentially broken audio
    else:
        print("  No audio tracks to add.")
        final_video = final_video.set_audio(None) # Ensure no audio track

    # 7. Write Video File
    print(f"--- Writing Final Video: {output_filename} ---")
    # ... (rest of the writing logic - unchanged)
    try:
        final_video.write_videofile(
            output_filename,
            fps=24, # Explicit FPS
            codec="libx264", audio_codec="aac",
            temp_audiofile=os.path.join(TEMP_ASSET_DIR, 'temp-audio.m4a'),
            remove_temp=True, preset=ffmpeg_preset,
            ffmpeg_params=ffmpeg_extra_params, threads=os.cpu_count(),
            logger='bar'
        )
        print(f"--- Video creation successful: {output_filename} ---")
    except Exception as e:
        print(f"Error writing video file: {e}")
        import traceback
        traceback.print_exc()

    # 8. Cleanup Temporary Files
    finally:
        cleanup_temp()

def cleanup_temp():
    """Cleans up the temporary asset directory."""
    if os.path.exists(TEMP_ASSET_DIR):
        print("--- Cleaning up temporary files ---")
        try:
            shutil.rmtree(TEMP_ASSET_DIR)
        except Exception as e:
            print(f"Warning: Could not remove temp directory {TEMP_ASSET_DIR}: {e}")

# --- Main Execution ---
if __name__ == "__main__":
    json_file_path = "video_script.json"
    output_video_file = "my_generated_video_with_audio.mp4"
    try:
        print(f"Loading script: {json_file_path}")
        with open(json_file_path, 'r') as f:
            video_data = json.load(f)
        create_video_from_json(video_data, output_video_file)
    except FileNotFoundError: print(f"Error: JSON file not found at {json_file_path}")
    except json.JSONDecodeError: print(f"Error: Could not decode JSON from {json_file_path}.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()