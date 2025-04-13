import json
import os
import requests
import shutil
import math
from moviepy.editor import (ImageClip, concatenate_videoclips, CompositeVideoClip,
                          VideoFileClip, AudioFileClip, TextClip)  # Import necessary classes
from moviepy.audio.AudioClip import concatenate_audioclips

# --- Configuration ---
TEMP_ASSET_DIR = "temp_video_assets"
DEFAULT_TRANSITION_DURATION = 1.0 # Default duration if not specified
DEFAULT_AUDIO_FADE_SECONDS = 1 # Fade audio in/out duration

# --- Mappings ---
# Map resolution strings to (width, height) tuples
RESOLUTION_MAP = {
    "sd": (640, 480),
    "hd": (1280, 720),
    "full-hd": (1920, 1080),
    "4k": (3840, 2160),
}

# Map quality strings loosely to FFmpeg presets and Constant Rate Factor (CRF)
# Lower CRF = higher quality, larger file size. Presets affect encoding speed vs compression.
# See: https://trac.ffmpeg.org/wiki/Encode/H.264
QUALITY_MAP = {
    "low": {"preset": "ultrafast", "crf": 28},
    "medium": {"preset": "medium", "crf": 23},
    "high": {"preset": "slow", "crf": 18},
    "production": {"preset": "veryslow", "crf": 16} # Example for very high quality
}

# --- Helper Functions ---

def download_asset(url, download_path):
    """Downloads a file from a URL to a specified path."""
    try:
        response = requests.get(url, stream=True, timeout=30) # Added timeout
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        with open(download_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Downloaded asset: {url} to {download_path}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error downloading {url}: {e}")
        return False
    except Exception as e:
        print(f"Error saving file {download_path}: {e}")
        return False

def get_ffmpeg_params(quality_str):
    """Gets FFmpeg preset and crf based on quality string."""
    quality_settings = QUALITY_MAP.get(quality_str, QUALITY_MAP["medium"]) # Default to medium
    # Return as a list suitable for ffmpeg_params
    # Note: MoviePy's preset maps directly, but CRF needs specific ffmpeg_params
    return quality_settings['preset'], ["-crf", str(quality_settings['crf'])]


# --- Main Video Creation Function ---

def create_video_from_json(json_data, output_filename="output_video.mp4"):
    """
    Creates a video from a JSON definition using MoviePy.

    Args:
        json_data (dict): The parsed JSON data defining the video.
        output_filename (str): The name of the output video file.
    """
    global TEMP_ASSET_DIR

    # 1. Parse Global Settings
    resolution_str = json_data.get("resolution", "hd") # Default to HD
    quality_str = json_data.get("quality", "medium") # Default to medium
    target_resolution = RESOLUTION_MAP.get(resolution_str, RESOLUTION_MAP["hd"])
    ffmpeg_preset, ffmpeg_extra_params = get_ffmpeg_params(quality_str)
    scenes_data = json_data.get("scenes", [])
    bg_audio_path = json_data.get("audio", {}).get("src")
    bg_audio_volume = json_data.get("audio", {}).get("volume", 1.0) # Default volume is 100%

    if not scenes_data:
        print("Error: No scenes found in JSON data.")
        return

    # 2. Prepare Temporary Directory for Assets
    if os.path.exists(TEMP_ASSET_DIR):
        shutil.rmtree(TEMP_ASSET_DIR) # Clear previous temp data
    os.makedirs(TEMP_ASSET_DIR, exist_ok=True)

    # 3. Process Scenes and Download Assets
    processed_elements = [] # List to hold processed MoviePy clips and their timing info
    total_estimated_duration = 0
    download_success = True

    print("--- Processing Scenes ---")
    for i, scene in enumerate(scenes_data):
        print(f"Processing Scene #{i+1}: {scene.get('comment', '')}")
        scene_elements = scene.get("elements", [])
        scene_clips = [] # Clips within this scene (e.g., image + text overlay)

        if not scene_elements:
            print(f"Warning: Scene #{i+1} has no elements. Skipping.")
            continue

        # --- Process elements within the scene ---
        scene_duration = 0
        for j, element in enumerate(scene_elements):
            element_type = element.get("type")
            element_src = element.get("src")
            element_duration = element.get("duration")
            element_text = element.get("text") # For text type

            clip = None

            if element_type == "image" and element_src and element_duration:
                asset_filename = os.path.basename(element_src)
                # Avoid collisions if multiple scenes use same filename
                local_path = os.path.join(TEMP_ASSET_DIR, f"scene_{i}_elem_{j}_{asset_filename}")

                if not download_asset(element_src, local_path):
                    download_success = False
                    continue # Skip this element if download failed

                try:
                    # Use pillow's Image to load and resize first to handle the ANTIALIAS issue
                    from PIL import Image
                    pil_image = Image.open(local_path)
                    # Calculate new dimensions while maintaining aspect ratio
                    img_ratio = pil_image.size[0] / pil_image.size[1]
                    target_height = target_resolution[1]
                    target_width = int(target_height * img_ratio)
                    if target_width > target_resolution[0]:
                        target_width = target_resolution[0]
                        target_height = int(target_width / img_ratio)
                    # Use Lanczos resampling (replacement for ANTIALIAS)
                    pil_image = pil_image.resize((target_width, target_height), Image.Resampling.LANCZOS)
                    pil_image.save(local_path)
                    
                    clip = ImageClip(local_path, duration=element_duration)
                    clip = clip.set_position('center')
                    scene_duration = max(scene_duration, element_duration)
                except Exception as e:
                    print(f"Error processing image {local_path}: {e}")
                    continue

            elif element_type == "video" and element_src:
                # --- Basic Video Element Handling (Example) ---
                asset_filename = os.path.basename(element_src)
                local_path = os.path.join(TEMP_ASSET_DIR, f"scene_{i}_elem_{j}_{asset_filename}")
                if not download_asset(element_src, local_path):
                    download_success = False
                    continue
                try:
                    clip = VideoFileClip(local_path, target_resolution=target_resolution)
                    if element_duration: # Allow overriding duration or trimming
                        clip = clip.subclip(0, element_duration)
                    else:
                        element_duration = clip.duration # Use video's own duration if not specified

                    clip = clip.resize(height=target_resolution[1])
                    if clip.w > target_resolution[0]:
                         clip = clip.resize(width=target_resolution[0])
                    clip = clip.set_position('center')

                    scene_duration = max(scene_duration, element_duration)
                except Exception as e:
                    print(f"Error processing video {local_path}: {e}")
                    continue

            elif element_type == "text" and element_text and element_duration:
                 # --- Basic Text Element Handling (Example) ---
                 fontsize = element.get("fontsize", 70)
                 font = element.get("font", "Arial") # Ensure font is available on system
                 color = element.get("color", "white")
                 bg_color = element.get("bg_color", "transparent")
                 pos = element.get("position", "center") # e.g., 'center', ('center', 50), (100, 100)

                 try:
                    clip = TextClip(element_text, fontsize=fontsize, font=font, color=color, bg_color=bg_color)
                    clip = clip.set_duration(element_duration).set_position(pos)
                    scene_duration = max(scene_duration, element_duration)
                 except Exception as e:
                     print(f"Error creating text clip: {e}")
                     continue # Skip this element

            else:
                 print(f"Warning: Unsupported element type '{element_type}' or missing data in Scene #{i+1}. Skipping.")
                 continue

            if clip:
                scene_clips.append(clip)

        # --- Combine elements for the scene ---
        if scene_clips:
            # If multiple clips (e.g., text on image), composite them
            # Set the duration of the composite scene clip
            scene_composite_clip = CompositeVideoClip(scene_clips, size=target_resolution).set_duration(scene_duration)

            transition_info = scene.get('transition')
            processed_elements.append({
                "clip": scene_composite_clip,
                "transition_to_this": transition_info, # The transition DEFINED IN THIS scene leads INTO it
                "scene_duration": scene_duration # Store original duration before transitions
            })
            print(f"Scene #{i+1} processed. Duration: {scene_duration:.2f}s")
        else:
             print(f"Warning: Scene #{i+1} resulted in no processable clips.")


    if not download_success:
        print("Error: Failed to download one or more assets. Aborting video creation.")
        # Clean up temporary files even on failure
        if os.path.exists(TEMP_ASSET_DIR):
            shutil.rmtree(TEMP_ASSET_DIR)
        return

    if not processed_elements:
        print("Error: No scenes could be processed successfully. Aborting.")
        # Clean up temporary files even on failure
        if os.path.exists(TEMP_ASSET_DIR):
            shutil.rmtree(TEMP_ASSET_DIR)
        return

    # 4. Assemble Clips with Transitions (Using Crossfade as Placeholder)
    print("--- Assembling Video with Transitions ---")
    final_clips_to_compose = []
    current_timeline_pos = 0.0

    for i, element_data in enumerate(processed_elements):
        clip = element_data["clip"]
        transition_info = element_data["transition_to_this"]
        scene_duration = element_data["scene_duration"] # Original duration
        transition_duration = 0.0

        clip_start_time = current_timeline_pos

        if i > 0 and transition_info: # Apply transition *into* this clip (from previous)
            transition_duration = transition_info.get("duration", DEFAULT_TRANSITION_DURATION)
            transition_style = transition_info.get("style", "fade") # Default to fade if style missing

            # *** IMPORTANT LIMITATION ***
            # MoviePy doesn't have built-in named transitions like 'wipeup', 'circleopen'.
            # We are approximating ALL transitions using crossfadein.
            # Implementing specific wipes/circles requires advanced masking or FFmpeg filters.
            print(f"  Applying transition into Scene #{i+1}: '{transition_style}' (duration: {transition_duration:.2f}s) - Approximated as Crossfade")

            # Overlap clips for the transition
            clip_start_time -= transition_duration
            # Apply the fade-in effect to the current clip over the transition duration
            clip = clip.crossfadein(transition_duration)

        # Set the start time of the clip on the timeline
        clip = clip.set_start(clip_start_time)
        final_clips_to_compose.append(clip)

        # Update the timeline position for the *next* clip's start
        # The next clip starts after this scene's original duration, MINUS the overlap time
        current_timeline_pos += scene_duration # Add original duration
        if i > 0:
            pass # The start time calculation `clip_start_time -= transition_duration` handles the overlap correctly

    # 5. Create Final Composite Video
    if not final_clips_to_compose:
        print("Error: No clips available for final composition.")
        # Clean up temporary files
        if os.path.exists(TEMP_ASSET_DIR):
            shutil.rmtree(TEMP_ASSET_DIR)
        return

    # Calculate total duration based on the last clip's start time and its duration
    last_clip = final_clips_to_compose[-1]
    total_duration = last_clip.start + last_clip.duration

    print(f"Total video duration (estimated): {total_duration:.2f}s")
    final_video = CompositeVideoClip(final_clips_to_compose, size=target_resolution)
    final_video = final_video.set_duration(total_duration) # Set exact duration

    # 6. Add Background Audio (Optional)
    final_audio = None
    if bg_audio_path:
        print(f"--- Adding Background Audio: {bg_audio_path} ---")
        audio_local_path = os.path.join(TEMP_ASSET_DIR, os.path.basename(bg_audio_path))
        if download_asset(bg_audio_path, audio_local_path):
            try:
                background_audio = AudioFileClip(audio_local_path)
                # Adjust volume
                background_audio = background_audio.volumex(bg_audio_volume)

                # Loop or cut audio to match video duration
                if background_audio.duration < total_duration:
                    # Loop the audio - calculate how many loops needed
                    num_loops = math.ceil(total_duration / background_audio.duration)
                    background_audio = concatenate_audioclips([background_audio] * num_loops)
                    print(f"Looping audio {num_loops} times.")
                # Trim audio if it's longer than video
                final_audio = background_audio.subclip(0, total_duration)
                # Add fade in/out to audio
                final_audio = final_audio.audio_fadein(DEFAULT_AUDIO_FADE_SECONDS).audio_fadeout(DEFAULT_AUDIO_FADE_SECONDS)

                final_video = final_video.set_audio(final_audio)
                print("Background audio added successfully.")
            except Exception as e:
                print(f"Error processing background audio {audio_local_path}: {e}")
                # Continue without audio if it fails
        else:
            print("Failed to download background audio. Continuing without it.")


    # 7. Write Video File
    print(f"--- Writing Final Video: {output_filename} ---")
    print(f"Resolution: {target_resolution[0]}x{target_resolution[1]} ({resolution_str})")
    print(f"Quality: {quality_str} (Preset: {ffmpeg_preset}, Params: {ffmpeg_extra_params})")
    try:
        final_video.write_videofile(
            output_filename,
            fps=24,  # Standard video frame rate
            codec="libx264", # Common, good quality codec
            audio_codec="aac", # Common audio codec
            temp_audiofile=os.path.join(TEMP_ASSET_DIR, 'temp-audio.m4a'), # Temp file for audio processing
            remove_temp=True,
            preset=ffmpeg_preset,
            ffmpeg_params=ffmpeg_extra_params,
            threads=os.cpu_count(), # Use available CPU cores
            logger='bar' # Show progress bar
            # verbose=True # Uncomment for more detailed FFmpeg output
        )
        print(f"--- Video creation successful: {output_filename} ---")
    except Exception as e:
        print(f"Error writing video file: {e}")
        # Log the full traceback for debugging
        import traceback
        traceback.print_exc()

    # 8. Cleanup Temporary Files
    finally: # Ensure cleanup happens even if write_videofile fails
        if os.path.exists(TEMP_ASSET_DIR):
            print("--- Cleaning up temporary files ---")
            shutil.rmtree(TEMP_ASSET_DIR)


# --- Main Execution ---
if __name__ == "__main__":
    json_file_path = "video_script.json"
    output_video_file = "my_generated_video.mp4"

    try:
        with open(json_file_path, 'r') as f:
            video_data = json.load(f)

        create_video_from_json(video_data, output_video_file)

    except FileNotFoundError:
        print(f"Error: JSON file not found at {json_file_path}")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {json_file_path}. Check its format.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()