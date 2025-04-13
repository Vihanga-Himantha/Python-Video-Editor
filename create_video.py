import json
import os
import requests
import shutil
import math
import hashlib
import traceback
import re # Import regex
import mimetypes # For inferring extension from Content-Type
from urllib.parse import urlparse, unquote # For robust URL parsing
from PIL import Image # Keep PIL for potential future use, though TextClip often uses ImageMagick
import moviepy.config as mp_config
import numpy as np

# Fix PIL resize filter for newer versions
def get_resize_filter():
    if hasattr(Image, 'Resampling'):
        return Image.Resampling.LANCZOS
    if hasattr(Image, 'LANCZOS'):
        return Image.LANCZOS
    return Image.ANTIALIAS

# Configure MoviePy to use ImageMagick with proper parameters for text rendering
if os.name == 'nt':  # Windows
    mp_config.change_settings({
        "IMAGEMAGICK_BINARY": "magick",
    })

# Override MoviePy's resizer function
def new_resizer(pic, newsize):
    """Resize picture to new size using LANCZOS resampling"""
    newsize = list(map(int, newsize))[::-1]  # Convert to ints and flip w,h to h,w
    
    # Convert to PIL Image if needed
    if isinstance(pic, np.ndarray):
        pilim = Image.fromarray(pic.astype('uint8'))
    elif isinstance(pic, Image.Image):
        pilim = pic
    else:
        # For clips that don't have shape attribute, get their frame
        if hasattr(pic, 'get_frame'):
            frame = pic.get_frame(0)
            if isinstance(frame, np.ndarray):
                pilim = Image.fromarray(frame.astype('uint8'))
            else:
                raise ValueError("Cannot convert frame to PIL Image")
        else:
            raise ValueError("Cannot convert input to PIL Image")

    # Perform the resize
    resized_pil = pilim.resize(newsize, get_resize_filter())
    
    # Convert back to numpy array
    return np.array(resized_pil)

# --- MoviePy Imports ---
from moviepy.editor import (
    VideoClip, ImageClip, TextClip, VideoFileClip, AudioFileClip,
    CompositeVideoClip, CompositeAudioClip, concatenate_videoclips
)
from moviepy.audio.AudioClip import concatenate_audioclips
from moviepy.video.fx.all import resize as moviepy_resize
from moviepy.video.fx.all import rotate as moviepy_rotate

# Apply the patch to MoviePy's resize module
import moviepy.video.fx.resize as resize_module
resize_module.resizer = new_resizer

# --- Configuration ---
TEMP_ASSET_DIR = "temp_video_assets_adv"
CACHE_DIR = "asset_cache" # Cache directory for downloads
DEFAULT_TRANSITION_DURATION = 1.0
DEFAULT_AUDIO_FADE_SECONDS = 1.0
DUCK_BG_MUSIC_FACTOR = 0.5
DEFAULT_ELEMENT_DURATION = 3.0 # Default duration if element/VO duration is missing
DEFAULT_Z_INDEX = 0

# --- Mappings ---
RESOLUTION_MAP = {
    "sd": (640, 480), "hd": (1280, 720), "full-hd": (1920, 1080), "4k": (3840, 2160),
}
QUALITY_MAP = {
    "low": {"preset": "ultrafast", "crf": 28}, "medium": {"preset": "medium", "crf": 23},
    "high": {"preset": "slow", "crf": 18}, "production": {"preset": "veryslow", "crf": 16}
}
# Moviepy position keywords mapping
POSITION_MAP = {
    "center": ("center", "center"), "top": ("center", "top"), "bottom": ("center", "bottom"),
    "left": ("left", "center"), "right": ("right", "center"),
    "top_left": ("left", "top"), "top_right": ("right", "top"),
    "bottom_left": ("left", "bottom"), "bottom_right": ("right", "bottom"),
}

# --- Helper Functions ---

def cleanup_temp():
    """Cleans up the temporary asset directory."""
    if os.path.exists(TEMP_ASSET_DIR):
        print("--- Cleaning up temporary files ---")
        try:
            shutil.rmtree(TEMP_ASSET_DIR)
        except Exception as e:
            print(f"Warning: Could not remove temp directory {TEMP_ASSET_DIR}: {e}")

def check_local_file(path):
    """Checks if a file exists locally."""
    return os.path.isfile(path)

def sanitize_filename(filename):
    """Removes or replaces characters invalid for common file systems."""
    # Remove characters that are explicitly invalid on Windows & often problematic elsewhere
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Remove control characters (0-31)
    filename = re.sub(r'[\x00-\x1f]', '', filename)
    # Replace sequences of dots with a single dot (but not file extension dot)
    name_part, ext_part = os.path.splitext(filename)
    name_part = re.sub(r'\.+', '.', name_part) # Replace dots only in name part
    filename = name_part + ext_part
    # Remove leading/trailing whitespace, dots, and underscores
    filename = filename.strip('. _')
    # Limit filename length (OS limits vary, be conservative)
    max_len = 100
    if len(filename) > max_len:
         name_part, ext_part = os.path.splitext(filename)
         # Truncate the name part to fit within max_len, preserving extension
         name_part = name_part[:max_len - len(ext_part) - 1] # -1 for the dot
         filename = name_part + ext_part
    # Ensure filename is not empty after sanitization
    if not filename or filename == os.path.splitext(filename)[1]: # Check if only extension left
        filename = f"sanitized_{hashlib.md5(filename.encode()).hexdigest()[:8]}{os.path.splitext(filename)[1]}"

    return filename

def get_cache_filename(url):
    """Generates a sanitized cache filename based on the URL hash and path."""
    try:
        parsed_url = urlparse(url)
        # Get the path part and decode URL encoding (e.g., %20 -> space)
        path_part = unquote(parsed_url.path)
        # Extract the base filename from the path
        base_filename = os.path.basename(path_part) if path_part and os.path.basename(path_part) else "downloaded_asset"

        # Get the extension
        _, ext = os.path.splitext(base_filename)
        if not ext or len(ext) > 5 : # Basic check for valid extension
             ext = ".cache" # Use default if no/invalid extension

        # Generate hash from the full URL for uniqueness
        url_bytes = url.encode('utf-8')
        hash_hex = hashlib.sha256(url_bytes).hexdigest()

        # Create a sanitized filename using the *original* base name (truncated) + hash + extension
        # Remove extension before sanitizing name part to avoid affecting it
        sanitized_base = sanitize_filename(base_filename[:-len(ext)] if ext else base_filename)

        # Combine name snippet (max 30 chars), hash snippet, and extension
        final_filename = f"{sanitized_base[:30]}_{hash_hex[:10]}{ext}"
        # Sanitize the final combined name again just in case combination created issues
        return sanitize_filename(final_filename)

    except Exception as e:
        print(f"Warning: Error parsing URL '{url}' for cache filename: {e}")
        # Fallback to pure hash if parsing fails badly
        url_bytes = url.encode('utf-8')
        hash_hex = hashlib.sha256(url_bytes).hexdigest()
        return f"{hash_hex[:16]}.cache" # Simple hash-based fallback


def download_or_get_from_cache(url, cache_dir, temp_dir):
    """
    Downloads asset if not in cache, otherwise copies from cache.
    Returns the path to the asset in the temp directory, or None on failure.
    """
    os.makedirs(cache_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)

    # Check if it's a local file path
    if os.path.exists(url):
        # For local files, just copy directly to temp dir with a unique name
        filename = os.path.basename(url)
        temp_path = os.path.join(temp_dir, f"temp_{filename}")
        try:
            shutil.copy2(url, temp_path)
            return temp_path
        except Exception as e:
            print(f"Error copying local file '{url}' to '{temp_path}': {repr(e)}")
            return None

    # Handle remote URLs
    cache_filename = get_cache_filename(url)
    if not cache_filename:
        print(f"Error: Could not generate a valid cache filename for URL: {url}")
        return None
    cache_path = os.path.join(cache_dir, cache_filename)
    temp_path = os.path.join(temp_dir, f"temp_{cache_filename}")

    if os.path.exists(cache_path):
        print(f"Cache hit: Using cached asset '{cache_filename}' for {url}")
        try:
            shutil.copy2(cache_path, temp_path)
            return temp_path
        except Exception as e:
            print(f"Error copying from cache '{cache_path}' to '{temp_path}': {repr(e)}")
            return None

    print(f"Cache miss: Attempting to download: {url} to cache file: '{cache_filename}'")
    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()

        # Try to get extension from Content-Type header if using default
        _, current_ext = os.path.splitext(cache_filename)
        if current_ext == '.cache':
            content_type = response.headers.get('Content-Type')
            if content_type:
                inferred_ext = mimetypes.guess_extension(content_type.split(';')[0].strip())
                if inferred_ext and inferred_ext != '.cache':
                    new_cache_filename = cache_filename.replace('.cache', inferred_ext)
                    new_cache_path = os.path.join(cache_dir, new_cache_filename)
                    print(f"  (Inferred extension '{inferred_ext}', updating cache filename to '{new_cache_filename}')")
                    cache_filename = new_cache_filename
                    cache_path = new_cache_path
                    temp_path = os.path.join(temp_dir, f"temp_{cache_filename}")

        with open(cache_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Downloaded asset successfully to cache: {cache_filename}")
        shutil.copy2(cache_path, temp_path)
        return temp_path
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        if os.path.exists(cache_path):
            try:
                os.remove(cache_path)
            except Exception as rm_err:
                print(f"Warning: Could not remove incomplete cache file {cache_path}: {rm_err}")
        return None


def get_ffmpeg_params(quality_str):
    """Gets FFmpeg preset and crf based on quality string."""
    quality_settings = QUALITY_MAP.get(quality_str, QUALITY_MAP["medium"])
    return quality_settings['preset'], ["-crf", str(quality_settings['crf'])]

def parse_value(value, reference):
    """Parses percentage or pixel values."""
    if isinstance(value, str) and value.endswith('%'):
        try:
            percent = float(value[:-1])
            return reference * percent / 100.0
        except ValueError:
            return None # Invalid percentage
    try:
        # Allow float values for pixels too, then convert to int later if needed
        return float(value)
    except (ValueError, TypeError):
        return None # Invalid value


def parse_size(size_data, video_size):
    """ Parses size object ({ "width": "50%" } or { "height": 300 }) into MoviePy args. """
    if not isinstance(size_data, dict): return {}

    args = {}
    vid_w, vid_h = video_size

    width = size_data.get("width")
    height = size_data.get("height")

    parsed_w = parse_value(width, vid_w) if width is not None else None
    parsed_h = parse_value(height, vid_h) if height is not None else None

    if parsed_w is not None and parsed_h is not None:
        args['width'] = int(parsed_w)
        args['height'] = int(parsed_h)
    elif parsed_w is not None:
        args['width'] = int(parsed_w)
    elif parsed_h is not None:
        args['height'] = int(parsed_h)
    # Handle case where neither is specified? Return empty dict is fine.
    return args

def parse_position(pos_data, video_size, element_size, align=None):
    """ Parses position object/string into MoviePy coordinates. Handles alignment. """
    vid_w, vid_h = video_size
    elem_w, elem_h = element_size
    # Default alignment is center if not specified or invalid
    align_h, align_v = POSITION_MAP.get(align, ("center", "center"))

    # --- Calculate base coordinates (intended anchor point on the video frame) ---
    x, y = None, None # Initialize

    if isinstance(pos_data, str) and pos_data in POSITION_MAP:
        # Handle keywords like "center", "top_left" etc.
        target_align_h, target_align_v = POSITION_MAP[pos_data]

        if target_align_h == 'left':   x = 0.0
        elif target_align_h == 'right':  x = float(vid_w)
        else: x = vid_w / 2.0 # center

        if target_align_v == 'top':    y = 0.0
        elif target_align_v == 'bottom': y = float(vid_h)
        else: y = vid_h / 2.0 # center

    elif isinstance(pos_data, (list, tuple)) and len(pos_data) == 2:
        # Handle [x, y] values (pixels or percentages relative to video frame)
        x_val, y_val = pos_data
        x = parse_value(x_val, vid_w)
        y = parse_value(y_val, vid_h)
        if x is None or y is None:
            print(f"Warning: Invalid position value found in {pos_data}. Defaulting to center.")
            x, y = vid_w / 2.0, vid_h / 2.0 # Fallback on error

    else:
        # Default to center if format is invalid or not provided
        print(f"Warning: Invalid or missing position data '{pos_data}'. Defaulting to center.")
        x, y = vid_w / 2.0, vid_h / 2.0

    # --- Adjust coordinates based on the element's *own* alignment anchor ---
    # Adjust x based on horizontal alignment of the element itself
    if align_h == 'left':   final_x = x
    elif align_h == 'right':  final_x = x - elem_w
    else: final_x = x - elem_w / 2.0 # center

    # Adjust y based on vertical alignment of the element itself
    if align_v == 'top':    final_y = y
    elif align_v == 'bottom': final_y = y - elem_h
    else: final_y = y - elem_h / 2.0 # center

    return (final_x, final_y)


def lerp(start, end, t):
    """Linear interpolation."""
    # Clamp t to ensure it's between 0 and 1
    t = max(0.0, min(1.0, t))
    return start + (end - start) * t

# --- TTS Placeholder ---
def generate_tts_audio(tts_data, output_dir):
    """
    *** PLACEHOLDER ***
    Generates audio file from text using TTS.
    Replace this with actual TTS library/API calls.
    Requires installing the chosen TTS library (e.g., `pip install gTTS`).
    """
    text = tts_data.get("text", "Missing text for TTS.")
    lang = tts_data.get("language", "en")
    # voice = tts_data.get("voice") # Specific voice model if supported by your TTS

    print(f"--- TTS Generation (Placeholder) ---")
    print(f"Text: {text[:50]}...") # Print snippet
    print(f"Lang: {lang}")
    print("--- NOTE: Attempting TTS generation using gTTS (requires installation) ---")
    print("--- If this fails, check installation and internet connection, ---")
    print("--- or replace this function with your preferred TTS method. ---")

    # --- Example using gTTS (Install with: pip install gTTS) ---
    try:
        from gtts import gTTS
        # Use a hash of the text for a semi-unique filename
        filename_base = f"tts_{hashlib.md5(text.encode()).hexdigest()[:10]}"
        filename = sanitize_filename(f"{filename_base}.mp3")
        filepath = os.path.join(output_dir, filename)

        if os.path.exists(filepath):
            print(f"TTS audio already exists (likely from previous failed run): {filepath}")
            return filepath

        print(f"Attempting gTTS generation to: {filepath}")
        tts = gTTS(text=text, lang=lang, slow=False) # slow=False for normal speed
        tts.save(filepath)
        print("gTTS generation successful.")
        return filepath
    except ImportError:
        print("*** ERROR: gTTS library not found. Cannot generate TTS audio. ***")
        print("*** Please install it: pip install gTTS ***")
        return None
    except Exception as e:
        print(f"*** Error during gTTS generation: {e} ***")
        # Attempt to clean up partial file if save failed
        if 'filepath' in locals() and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception as rm_err:
                print(f"Warning: Could not remove partially generated TTS file {filepath}: {rm_err}")
        return None
    # --- End Example ---


def fl_image_safe(clip, image_func):
    """Safe version of fl_image that works with any clip type"""
    def new_make_frame(t):
        frame = clip.get_frame(t)
        return image_func(frame)
    return clip.set_make_frame(new_make_frame)

def create_animation_func(clip_to_animate, start_state, end_state, anim_duration, video_size):
    """Creates an animation function for a clip based on start/end states."""
    # Parse start and end states
    start_size_args = parse_size(start_state.get("size", {}), video_size)
    end_size_args = parse_size(end_state.get("size", {}), video_size)

    # Get initial size without using shape attribute
    initial_size = (clip_to_animate.w, clip_to_animate.h)
    
    # Calculate start and end sizes
    if start_size_args:
        temp_start = moviepy_resize(clip_to_animate, **start_size_args)
        start_elem_size = (temp_start.w, temp_start.h)
        temp_start.close()
    else:
        start_elem_size = initial_size

    if end_size_args:
        temp_end = moviepy_resize(clip_to_animate, **end_size_args)
        end_elem_size = (temp_end.w, temp_end.h)
        temp_end.close()
    else:
        end_elem_size = initial_size

    # Parse positions with correct element sizes
    start_pos = parse_position(start_state.get("position"), video_size, start_elem_size, start_state.get("align"))
    end_pos = parse_position(end_state.get("position"), video_size, end_elem_size, end_state.get("align"))

    def animate_frame(t):
        """Frame-by-frame animation function."""
        progress = t / anim_duration if anim_duration > 0 else 1.0
        progress = max(0.0, min(1.0, progress))  # Clamp between 0 and 1
        
        # Create a copy of the clip to avoid modifying the original
        styled_clip = clip_to_animate.copy()

        # Size animation
        if start_size_args or end_size_args:
            # Interpolate size args
            interp_size_args = {}
            if "width" in (start_size_args or {}) or "width" in (end_size_args or {}):
                start_w = start_size_args.get("width", styled_clip.w)
                end_w = end_size_args.get("width", styled_clip.w)
                interp_size_args["width"] = lerp(start_w, end_w, progress)
            if "height" in (start_size_args or {}) or "height" in (end_size_args or {}):
                start_h = start_size_args.get("height", styled_clip.h)
                end_h = end_size_args.get("height", styled_clip.h)
                interp_size_args["height"] = lerp(start_h, end_h, progress)
            if interp_size_args:
                styled_clip = moviepy_resize(styled_clip, **interp_size_args)

        # Position animation
        if start_pos and end_pos:
            pos_x = lerp(start_pos[0], end_pos[0], progress)
            pos_y = lerp(start_pos[1], end_pos[1], progress)
            styled_clip = styled_clip.set_position((pos_x, pos_y))
        elif start_pos:  # Only start position
            styled_clip = styled_clip.set_position(start_pos)
        elif end_pos:    # Only end position
            styled_clip = styled_clip.set_position(end_pos)

        return styled_clip

    return animate_frame


# --- Main Video Creation Function ---

def create_video_from_json(json_data, output_filename="output_video_adv.mp4"):
    """Creates a video from JSON, including advanced positioning, styling,
    basic animation, layering, TTS placeholder, and caching."""
    global TEMP_ASSET_DIR, CACHE_DIR, DUCK_BG_MUSIC_FACTOR, DEFAULT_ELEMENT_DURATION

    # 1. Parse Global Settings
    resolution_str = json_data.get("resolution", "hd")
    quality_str = json_data.get("quality", "medium")
    target_resolution = RESOLUTION_MAP.get(resolution_str, RESOLUTION_MAP["hd"])
    ffmpeg_preset, ffmpeg_extra_params = get_ffmpeg_params(quality_str)
    scenes_data = json_data.get("scenes", [])
    audio_info = json_data.get("audio", {})
    bg_audio_path = audio_info.get("src")
    bg_audio_volume = audio_info.get("volume", 1.0)
    # Check if ducking needed - considers both src and tts fields
    has_any_voiceovers = any(scene.get("voiceover", {}).get("src") or scene.get("voiceover", {}).get("tts") for scene in scenes_data)

    if not scenes_data: print("Error: No scenes found."); return

    # 2. Prepare Directories
    # Clear temp dir at start
    if os.path.exists(TEMP_ASSET_DIR):
        try:
            shutil.rmtree(TEMP_ASSET_DIR)
            print(f"Cleaned previous temp directory: {TEMP_ASSET_DIR}")
        except Exception as e:
            print(f"Warning: Could not remove previous temp directory {TEMP_ASSET_DIR}: {e}")
            print("Attempting to continue...")
    try:
        os.makedirs(TEMP_ASSET_DIR, exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True) # Ensure cache dir exists
    except OSError as e:
        print(f"*** CRITICAL ERROR: Could not create required directories: {e} ***")
        return # Cannot proceed without directories


    # 3. Process Scenes (Determine Duration, Handle TTS, Process Elements)
    processed_scenes = [] # Store successfully processed scene data
    download_issues = False # Track if any non-critical download/cache issues occurred
    total_video_duration_estimate = 0 # Keep track for BG audio duration estimate

    print("--- Processing Scenes ---")
    for i, scene in enumerate(scenes_data):
        print(f"\nProcessing Scene #{i+1}: {scene.get('comment', '')}")
        scene_elements_data = scene.get("elements", [])
        scene_voiceover_clip = None
        scene_duration = 0
        voiceover_loaded_successfully = False
        determined_by = "default" # Track how duration was set
        scene_processing_error = False # Flag for errors within this scene

        # Skip scene immediately if it has no visual elements defined
        if not scene_elements_data:
            print(f"Warning: Scene #{i+1} has no 'elements' array defined or it's empty. Skipping scene.")
            continue

        # --- Handle Voiceover (TTS or File) & Determine Scene Duration ---
        voiceover_info = scene.get("voiceover")
        actual_vo_path = None # Path to the final audio file to use
        if voiceover_info:
            vo_src = voiceover_info.get("src")
            vo_tts = voiceover_info.get("tts")
            vo_volume = voiceover_info.get("volume", 1.0)

            if vo_tts:
                print("  Voiceover TTS data found.")
                # Call TTS generation function
                generated_path = generate_tts_audio(vo_tts, TEMP_ASSET_DIR)
                if generated_path and check_local_file(generated_path):
                     actual_vo_path = generated_path
                     print(f"  Using generated TTS audio: {os.path.basename(actual_vo_path)}")
                else:
                     print("  TTS generation failed or returned invalid/missing path. Skipping voiceover for duration calculation.")
                     # Potentially flag error if TTS was the *only* source? Depends on desired behavior.
            elif vo_src:
                 if check_local_file(vo_src):
                     actual_vo_path = vo_src
                     print(f"  Using local voiceover file: {vo_src}")
                 else:
                     # Optionally attempt download for voiceover if it's a URL
                     # This assumes voiceovers might also be remote URLs like images/videos
                     print(f"  Voiceover file not found locally: {vo_src}. Attempting download/cache...")
                     actual_vo_path = download_or_get_from_cache(vo_src, CACHE_DIR, TEMP_ASSET_DIR)
                     if actual_vo_path:
                         print(f"  Successfully obtained remote voiceover: {os.path.basename(actual_vo_path)}")
                     else:
                         download_issues = True
                         print(f"  Failed to download/cache voiceover: {vo_src}. Skipping voiceover for duration calculation.")

            # If we have a valid path (either local, downloaded, or TTS generated)
            if actual_vo_path:
                try:
                    print(f"  Loading voiceover to determine duration: {os.path.basename(actual_vo_path)}")
                    temp_vo_clip = AudioFileClip(actual_vo_path)
                    if temp_vo_clip.duration is None or temp_vo_clip.duration <= 0:
                        print(f"*** Error: Invalid duration ({temp_vo_clip.duration}s) for voiceover: {os.path.basename(actual_vo_path)} ***")
                        temp_vo_clip.close()
                        scene_voiceover_clip = None
                    else:
                        scene_duration = temp_vo_clip.duration
                        scene_voiceover_clip = temp_vo_clip.volumex(vo_volume)
                        voiceover_loaded_successfully = True
                        determined_by = "voiceover"
                        print(f"  Voiceover loaded. Scene duration set to: {scene_duration:.2f}s")
                except Exception as e:
                    print(f"  *** Error loading voiceover '{os.path.basename(actual_vo_path)}': {repr(e)} ***")
                    scene_voiceover_clip = None
                    if 'temp_vo_clip' in locals():
                        temp_vo_clip.close()

        # --- Determine Duration from Elements if No Voiceover ---
        if not voiceover_loaded_successfully:
            explicit_scene_duration = scene.get("duration")
            if explicit_scene_duration is not None:
                 try:
                     scene_duration = float(explicit_scene_duration)
                     determined_by = "explicit"
                     print(f"  Scene duration set from explicit 'duration' property: {scene_duration:.2f}s")
                 except ValueError:
                     print(f"Warning: Invalid explicit scene duration '{explicit_scene_duration}'. Falling back.")
                     determined_by = "fallback" # Fallback needed
            else:
                print("  No voiceover/explicit duration. Determining duration from visual elements.")
                determined_by = "elements"
                max_element_duration = 0
                has_any_element_duration = False
                for element in scene_elements_data:
                    e_dur = element.get("duration")
                    if e_dur is not None:
                        try:
                            element_duration = float(e_dur)
                            if element_duration > 0:
                                has_any_element_duration = True
                                max_element_duration = max(max_element_duration, element_duration)
                        except ValueError:
                            print(f"Warning: Invalid duration '{e_dur}' for element in Scene #{i+1}")

                if not has_any_element_duration:
                    print(f"Warning: No durations found in elements for Scene #{i+1}. Using default: {DEFAULT_ELEMENT_DURATION}s")
                    scene_duration = DEFAULT_ELEMENT_DURATION
                    determined_by = "default"
                else:
                    scene_duration = max_element_duration
                print(f"  Scene duration set from {determined_by}: {scene_duration:.2f}s")


        # --- Process Visual Elements for the Scene ---
        if scene_duration <= 0:
             print(f"*** Error: Scene #{i+1} has a calculated duration of {scene_duration:.2f}s. Skipping scene. ***")
             # Clean up voiceover clip if it was loaded but duration was invalid
             if scene_voiceover_clip: scene_voiceover_clip.close()
             continue # Skip to next scene

        print(f"  Processing visual elements for determined duration: {scene_duration:.2f}s")
        scene_visual_clips_data = [] # Store tuples of (clip, z_index) for layering

        for j, element in enumerate(scene_elements_data):
            element_type = element.get("type")
            element_src = element.get("src")
            element_text = element.get("text")
            z_index = element.get("z_index", DEFAULT_Z_INDEX)
            animation_data = element.get("animation") # Get animation data
            clip = None
            base_clip = None # Store the initially loaded clip before styling/animation
            local_path = None # Keep track of downloaded path if any

            try:
                # --- Create Base Clip ---
                if element_type == "image" and element_src:
                    # Filename for asset in temp dir (used for ImageClip)
                    # Use hash of URL for unique temp filename base
                    url_hash = hashlib.sha256(element_src.encode()).hexdigest()[:16]
                    _, ext = os.path.splitext(urlparse(element_src).path)
                    asset_filename = sanitize_filename(f"scene_{i}_elem_{j}_{url_hash}{ext if ext else '.jpg'}")

                    local_path = download_or_get_from_cache(element_src, CACHE_DIR, TEMP_ASSET_DIR)
                    if not local_path:
                        print(f"    Error downloading image asset: {element_src}")
                        continue # Skip this element
                    base_clip = ImageClip(local_path)
                    # Ensure base clip fills the target resolution by default
                    base_clip = moviepy_resize(base_clip, width=target_resolution[0], height=target_resolution[1])

                elif element_type == "video" and element_src:
                    url_hash = hashlib.sha256(element_src.encode()).hexdigest()[:16]
                    _, ext = os.path.splitext(urlparse(element_src).path)
                    asset_filename = sanitize_filename(f"scene_{i}_elem_{j}_{url_hash}{ext if ext else '.mp4'}")

                    local_path = download_or_get_from_cache(element_src, CACHE_DIR, TEMP_ASSET_DIR)
                    if not local_path:
                        print(f"    Error downloading video asset: {element_src}")
                        continue # Skip this element

                    # Load without resizing initially, animation/styling handles it
                    base_clip = VideoFileClip(local_path, audio=False)
                    # Resize video to fill target resolution while maintaining aspect ratio
                    base_w, base_h = base_clip.size
                    target_w, target_h = target_resolution
                    # Calculate resize dimensions to cover the entire frame
                    ratio = max(target_w/base_w, target_h/base_h)
                    new_w = int(base_w * ratio)
                    new_h = int(base_h * ratio)
                    base_clip = moviepy_resize(base_clip, width=new_w, height=new_h)
                    # Center the clip if it's larger than target resolution
                    if new_w > target_w or new_h > target_h:
                        x_offset = (new_w - target_w) // 2
                        y_offset = (new_h - target_h) // 2
                        base_clip = base_clip.crop(x1=x_offset, y1=y_offset, x2=x_offset+target_w, y2=y_offset+target_h)

                    # Trim or use full length up to scene_duration
                    clip_natural_duration = base_clip.duration
                    if clip_natural_duration is None or clip_natural_duration <= 0:
                         print(f"    Error: Invalid video clip duration: {clip_natural_duration}s")
                         base_clip.close()
                         continue
                    # Trim the base clip *before* animation/styling
                    final_clip_duration = min(clip_natural_duration, scene_duration)
                    base_clip = base_clip.subclip(0, final_clip_duration)

                    if clip_natural_duration < scene_duration:
                        print(f"    Info: Video element #{j} is shorter ({clip_natural_duration:.2f}s) than scene duration ({scene_duration:.2f}s). Video will end early (last frame held).")

                elif element_type == "text" and element_text:
                    # Text specific styling
                    fontsize = element.get("fontsize", 70)
                    font = element.get("font", "Arial") # Make sure this font is installed/accessible
                    color = element.get("color", "white")
                    bg_color = element.get("bg_color", "transparent")
                    stroke_color = element.get("stroke_color") # New
                    stroke_width = element.get("stroke_width", 1) # New
                    text_align = element.get("align", "center") # New text alignment ('left', 'center', 'right')
                    # Method 'caption' useful for auto-wrapping text based on size
                    # Use caption if alignment is not center, otherwise label (default)
                    # Provide a sensible max width for caption wrapping (e.g., 80% of video width)
                    text_size = (target_resolution[0] * 0.8, None) # Max width, auto height
                    method = 'caption' if text_align != 'center' else 'label'

                    # Attempt to create TextClip - NEEDS IMAGEMAGICK INSTALLED AND IN PATH
                    try:
                        # Convert text alignment to ImageMagick-compatible format
                        align_map = {
                            'left': 'west',
                            'center': 'center',
                            'right': 'east'
                        }
                        img_align = align_map.get(text_align, 'center')
                        
                        base_clip = TextClip(
                            element_text,
                            fontsize=fontsize,
                            font=font,
                            color=color,
                            bg_color=bg_color,
                            stroke_color=stroke_color,
                            stroke_width=stroke_width,
                            method=method,
                            align=img_align,  # Use mapped alignment
                            size=text_size if method == 'caption' else None
                        )
                    except Exception as text_clip_error:
                         print(f"*** ERROR CREATING TEXTCLIP for element #{j} ***")
                         print("*** This often means ImageMagick is not installed or not in your system PATH. ***")
                         print(f"*** Original Error: {repr(text_clip_error)} ***")
                         continue

                else:
                    print(f"  Warning: Unsupported element type '{element_type}' or missing src/text for element #{j}. Skipping.")
                    continue

                # --- Apply Animation or Static Styling ---
                processed_clip = None # This will hold the final styled/animated clip
                if animation_data:
                    print(f"    Applying animation to element #{j}")
                    animation_function = create_animation_func(
                        base_clip, 
                        animation_data.get("start",{}), 
                        animation_data.get("end",{}), 
                        scene_duration, 
                        target_resolution
                    )
                    processed_clip = base_clip.set_make_frame(
                        lambda t: animation_function(t).get_frame(0)
                    )

                else:
                    # Apply static styling (No animation block found)
                    print(f"    Applying static styling to element #{j}")
                    try:
                        # Apply size transformation if specified
                        size_args = parse_size(element.get("size", {}), target_resolution)
                        if size_args:
                            processed_clip = moviepy_resize(base_clip, **size_args)
                        else:
                            processed_clip = base_clip

                        # Apply static position if specified
                        position_data = element.get("position")
                        if position_data:
                            # Get element size after any size transforms
                            elem_size = (processed_clip.w, processed_clip.h)
                            position = parse_position(position_data, target_resolution, elem_size, element.get("align"))
                            if position:
                                processed_clip = processed_clip.set_position(position)

                    except Exception as style_error:
                        print(f"    *** Error applying static styling to element #{j}: {repr(style_error)} ***")
                        if base_clip:
                            base_clip.close()
                        continue

                # --- Final Duration Set & Store ---
                # Set the duration for the final processed clip (animated or static)
                processed_clip = processed_clip.set_duration(scene_duration)

                # Store the final clip and its z_index for layering
                scene_visual_clips_data.append((processed_clip, z_index))
                # Note: base_clip is not explicitly closed here IF processed_clip references it.
                # MoviePy often handles this, but complex filters might need manual closure.

            except Exception as e:
                print(f"  *** CRITICAL ERROR processing element #{j} in Scene #{i+1}: {repr(e)} ***")
                traceback.print_exc()
                scene_processing_error = True # Mark scene as having errors
                # Attempt to close base clip if it was created before error
                if base_clip:
                    try: base_clip.close()
                    except: pass # Ignore errors during cleanup
                continue # Skip this element on error

        # --- Combine visual elements for the scene based on Z-index ---
        if scene_visual_clips_data and not scene_processing_error:
            # Sort clips by z_index (ascending, so higher z is later in list = on top)
            scene_visual_clips_data.sort(key=lambda item: item[1])
            sorted_clips = [item[0] for item in scene_visual_clips_data]

            # Create composite for the scene
            # Use a transparent background by default unless a base layer fills screen
            scene_visual_composite = CompositeVideoClip(
                sorted_clips,
                size=target_resolution,
                use_bgclip=True, # Important for transparency & correct animation compositing
                bg_color=(0,0,0,0) # Explicit transparent background
            ).set_duration(scene_duration)
        elif scene_processing_error:
             print(f"Warning: Scene #{i+1} skipped due to errors processing its elements.")
             # Clean up any clips created before the error
             for clip_tuple in scene_visual_clips_data:
                 if clip_tuple[0]: clip_tuple[0].close()
             if scene_voiceover_clip: scene_voiceover_clip.close()
             continue # Skip to the next scene
        else:
            # No elements processed, but no explicit error flagged? Log warning.
            print(f"Warning: Scene #{i+1} resulted in no processable visual clips. Skipping scene.")
            if scene_voiceover_clip: scene_voiceover_clip.close() # Clean up VO clip if unused
            continue # Skip to the next scene

        # --- Store processed scene data for assembly ---
        transition_info = scene.get('transition')
        processed_scenes.append({
            "id": i+1, # Store scene number for easier debugging
            "clip": scene_visual_composite,
            "voiceover_clip": scene_voiceover_clip, # Already loaded and volume adjusted (or None)
            "scene_duration": scene_duration,
            "transition_to_this": transition_info
        })
        # Estimate duration - refine later based on transitions
        total_video_duration_estimate += scene_duration
        print(f"Scene #{i+1} processing complete. Final Duration: {scene_duration:.2f}s")


    # --- Error checks after processing all scenes ---
    if download_issues: print("\nWarning: One or more assets had download or caching issues during processing.")
    if not processed_scenes:
        print("\n*** Error: No scenes were processed successfully. Cannot create video. ***")
        cleanup_temp() # Clean up even if no scenes processed
        return # Exit

    # 4. Assemble Visual Clips with Transitions
    print("\n--- Assembling Video Visuals with Transitions ---")
    final_clips_to_compose = [] # Holds the final visual clips with start times and fades
    current_timeline_pos = 0.0
    actual_total_duration = 0

    for i, scene_data in enumerate(processed_scenes):
        clip = scene_data["clip"]
        transition_info = scene_data["transition_to_this"]
        scene_duration = scene_data["scene_duration"]
        transition_duration = 0.0
        clip_start_time = current_timeline_pos

        if i > 0 and transition_info:
            # Approximation using crossfade (replace with advanced logic if needed)
            try:
                transition_duration = float(transition_info.get("duration", DEFAULT_TRANSITION_DURATION))
            except ValueError:
                 print(f"Warning: Invalid transition duration '{transition_info.get('duration')}' for scene {scene_data['id']}. Using default.")
                 transition_duration = DEFAULT_TRANSITION_DURATION

            transition_style = transition_info.get("style", "fade") # Style not used in crossfade approx.
            print(f"  Applying transition into Scene #{scene_data['id']}: '{transition_style}' (duration: {transition_duration:.2f}s) - Approximated as Crossfade")

            # Adjust start time for overlap & Apply crossfade effect
            # Ensure clip_start_time doesn't go negative significantly
            clip_start_time = max(0, current_timeline_pos - transition_duration)
            # Calculate the actual overlap duration
            overlap_duration = current_timeline_pos - clip_start_time

            if overlap_duration > 0:
                 clip = clip.crossfadein(overlap_duration)
            # else: No overlap, place clip directly after previous


        clip = clip.set_start(clip_start_time)
        final_clips_to_compose.append(clip)

        # Advance timeline position for the *next* clip's start
        current_timeline_pos = clip_start_time + scene_duration

    # Calculate final duration based on the last clip's end time
    if final_clips_to_compose:
        last_clip = final_clips_to_compose[-1]
        actual_total_duration = last_clip.start + last_clip.duration # Use duration after potential crossfadein
        print(f"Total video duration calculated: {actual_total_duration:.2f}s")
    else:
         print("*** Error: No visual clips available for final composition. ***")
         cleanup_temp()
         return

    if actual_total_duration <= 0:
        print(f"*** Error: Calculated total video duration is {actual_total_duration:.2f}s. Cannot write video. ***")
        cleanup_temp()
        return


    # 5. Create Final Composite Visual Video
    print("Compositing final video track...")
    try:
        final_video = CompositeVideoClip(
            final_clips_to_compose,
            size=target_resolution
            ).set_duration(actual_total_duration)
        print("Visual composition complete.")
    except Exception as e:
        print(f"*** Error during final visual composition: {repr(e)} ***")
        traceback.print_exc()
        # Attempt cleanup before exiting
        for clip in final_clips_to_compose: clip.close()
        for scene_data in processed_scenes: scene_data['clip'].close() # Close scene composites
        cleanup_temp()
        return

    # 6. Prepare and Composite Audio
    print("\n--- Preparing and Compositing Audio ---")
    all_audio_clips = [] # List to hold final audio clips (BG, VOs)
    final_combined_audio = None # Initialize

    # --- Background Audio ---
    if bg_audio_path:
        # Use check_local_file first for local paths
        bg_local_path = None
        if check_local_file(bg_audio_path):
             bg_local_path = bg_audio_path
             print(f"  Using local background music: {bg_audio_path}")
        else:
            # Try downloading if it looks like a URL (basic check)
            if bg_audio_path.startswith(('http://', 'https://')):
                 print(f"  Local background music not found. Attempting download/cache for: {bg_audio_path}")
                 bg_local_path = download_or_get_from_cache(bg_audio_path, CACHE_DIR, TEMP_ASSET_DIR)
                 if not bg_local_path:
                      download_issues = True
                      print(f"  Failed to download/cache background music: {bg_audio_path}")
            else:
                 print(f"  Warning: Background music file not found: {bg_audio_path}")

        if bg_local_path:
            try:
                print(f"  Loading background music: {os.path.basename(bg_local_path)}")
                background_audio = AudioFileClip(bg_local_path)

                # Ducking logic
                actual_bg_volume = bg_audio_volume
                if has_any_voiceovers:
                    print("  Applying volume ducking to background music due to voiceovers")
                    actual_bg_volume = bg_audio_volume * DUCK_BG_MUSIC_FACTOR
                    print(f"  Background music volume reduced to {actual_bg_volume:.2%}")
                background_audio = background_audio.volumex(actual_bg_volume)

                # Looping logic
                if background_audio.duration < actual_total_duration:
                    print(f"  Background music ({background_audio.duration:.2f}s) is shorter than video ({actual_total_duration:.2f}s). Setting up looping.")
                    # Calculate how many full loops we need
                    num_loops = math.ceil(actual_total_duration / background_audio.duration)
                    # Create concatenated audio of required loops
                    looped_chunks = [background_audio] * num_loops
                    background_audio = concatenate_audioclips(looped_chunks)
                    # Trim to exact duration needed
                    background_audio = background_audio.subclip(0, actual_total_duration)

                # Trim to final duration and add fades
                background_audio = background_audio.subclip(0, actual_total_duration)
                # Apply fades safely, ensuring fade duration isn't longer than clip
                fade_in_dur = min(DEFAULT_AUDIO_FADE_SECONDS, actual_total_duration / 2)
                fade_out_dur = min(DEFAULT_AUDIO_FADE_SECONDS, actual_total_duration / 2)
                background_audio = background_audio.audio_fadein(fade_in_dur).audio_fadeout(fade_out_dur)

                all_audio_clips.append(background_audio)
            except Exception as e:
                print(f"  *** Error loading or processing background music '{os.path.basename(bg_local_path)}': {repr(e)} ***")
                if 'background_audio' in locals() and background_audio: background_audio.close() # Attempt close on error


    # --- Scene Voiceovers ---
    for i, scene_data in enumerate(processed_scenes):
        vo_clip = scene_data.get("voiceover_clip") # Use .get for safety
        if vo_clip:
            # Find corresponding visual clip's start time from the final composed list
            try:
                 visual_clip_start_time = final_clips_to_compose[i].start
            except IndexError:
                 print(f"Warning: Could not find visual clip for voiceover of scene {scene_data['id']}. Skipping VO.")
                 vo_clip.close() # Close unused clip
                 continue

            actual_vo_start_time = max(0, visual_clip_start_time) # Ensure non-negative start time
            print(f"  Adding voiceover for Scene #{scene_data['id']} at time {actual_vo_start_time:.2f}s")
            vo_clip = vo_clip.set_start(actual_vo_start_time)

            # Ensure VO doesn't exceed total video duration (important for last scene VOs)
            vo_end_time = actual_vo_start_time + vo_clip.duration
            if vo_end_time > actual_total_duration:
                print(f"    Trimming voiceover for scene {scene_data['id']} as it exceeds total duration.")
                vo_clip = vo_clip.subclip(0, max(0, actual_total_duration - actual_vo_start_time))

            # Only add if duration is still positive after potential trim
            if vo_clip.duration > 0:
                all_audio_clips.append(vo_clip)
            else:
                 print(f"    Voiceover for scene {scene_data['id']} has zero duration after trimming. Skipping.")
                 vo_clip.close() # Close zero-duration clip


    # --- Mix all audio ---
    if all_audio_clips:
        print("  Compositing final audio track...")
        try:
            # Composite audio clips together
            final_combined_audio = CompositeAudioClip(all_audio_clips).set_duration(actual_total_duration)
            # Set the composite audio to the final video
            final_video = final_video.set_audio(final_combined_audio)
            print("  Audio composited successfully.")
        except Exception as e:
            print(f"  *** Error compositing audio: {repr(e)} ***")
            traceback.print_exc()
            final_video = final_video.set_audio(None) # Ensure no broken audio is attached
    else:
        print("  No audio tracks to add to the final video.")
        final_video = final_video.set_audio(None)


    # 7. Write Video File
    print(f"\n--- Writing Final Video: {output_filename} ---")
    render_success = False
    try:
        final_video.write_videofile(
            output_filename,
            fps=24,
            codec="libx264",        # Common, good quality/compression codec
            audio_codec="aac",      # Standard audio codec
            temp_audiofile=os.path.join(TEMP_ASSET_DIR, 'temp-audio.m4a'), # Use temp dir
            remove_temp=True,       # Clean up temp audio file
            preset=ffmpeg_preset,   # Controls encoding speed vs compression
            ffmpeg_params=ffmpeg_extra_params, # Additional params like -crf
            threads=max(1, os.cpu_count() // 2), # Use half cores to leave resources free
            logger='bar'            # Progress bar
        )
        print(f"\n--- Video creation successful: {output_filename} ---")
        render_success = True
    except Exception as e:
        print(f"\n*** ERROR WRITING VIDEO FILE: {repr(e)} ***")
        traceback.print_exc()


    # 8. Cleanup: Close All Clips and Remove Temp Dir
    finally:
        print("--- Final Cleanup ---")
        # Explicitly close clips to release file handles
        try:
            if 'final_video' in locals() and final_video: final_video.close()
            if 'final_combined_audio' in locals() and final_combined_audio: final_combined_audio.close()
            # Close clips held in processed_scenes and intermediate lists
            for scene_data in processed_scenes:
                if scene_data.get('clip'): scene_data['clip'].close()
                # Note: VO clips were added to all_audio_clips and closed there if compositeaudio was created
            for clip in all_audio_clips: # Close individual audio clips too
                if clip: clip.close()
            # Composites in final_clips_to_compose reference scene clips which should be closed above
            # for clip in final_clips_to_compose: # Closing these might double-close? Test if needed.
            #     if clip: clip.close()

        except Exception as close_err:
            print(f"Warning: Error during explicit clip cleanup: {close_err}")

        cleanup_temp() # Remove temp directory

        if render_success:
             print("Cleanup complete. Video generation finished.")
        else:
             print("Cleanup complete. Video generation finished with errors during rendering.")


# --- Main Execution ---
if __name__ == "__main__":
    json_file_path = "video_script_advanced.json"
    output_video_file = "my_generated_video_advanced.mp4"

    try:
        print("Starting video generation process...")
        print(f"Loading script: {json_file_path}")
        if not os.path.exists(json_file_path):
            raise FileNotFoundError(f"JSON script file not found at: {os.path.abspath(json_file_path)}")

        with open(json_file_path, 'r', encoding='utf-8') as f:
            video_data = json.load(f)

        create_video_from_json(video_data, output_video_file)

    except FileNotFoundError as e:
        print(f"\n*** Error: {e} ***")
    except json.JSONDecodeError as e:
        print(f"\n*** Error: Could not decode JSON from {json_file_path}. Check for syntax errors: {e} ***")
    except Exception as e:
        print(f"\n*** An unexpected critical error occurred in the main execution block: {repr(e)} ***")
        traceback.print_exc()
        cleanup_temp()

    print("\nScript finished.")