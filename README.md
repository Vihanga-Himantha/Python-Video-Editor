# Python Video Editor

A JSON-based video editing tool that allows you to create videos by defining scenes, transitions, and audio elements.

## Features

- Create videos from JSON configuration
- Support for multiple resolutions (Full-HD supported)
- Quality presets (low, medium, high)
- Scene transitions with customizable duration and styles
- Support for various media types:
  - Images with auto-resizing
- Audio features:
  - Background music support with volume control
  - Scene-specific voiceovers
  - Multiple audio file format support
- Transition effects:
  - Circle open
  - Wipe up
  - Fade

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

1. Prepare your video_script.json with desired scenes and audio configuration.
2. Place your audio files in the Assets directory.
3. Run the script:

```bash
python create_video.py
```

## JSON Configuration

### Global Settings

```json
{
  "resolution": "full-hd",
  "quality": "high"
}
```

### Audio Configuration

The project supports two types of audio:

1. Global background audio:

```json
{
  "audio": {
    "src": "path/to/audio.mp3",
    "volume": 0.5
  }
}
```

2. Scene-specific voiceovers:

```json
{
  "voiceover": {
    "src": "path/to/voiceover.mp3",
    "volume": 1.0
  }
}
```

### Scene Structure

Each scene can include:

- Comments for description
- Transitions between scenes (circleopen, wipeup, fade)
- Voiceover audio
- Visual elements

Example scene:

```json
{
  "comment": "Scene description",
  "transition": {
    "style": "circleopen|wipeup|fade",
    "duration": 1.5
  },
  "voiceover": {
    "src": "path/to/voiceover.mp3",
    "volume": 1.0
  },
  "elements": [
    {
      "type": "image",
      "src": "image_url",
      "duration": 5
    }
  ]
}
```

## Project Structure

```
├── create_video.py          # Main video creation script
├── video_script.json        # Video configuration file
├── Assets/                  # Audio assets directory
│   ├── background music
│   └── voiceovers
└── README.md
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
