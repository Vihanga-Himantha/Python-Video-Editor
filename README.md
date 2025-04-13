# JSON-based Video Editor

A Python-based video editor that creates videos from JSON configurations. This tool allows you to create videos by defining scenes, transitions, and elements in a JSON file.

## Features

- Create videos from JSON configuration
- Support for multiple resolutions (SD, HD, Full-HD, 4K)
- Quality presets (low, medium, high, production)
- Scene transitions with customizable duration
- Support for various media types:
  - Images with auto-resizing
  - Videos with resolution adjustment
  - Text overlays with customizable fonts and colors
- Background audio support with auto-looping and fade effects
- Temporary asset management
- Progress tracking during video creation

## Requirements

- Python 3.6+
- MoviePy
- Pillow
- FFmpeg
- Requests

## Installation

1. Clone the repository:

```bash
git clone https://github.com/yourusername/json-video-editor.git
cd json-video-editor
```

2. Install the required packages:

```bash
pip install moviepy pillow requests
```

3. Install FFmpeg (if not already installed):
   - Windows: Download from [FFmpeg official website](https://ffmpeg.org/download.html)
   - Linux: `sudo apt-get install ffmpeg`
   - macOS: `brew install ffmpeg`

## Usage

1. Create a JSON configuration file (e.g., `video_script.json`):

```json
{
  "resolution": "full-hd",
  "quality": "high",
  "scenes": [
    {
      "comment": "Scene #1",
      "transition": {
        "style": "fade",
        "duration": 1.5
      },
      "elements": [
        {
          "type": "image",
          "src": "https://example.com/image.jpg",
          "duration": 5
        }
      ]
    }
  ]
}
```

2. Run the script:

```bash
python create_video.py
```

## JSON Configuration

### Global Settings

- `resolution`: "sd" | "hd" | "full-hd" | "4k"
- `quality`: "low" | "medium" | "high" | "production"

### Scene Structure

- `comment`: Scene description
- `transition`: Transition effects
  - `style`: Currently supports "fade" (other styles approximated as crossfade)
  - `duration`: Transition duration in seconds
- `elements`: Array of media elements
  - Image Element:
    ```json
    {
      "type": "image",
      "src": "URL or path",
      "duration": seconds
    }
    ```
  - Video Element:
    ```json
    {
      "type": "video",
      "src": "URL or path",
      "duration": seconds (optional)
    }
    ```
  - Text Element:
    ```json
    {
      "type": "text",
      "text": "Your text",
      "duration": seconds,
      "fontsize": 70,
      "font": "Arial",
      "color": "white",
      "bg_color": "transparent",
      "position": "center"
    }
    ```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
