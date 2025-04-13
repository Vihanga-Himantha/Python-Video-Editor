import json
import os
import requests
import shutil
import math
from PIL import Image
from moviepy.editor import (ImageClip, concatenate_videoclips, CompositeVideoClip,
                            VideoFileClip, AudioFileClip, TextClip)
from moviepy.audio.AudioClip import concatenate_audioclips, CompositeAudioClip
import traceback # Import traceback for detailed error logging

# --- Configuration ---
TEMP_ASSET_DIR = "temp_video_assets"
DEFAULT_TRANSITION_DURATION = 1.0
DEFAULT_AUDIO_FADE_SECONDS = 1.0
DUCK_BG_MUSIC_FACTOR = 0.5
DEFAULT_ELEMENT_DURATION = 3.0 # Default duration if element/VO duration is missing

# --- Mappings ---
RESOLUTION_MAP = {
    "sd": (640, 480), "hd": (1280, 720), "full-hd": (1920, 1080), "4k": (3840, 2160),
}
QUALITY_MAP = {
    "low": {"preset": "ultrafast", "crf": 28}, "medium": {"preset": "medium", "crf": 23},
    "high": {"preset": "slow", "crf": 18}, "production": {"preset": "veryslow", "crf": 16}
}

# --- Helper Functions ---
# (download_asset, check_local_file, get_ffmpeg_params remain the same)
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

def cleanup_temp():
    """Cleans up the temporary asset directory."""
    if os.path.exists(TEMP_ASSET_DIR):
        print("--- Cleaning up temporary files ---")
        try:
            shutil.rmtree(TEMP_ASSET_DIR)
        except Exception as e:
            print(f"Warning: Could not remove temp directory {TEMP_ASSET_DIR}: {e}")

# --- Main Video Creation Function --- UPDATED ---

def create_video_from_json(json_data, output_filename="output_video.mp4"):
    """
    Creates a video from JSON. Scene duration is determined by voiceover length
    if available, otherwise by the max duration of visual elements.
    """
    global TEMP_ASSET_DIR, DUCK_BG_MUSIC_FACTOR, DEFAULT_ELEMENT_DURATION

    # 1. Parse Global Settings (same as before)
    resolution_str = json_data.get("resolution", "hd")
    quality_str = json_data.get("quality", "medium")
    target_resolution = RESOLUTION_MAP.get(resolution_str, RESOLUTION_MAP["hd"])
    ffmpeg_preset, ffmpeg_extra_params = get_ffmpeg_params(quality_str)
    scenes_data = json_data.get("scenes", [])
    audio_info = json_data.get("audio", {})
    bg_audio_path = audio_info.get("src")
    bg_audio_volume = audio_info.get("volume", 1.0)
    has_any_voiceovers = any(scene.get("voiceover", {}).get("src") for scene in scenes_data) # Check if ducking needed

    if not scenes_data: print("Error: No scenes found."); return

    # 2. Prepare Temporary Directory (same as before)
    if os.path.exists(TEMP_ASSET_DIR): shutil.rmtree(TEMP_ASSET_DIR)
    os.makedirs(TEMP_ASSET_DIR, exist_ok=True)

    # 3. Process Scenes (Visuals and Audio Info - UPDATED LOGIC)
    processed_elements = []
    download_success = True
    print("--- Processing Scenes (Determining Durations) ---")

    for i, scene in enumerate(scenes_data):
        print(f"Processing Scene #{i+1}: {scene.get('comment', '')}")
        scene_elements_data = scene.get("elements", [])
        scene_voiceover_clip = None
        scene_duration = 0 # Will be determined by VO or elements
        voiceover_loaded_successfully = False

        if not scene_elements_data:
            print(f"Warning: Scene #{i+1} has no visual elements. Skipping.")
            continue

        # --- Try loading voiceover FIRST to determine duration ---
        voiceover_info = scene.get("voiceover")
        if voiceover_info and voiceover_info.get("src"):
            vo_path = voiceover_info["src"]
            vo_volume = voiceover_info.get("volume", 1.0)
            if check_local_file(vo_path):
                try:
                    print(f"  Loading voiceover to determine duration: {vo_path}")
                    temp_vo_clip = AudioFileClip(vo_path)
                    scene_duration = temp_vo_clip.duration # *** Set scene duration from VO ***
                    scene_voiceover_clip = temp_vo_clip.volumex(vo_volume) # Apply volume now
                    voiceover_loaded_successfully = True
                    print(f"  Voiceover found. Scene duration set to: {scene_duration:.2f}s")
                except Exception as e:
                    print(f"  Error loading voiceover {vo_path}: {e}. Will use element durations.")
                    scene_voiceover_clip = None # Ensure it's None on error
            else:
                print(f"  Warning: Voiceover file not found: {vo_path}. Will use element durations.")

        # --- If voiceover didn't determine duration, use elements ---
        if not voiceover_loaded_successfully:
            print("  No voiceover found or loaded. Determining duration from visual elements.")
            max_element_duration = 0
            has_any_duration = False
            for element in scene_elements_data:
                e_dur = element.get("duration")
                if e_dur is not None:
                    try:
                        max_element_duration = max(max_element_duration, float(e_dur))
                        has_any_duration = True
                    except ValueError:
                         print(f"Warning: Invalid duration '{e_dur}' in element, ignoring.")

            if not has_any_duration:
                 print(f"Warning: No durations found in elements for Scene #{i+1}. Using default: {DEFAULT_ELEMENT_DURATION}s")
                 scene_duration = DEFAULT_ELEMENT_DURATION
            else:
                 scene_duration = max_element_duration
            print(f"  Scene duration set from elements: {scene_duration:.2f}s")

        # --- Process visual elements using the determined scene_duration ---
        print(f"  Processing visual elements for determined duration: {scene_duration:.2f}s")
        scene_visual_clips = []
        for j, element in enumerate(scene_elements_data):
            element_type = element.get("type")
            element_src = element.get("src")
            # We IGNORE element["duration"] now, using scene_duration instead
            element_text = element.get("text")
            clip = None

            try: # Wrap element processing in try/except
                if element_type == "image" and element_src:
                    asset_filename = f"scene_{i}_elem_{j}_{os.path.basename(element_src)}"
                    local_path = os.path.join(TEMP_ASSET_DIR, asset_filename)
                    if not download_asset(element_src, local_path): download_success = False; continue

                    pil_image = Image.open(local_path)
                    img_ratio = pil_image.size[0] / pil_image.size[1]
                    target_h = target_resolution[1]
                    target_w = int(target_h * img_ratio)
                    if target_w > target_resolution[0]: target_w, target_h = target_resolution[0], int(target_resolution[0] / img_ratio)
                    pil_image = pil_image.resize((target_w, target_h), Image.Resampling.LANCZOS)
                    pil_image.save(local_path)

                    clip = ImageClip(local_path, duration=scene_duration).set_position('center') # Use scene_duration

                elif element_type == "video" and element_src:
                    asset_filename = f"scene_{i}_elem_{j}_{os.path.basename(element_src)}"
                    local_path = os.path.join(TEMP_ASSET_DIR, asset_filename)
                    if not download_asset(element_src, local_path): download_success = False; continue

                    temp_clip = VideoFileClip(local_path, target_resolution=target_resolution)
                    # Trim or use full length up to scene_duration
                    clip_natural_duration = temp_clip.duration
                    final_clip_duration = min(clip_natural_duration, scene_duration)
                    clip = temp_clip.subclip(0, final_clip_duration)

                    # Apply resize after subclip
                    clip = clip.resize(height=target_resolution[1])
                    if clip.w > target_resolution[0]: clip = clip.resize(width=target_resolution[0])
                    clip = clip.set_position('center')
                    # If video is shorter than scene, it will end early. Extending requires looping/freeze frame (not implemented here).
                    if clip_natural_duration < scene_duration:
                         print(f"  Warning: Video element is shorter ({clip_natural_duration:.2f}s) than scene duration ({scene_duration:.2f}s). Video will end early.")
                    # Set the clip duration explicitly for MoviePy's compositor
                    clip = clip.set_duration(scene_duration)


                elif element_type == "text" and element_text:
                    fontsize = element.get("fontsize", 70); font = element.get("font", "Arial")
                    color = element.get("color", "white"); bg_color = element.get("bg_color", "transparent")
                    pos = element.get("position", "center")
                    clip = TextClip(element_text, fontsize=fontsize, font=font, color=color, bg_color=bg_color)
                    clip = clip.set_duration(scene_duration).set_position(pos) # Use scene_duration
                else:
                    print(f"  Warning: Unsupported element type '{element_type}' or missing data. Skipping element.")
                    continue

                if clip: scene_visual_clips.append(clip)

            except Exception as e:
                 print(f"  Error processing element #{j} in Scene #{i+1}: {e}")
                 traceback.print_exc() # Print detailed error
                 continue # Skip this element on error

        # --- Combine visual elements for the scene ---
        scene_visual_composite = None
        if scene_visual_clips:
            # Important: Set composite duration explicitly to scene_duration
            scene_visual_composite = CompositeVideoClip(scene_visual_clips, size=target_resolution).set_duration(scene_duration)
        else:
            print(f"Warning: Scene #{i+1} resulted in no processable visual clips. Skipping scene.")
            continue

        # --- Store processed data for assembly ---
        transition_info = scene.get('transition')
        processed_elements.append({
            "clip": scene_visual_composite,
            "voiceover_clip": scene_voiceover_clip, # Already loaded and volume adjusted
            "scene_duration": scene_duration, # Final determined duration
            "transition_to_this": transition_info
        })
        print(f"Scene #{i+1} processing complete. Final Duration: {scene_duration:.2f}s")


    # --- Error checks after processing all scenes (same) ---
    if not download_success: print("Error: Failed download visual assets."); cleanup_temp(); return
    if not processed_elements: print("Error: No scenes processed."); cleanup_temp(); return

    # 4. Assemble Visual Clips with Transitions (logic mostly same)
    print("--- Assembling Video Visuals with Transitions ---")
    # ... (Transition logic remains the same, using crossfade approximation) ...
    final_clips_to_compose = []
    current_timeline_pos = 0.0
    for i, element_data in enumerate(processed_elements):
        clip = element_data["clip"]
        transition_info = element_data["transition_to_this"]
        scene_duration = element_data["scene_duration"] # Use the final duration
        transition_duration = 0.0
        clip_start_time = current_timeline_pos

        if i > 0 and transition_info:
            transition_duration = transition_info.get("duration", DEFAULT_TRANSITION_DURATION)
            transition_style = transition_info.get("style", "fade")
            print(f"  Applying transition into Scene #{i+1}: '{transition_style}' (duration: {transition_duration:.2f}s) - Approximated as Crossfade")
            # --- Advanced Transition Placeholder ---
            clip_start_time -= transition_duration
            clip = clip.crossfadein(transition_duration)

        clip = clip.set_start(clip_start_time)
        final_clips_to_compose.append(clip)
        current_timeline_pos += scene_duration # Advance timeline by final scene duration

    # 5. Create Final Composite Visual Video (same)
    if not final_clips_to_compose: print("Error: No visual clips for final composition."); cleanup_temp(); return
    last_clip = final_clips_to_compose[-1]
    total_duration = last_clip.start + last_clip.duration
    print(f"Total video duration (estimated): {total_duration:.2f}s")
    final_video = CompositeVideoClip(final_clips_to_compose, size=target_resolution).set_duration(total_duration)


    # 6. Prepare and Composite Audio (logic mostly same, uses pre-loaded VO)
    print("--- Preparing and Compositing Audio ---")
    # ... (Background music loading, ducking, looping/trimming same) ...
    all_audio_clips = []
    actual_bg_volume = bg_audio_volume
    if bg_audio_path:
        if check_local_file(bg_audio_path):
            try:
                print(f"  Loading background music: {bg_audio_path}")
                background_audio = AudioFileClip(bg_audio_path)
                if has_any_voiceovers:
                    actual_bg_volume *= DUCK_BG_MUSIC_FACTOR
                    print(f"  Ducking background music volume to {actual_bg_volume:.2f}")
                background_audio = background_audio.volumex(actual_bg_volume)
                if background_audio.duration < total_duration:
                    num_loops = math.ceil(total_duration / background_audio.duration); print(f"  Looping background audio {num_loops} times.")
                    background_audio = concatenate_audioclips([background_audio] * num_loops)
                background_audio = background_audio.subclip(0, total_duration)
                background_audio = background_audio.audio_fadein(DEFAULT_AUDIO_FADE_SECONDS).audio_fadeout(DEFAULT_AUDIO_FADE_SECONDS)
                all_audio_clips.append(background_audio)
            except Exception as e: print(f"  Error loading background music {bg_audio_path}: {e}")
        else: print(f"  Warning: Background music file not found: {bg_audio_path}")

    # --- Scene Voiceovers (use already loaded clips) ---
    for i, element_data in enumerate(processed_elements):
        vo_clip = element_data["voiceover_clip"] # Get the pre-loaded/volume-adjusted clip
        if vo_clip:
            visual_clip_start_time = final_clips_to_compose[i].start
            actual_vo_start_time = max(0, visual_clip_start_time)
            print(f"  Adding voiceover for Scene #{i+1} at time {actual_vo_start_time:.2f}s")
            vo_clip = vo_clip.set_start(actual_vo_start_time)
            # No need to trim VO here as it already set the scene duration
            all_audio_clips.append(vo_clip)

    # --- Mix all audio (same) ---
    final_combined_audio = None
    if all_audio_clips:
        print("  Compositing final audio track...")
        try:
            final_combined_audio = CompositeAudioClip(all_audio_clips)
            final_video = final_video.set_audio(final_combined_audio)
            print("  Audio composited successfully.")
        except Exception as e:
            print(f"  Error compositing audio: {e}")
            final_video = final_video.set_audio(None)
    else:
        print("  No audio tracks to add.")
        final_video = final_video.set_audio(None)

    # 7. Write Video File (same)
    print(f"--- Writing Final Video: {output_filename} ---")
    # ... (write_videofile call remains the same) ...
    try:
        final_video.write_videofile(
            output_filename, fps=24, codec="libx264", audio_codec="aac",
            temp_audiofile=os.path.join(TEMP_ASSET_DIR, 'temp-audio.m4a'),
            remove_temp=True, preset=ffmpeg_preset, ffmpeg_params=ffmpeg_extra_params,
            threads=os.cpu_count(), logger='bar'
        )
        print(f"--- Video creation successful: {output_filename} ---")
    except Exception as e:
        print(f"Error writing video file: {e}")
        traceback.print_exc()

    # 8. Cleanup Temporary Files (same)
    finally:
        cleanup_temp()

# --- Main Execution (same) ---
if __name__ == "__main__":
    json_file_path = "video_script.json" # Use your updated JSON file
    output_video_file = "my_generated_video_vo_duration.mp4"
    try:
        print(f"Loading script: {json_file_path}")
        with open(json_file_path, 'r') as f:
            video_data = json.load(f)
        create_video_from_json(video_data, output_video_file)
    except FileNotFoundError: print(f"Error: JSON file not found at {json_file_path}")
    except json.JSONDecodeError: print(f"Error: Could not decode JSON from {json_file_path}.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        traceback.print_exc()