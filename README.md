# Python Video Editor (JSON Based)

Create videos programmatically using Python by defining scenes, elements, animations, audio, and transitions in a JSON configuration file. This tool leverages MoviePy and offers features like asset caching, TTS voiceovers, and element animations.

## Features

- **JSON Configuration:** Define entire videos via a structured JSON file.
- **Multiple Resolutions:** Supports SD, HD, Full-HD, 4K presets (`"sd"`, `"hd"`, `"full-hd"`, `"4k"`).
- **Variable Quality:** Control output quality vs. file size (`"low"`, `"medium"`, `"high"`, `"production"` presets).
- **Media Types:**
  - Images (JPG, PNG, etc.) - Fetched via URL or local path.
  - Videos (MP4, MOV, etc.) - Fetched via URL or local path.
  - Text Overlays - Customizable fonts, sizes, colors, stroke, background color. **(Requires ImageMagick)**
- **Audio Handling:**
  - Global background music (local path or URL) with volume control and auto-looping/trimming.
  - Scene-specific voiceovers (local path or URL).
  - **Text-to-Speech (TTS):** Generate voiceovers directly from text using gTTS (**Requires `pip install gTTS`**).
  - Basic Audio Ducking: Automatically lowers background music volume slightly when voiceovers are present.
- **Positioning & Sizing:**
  - Precise element placement using pixels or percentages (`"50%"`).
  - Alignment options (`"center"`, `"top_left"`, `"bottom_right"`, etc.).
  - Resize elements using pixels or percentages.
- **Layering:** Control element stacking using `z_index`.
- **Animation:**
  - Animate `size`, `position`, `opacity`, and `rotation` between `start` and `end` states over the element's duration.
- **Transitions:** Define transition styles and durations between scenes. _(**Limitation:** Currently approximates all specified transition `style`s as simple **crossfades**)._
- **Watermarking:** Add a global image or text watermark overlay.
- **Asset Management:**
  - Handles both local file paths and web URLs for media assets.
  - **Caching:** Automatically caches downloaded assets to `asset_cache/` folder to speed up subsequent runs.
  - Filename sanitization for cache files.

## Requirements

- **Python:** 3.8+ recommended.
- **Libraries:**
  - `moviepy==1.0.3` (Note: Specific older version used as a workaround during development. Consider upgrading to MoviePy 2.x later for more features/fixes, but troubleshoot installation if needed.)
  - `Pillow>=9.0.0` (Image handling)
  - `numpy` (Dependency for MoviePy and effects)
  - `requests` (For downloading URL assets)
  - `gTTS` (**Optional:** Only required if using the `"tts"` feature for voiceovers)
- **External Software:**
  - **FFmpeg:** Essential backend for MoviePy. Must be installed and accessible in the system's PATH.
  - **ImageMagick:** **Required ONLY if using Text elements (`type: "text"`)**. Must be installed, accessible in the system's PATH, and include "legacy utilities (e.g., convert)" during installation (especially on Windows).

## Installation

1.  **Clone the Repository:**

    ```bash
    git clone [https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git](https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git) # Replace with your repo URL
    cd YOUR_REPOSITORY_NAME
    ```

2.  **Create and Activate a Virtual Environment (Strongly Recommended):**

    ```bash
    # Create environment (do this once)
    python -m venv venv

    # Activate environment (do this each time you work on the project)
    # Windows (cmd.exe):
    .\venv\Scripts\activate.bat
    # Windows (PowerShell):
    .\venv\Scripts\Activate.ps1
    # macOS / Linux (bash/zsh):
    source venv/bin/activate
    ```

    _(You should see `(venv)` at the start of your terminal prompt)_

3.  **Install Required Python Packages:**

    ```bash
    # Make sure your virtual environment is active!
    pip install moviepy==1.0.3 Pillow>=9.0.0 numpy requests gTTS
    ```

4.  **Install FFmpeg:**

    - Download from the [FFmpeg official website](https://ffmpeg.org/download.html).
    - Follow the installation instructions for your operating system.
    - **Crucial:** Ensure the directory containing the `ffmpeg` executable is added to your system's **PATH** environment variable.
    - Verify by opening a **new** terminal and typing: `ffmpeg -version`

5.  **Install ImageMagick (ONLY if using Text elements):**
    - Download from the [ImageMagick official website](https://imagemagick.org/script/download.php).
    - **Windows:** During installation, **make sure to check the boxes** for:
      - `Install legacy utilities (e.g., convert)`
      - `Add application directory to your system path (PATH)`
    - **macOS:** `brew install imagemagick`
    - **Linux (Debian/Ubuntu):** `sudo apt-get update && sudo apt-get install imagemagick`
    - **Crucial:** After installing, **RESTART your computer** or at least fully close and reopen your terminal/IDE to ensure the PATH updates are recognized.
    - Verify by opening a **new** terminal and typing: `magick -version` (or sometimes `convert -version`).

## Usage

1.  **Prepare JSON Script:** Create or modify your video definition file (e.g., `video_script_advanced.json`). See the detailed guide below.
2.  **Place Local Assets:** Create an `Assets` folder (or any folder) in your project directory. Place any local image, video, or audio files referenced in your JSON inside this folder. Use the correct relative (e.g., `Assets/music.mp3`) or absolute paths in the JSON `src` fields.
3.  **Run the Script:**
    - Make sure your virtual environment `(venv)` is active.
    - Execute the Python script from your terminal, providing the path to your JSON file:
      ```bash
      python create_video_final_v3.py video_script_advanced.json my_output_video.mp4
      ```
      - Replace `create_video_final_v3.py` with the actual name of the Python script file.
      - Replace `video_script_advanced.json` with the name of your JSON configuration file.
      - `my_output_video.mp4` is the optional output filename (defaults to `my_generated_video_...mp4`).
4.  **Output:**
    - The final video file will be saved in the directory where you ran the script.
    - Downloaded assets are cached in the `asset_cache/` folder.
    - Temporary files are created and deleted in `temp_video_assets_adv/` during runtime.

## JSON Configuration Guide

This guide details all the parameters you can use in your JSON file.

### Top-Level Object

| Key          | Type   | Required | Default     | Description                                                                                                 |
| :----------- | :----- | :------- | :---------- | :---------------------------------------------------------------------------------------------------------- |
| `resolution` | String | No       | `"full-hd"` | Output video resolution. Values: `"sd"`, `"hd"`, `"full-hd"`, `"4k"`.                                       |
| `quality`    | String | No       | `"medium"`  | Output quality preset. Values: `"low"`, `"medium"`, `"high"`, `"production"`.                               |
| `defaults`   | Object | No       | `{}`        | Default values for element properties (e.g., `font`, `fontsize`, `color`).                                  |
| `audio`      | Object | No       | `null`      | Global background audio settings. See **Audio Object** below.                                               |
| `watermark`  | Object | No       | `null`      | Global watermark overlay settings. See **Watermark Object** below.                                          |
| `scenes`     | Array  | Yes      | `[]`        | An array of **Scene Objects** defining the video sequence. Must contain at least one valid processed scene. |

### Audio Object (Background Audio)

Used inside the top-level `audio` key.

| Key       | Type    | Required | Default | Description                                                                          |
| :-------- | :------ | :------- | :------ | :----------------------------------------------------------------------------------- |
| `src`     | String  | Yes      | `null`  | Local file path (`Assets/music.mp3`) or URL (`https://...`) to the audio file.       |
| `volume`  | Number  | No       | `1.0`   | Volume multiplier (0.0 to 1.0+).                                                     |
| `ducking` | Object  | No       | `{}`    | Settings for reducing volume during voiceovers.                                      |
| `enabled` | Boolean | No       | `false` | If `true`, reduces volume by `DUCK_BG_MUSIC_FACTOR` when any voiceovers are present. |

### Watermark Object

Used inside the top-level `watermark` key.

| Key        | Type                 | Required                | Default    | Description                                                                          |
| :--------- | :------------------- | :---------------------- | :--------- | :----------------------------------------------------------------------------------- |
| `type`     | String               | Yes                     | `null`     | `"image"` or `"text"`.                                                               |
| `src`      | String               | Yes, if `type=="image"` | `null`     | Local path or URL to the image file.                                                 |
| `text`     | String               | Yes, if `type=="text"`  | `null`     | The text content.                                                                    |
| `font`     | String               | No (uses `defaults`)    | `"Arial"`  | Font name for text watermark. **Must be installed.**                                 |
| `fontsize` | Number               | No (uses `defaults`)    | `30`       | Font size for text watermark.                                                        |
| `color`    | String               | No (uses `defaults`)    | `"white"`  | Color for text watermark (name, `#rrggbb`, `rgba(...)`).                             |
| `opacity`  | Number               | No                      | `1.0`      | Overall opacity (0.0 to 1.0).                                                        |
| `size`     | Object               | No                      | `null`     | Resize the watermark. See **Size Object** below.                                     |
| `position` | Object\|String\|List | No                      | `"center"` | Position the watermark. See **Position Object** below.                               |
| `align`    | String               | No                      | `"center"` | Watermark's anchor point relative to its position. See **Alignment Keywords** below. |

### Scene Object

Each object within the top-level `"scenes"` array.

| Key          | Type   | Required | Default | Description                                                                                                                                  |
| :----------- | :----- | :------- | :------ | :------------------------------------------------------------------------------------------------------------------------------------------- |
| `comment`    | String | No       | `null`  | User description (ignored by script).                                                                                                        |
| `duration`   | Number | No       | `null`  | Explicit duration in seconds. **If set, overrides voiceover/element duration.**                                                              |
| `transition` | Object | No       | `null`  | Transition _into_ this scene. See **Transition Object** below.                                                                               |
| `voiceover`  | Object | No       | `null`  | Scene-specific audio. Its duration sets scene duration if `scene.duration` is not set. See **Voiceover Object** below.                       |
| `elements`   | Array  | Yes      | `[]`    | Array of **Element Objects** to display in this scene. Must contain at least one element that renders successfully for the scene to be kept. |

### Transition Object

Used inside a **Scene Object**.

| Key        | Type   | Required | Default  | Description                                                                                                   |
| :--------- | :----- | :------- | :------- | :------------------------------------------------------------------------------------------------------------ |
| `style`    | String | No       | `"fade"` | Desired style (e.g., `"fade"`, `"wiperight"`). **_(Limitation: All styles currently render as crossfades)._** |
| `duration` | Number | No       | `1.0`    | Duration of the transition overlap in seconds.                                                                |

### Voiceover Object

Used inside a **Scene Object**.

| Key      | Type   | Required                       | Default | Description                                          |
| :------- | :----- | :----------------------------- | :------ | :--------------------------------------------------- |
| `src`    | String | No (but `src` or `tts` needed) | `null`  | Local path or URL to an audio file.                  |
| `tts`    | Object | No (but `src` or `tts` needed) | `null`  | Text-to-Speech parameters. See **TTS Object** below. |
| `volume` | Number | No                             | `1.0`   | Volume multiplier (0.0 to 1.0+).                     |

### TTS Object

Used inside a **Voiceover Object**. **Requires `pip install gTTS`**.

| Key        | Type   | Required | Default | Description                                                 |
| :--------- | :----- | :------- | :------ | :---------------------------------------------------------- |
| `text`     | String | Yes      | `null`  | The text to synthesize into speech.                         |
| `language` | String | No       | `"en"`  | Language code for TTS generation (e.g., `"en-uk"`, `"es"`). |

### Element Object

Each object within a scene's `"elements"` array.

| Key            | Type         | Required              | Default         | Description                                                                                                                  |
| :------------- | :----------- | :-------------------- | :-------------- | :--------------------------------------------------------------------------------------------------------------------------- |
| `comment`      | String       | No                    | `null`          | User description.                                                                                                            |
| `type`         | String       | Yes                   | `null`          | `"image"`, `"video"`, or `"text"`.                                                                                           |
| `src`          | String       | Yes (for image/video) | `null`          | Local path or URL to the media file.                                                                                         |
| `text`         | String       | Yes (for text)        | `null`          | Text content (can include `\n` for newlines).                                                                                |
| `duration`     | Number       | No                    | `null`          | **Only used if** scene has no `duration` and no `voiceover`. Max value across elements sets scene duration.                  |
| `z_index`      | Integer      | No                    | `0`             | Stacking order (higher numbers are on top).                                                                                  |
| `size`         | Object       | No                    | `null`          | Static size. Applied _after_ initial loading/fitting. See **Size Object**.                                                   |
| `position`     | String\|List | No                    | `"center"`      | Static position of the element's anchor point. See **Position Values**.                                                      |
| `align`        | String       | No                    | `"center"`      | Element's anchor point relative to its `position`. See **Alignment Keywords**.                                               |
| `opacity`      | Number       | No                    | `1.0`           | Static opacity (0.0 to 1.0).                                                                                                 |
| `rotation`     | Number       | No                    | `0.0`           | Static rotation in degrees.                                                                                                  |
| `animation`    | Object       | No                    | `null`          | Animate element properties. If present, static `size`/`position`/`opacity`/`rotation` are ignored. See **Animation Object**. |
| `fontsize`     | Number       | No (uses `defaults`)  | `70`            | (Text only) Font size.                                                                                                       |
| `font`         | String       | No (uses `defaults`)  | `"Arial"`       | (Text only) Font name. **Must be installed on system.**                                                                      |
| `color`        | String       | No (uses `defaults`)  | `"white"`       | (Text only) Text color (name, `#rrggbb`, `rgba(...)`).                                                                       |
| `bg_color`     | String       | No                    | `"transparent"` | (Text only) Background color for text bounding box.                                                                          |
| `stroke_color` | String       | No                    | `null`          | (Text only) Outline color.                                                                                                   |
| `stroke_width` | Number       | No                    | `1`             | (Text only) Outline width in pixels.                                                                                         |

### Size Object

Used inside `element.size` or `watermark.size`.

| Key      | Type           | Description                                                                                                                                                                                                                              |
| :------- | :------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `width`  | Number\|String | Width in pixels (e.g., `300`) or percentage of video width (e.g., `"50%"`).                                                                                                                                                              |
| `height` | Number\|String | Height in pixels (e.g., `200`) or percentage of video height (e.g., `"25%"`).                                                                                                                                                            |
|          |                | _Note:_ If only one dimension (`width` or `height`) is provided, the other is calculated automatically to maintain the element's original aspect ratio. If both are provided, the element is forced into that specific width and height. |

### Position Values

Used for `element.position` or `watermark.position`. Can be:

1.  **Keyword String:** `"center"`, `"top"`, `"bottom"`, `"left"`, `"right"`, `"top_left"`, `"top_right"`, `"bottom_left"`, `"bottom_right"`. These define the target point on the video frame.
2.  **List `[x, y]`:** Defines the target point using coordinates.
    - `x`, `y` can be Numbers (pixels) or Strings (percentages relative to video dimensions, e.g., `"50%"`). Example: `[100, "25%"]`.

### Alignment Keywords

Used for `element.align` or `watermark.align`. Defines which part of the element itself is placed at the calculated `position`. Uses the same keywords as the Position Keyword Strings above (e.g., `"center"`, `"top_left"`, `"bottom_right"`). Defaults to `"center"`.

### Animation Object

Used inside `element.animation`. Defines how properties change over the element's duration.

| Key     | Type   | Required | Description                                                                                                                                                                                                                                                                                             |
| :------ | :----- | :------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `start` | Object | Yes      | A **State Object** defining properties at the beginning (time = 0).                                                                                                                                                                                                                                     |
| `end`   | Object | Yes      | A **State Object** defining properties at the end (time = duration).                                                                                                                                                                                                                                    |
|         |        |          | _Note:_ The script linearly interpolates numeric values (`size`, `opacity`, `rotation`, numeric `position` coordinates) between the `start` and `end` states over the element's duration. Alignment keywords are applied based on the state they are defined in (usually consistent between start/end). |

### State Object (`start`/`end`)

Used inside the `animation` object. Can contain any combination of the following keys:

| Key        | Type         | Description                                                                                                                                                                                               |
| :--------- | :----------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `size`     | Object       | Target size at this state. See **Size Object**.                                                                                                                                                           |
| `position` | String\|List | Target position at this state. See **Position Values**.                                                                                                                                                   |
| `align`    | String       | Element's anchor point at this state. See **Alignment Keywords**. Usually set consistently in both `start` and `end` unless you intend a specific pivot change (which might look odd with interpolation). |
| `opacity`  | Number       | Opacity (0.0 to 1.0) at this state.                                                                                                                                                                       |
| `rotation` | Number       | Rotation (degrees) at this state.                                                                                                                                                                         |

## Project Structure Example

YOUR_PROJECT_FOLDER/
├── create_video_final_v3.py # The main Python script
├── video_script_advanced.json # Your video definition file
├── Assets/ # Directory for YOUR local media files
│ ├── music.mp3
│ ├── logo.png
│ ├── scene1_vo.wav
│ └── sample_video.mp4
├── asset_cache/ # Automatically created for downloaded files
│ └── ...cached files...
├── temp_video_assets_adv/ # Automatically created and deleted during runtime
└── venv/ # Your Python virtual environment (recommended)
└── ...

## Known Limitations & Issues

- **Advanced Transitions:** All specified transition `style`s currently render as simple **crossfades**. Implementing wipes, slides, etc., requires significant code changes (likely using masking or direct FFmpeg commands).
- **Ken Burns Effect:** The JSON supports the structure (`ken_burns` key), but the effect logic is a **placeholder** in the Python code and is not currently applied.
- **Advanced Audio Ducking:** The script only applies a simple volume reduction factor (`DUCK_BG_MUSIC_FACTOR`) to background music when any voiceovers are present. It does not dynamically fade volume based on precise voiceover timing.
- **Text Rendering:** Relies heavily on **ImageMagick** being correctly installed and configured in the system PATH. If ImageMagick fails, text elements will be **replaced by black rectangles** (with a warning in the console). Ensure specified fonts are installed on your system.
- **Animation Performance:** Complex animations applied to many elements, especially on high-resolution videos, can significantly increase rendering time as they are processed frame-by-frame.
- **MoviePy Version:** The script is currently set up with `moviepy==1.0.3` due to user environment workarounds. Using the latest MoviePy (2.x) is generally recommended but may require resolving installation issues. Some minor incompatibilities might exist with v1.0.3.

## Troubleshooting

- **Check Console Output:** Carefully read all messages printed in the terminal. Warnings (`Warning: ...`) and errors (`Error: ...`, `FATAL ERROR: ...`, tracebacks) provide crucial clues.
- **`FileNotFoundError`:** Double-check all local file paths (`src`) in your JSON. Ensure they are correct relative to where you run the script, or use valid absolute paths. Check for typos.
- **ImageMagick / TextClip Errors / Black Text:** Ensure ImageMagick is installed correctly (including legacy utilities + PATH) and **restart** your terminal/computer. Test `magick -version` in the terminal. If text still fails, check font names are correct and installed.
- **TTS Errors (`gTTS`):** Ensure `pip install gTTS` was successful and you have an active internet connection when running the script with TTS elements. Check the specified language code.
- **Download/Cache Errors:** Check the URL is correct and accessible. Ensure the `asset_cache` directory is writable. Try deleting the `asset_cache` folder to force redownloads.
- **Slow Rendering:** Reduce video `resolution`/`quality`, simplify `animation` objects, use fewer elements per scene, or shorten scene durations.
- **Black Background Showing:** Usually means elements failed to load/render (check console for errors related to specific elements), or elements have transparency (like PNGs), or elements don't cover the full frame due to `size`/`position`.

## Contributing

Contributions, bug reports, and feature requests are welcome! Please feel free to open an issue or submit a Pull Request on the GitHub repository.

## License

This project is likely licensed under the MIT License (or specify your chosen license). Consider adding a `LICENSE` file to your repository.

Sources and related content
