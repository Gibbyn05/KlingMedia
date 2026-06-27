#!/usr/bin/env python3
"""
Claude-powered video editor using FFmpeg.
Usage: python editor.py <video_file> "<prompt>"
Example: python editor.py clip.mp4 "klipp fra 0:10 til 0:30 og legg til tekst 'Hei verden' øverst"
"""

import sys
import os
import subprocess
import json
import re
from anthropic import Anthropic

client = Anthropic()

SYSTEM_PROMPT = """
You are a video editing assistant. The user will describe what they want to do to a video in natural language (Norwegian or English).
Your job is to translate their request into valid FFmpeg shell commands.

Rules:
- Always use 'input.mp4' as the input filename placeholder
- Always use 'output.mp4' as the output filename
- Return ONLY a JSON object with this structure:
  {"commands": ["ffmpeg command here"], "description": "kort beskrivelse av hva som gjøres"}
- If multiple steps are needed, list multiple commands in order
- For text overlays, use the drawtext filter
- For cuts, use -ss and -to or -t flags
- For speed changes, use the setpts filter
- For audio removal, use -an
- Do not include any explanation outside the JSON

Common operations:
- Clip/cut: ffmpeg -i input.mp4 -ss HH:MM:SS -to HH:MM:SS -c copy output.mp4
- Add text: ffmpeg -i input.mp4 -vf "drawtext=text='TEXT':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=50" output.mp4
- Remove audio: ffmpeg -i input.mp4 -c:v copy -an output.mp4
- Speed up 2x: ffmpeg -i input.mp4 -vf "setpts=0.5*PTS" -af "atempo=2.0" output.mp4
- Rotate 90°: ffmpeg -i input.mp4 -vf "transpose=1" output.mp4
- Resize to 1080p: ffmpeg -i input.mp4 -vf scale=1920:1080 output.mp4
- Add fade in: ffmpeg -i input.mp4 -vf "fade=t=in:st=0:d=1" output.mp4
- Mute and add music: ffmpeg -i input.mp4 -i music.mp3 -c:v copy -map 0:v -map 1:a -shortest output.mp4
"""


def parse_time(t):
    """Convert M:SS or H:MM:SS to seconds for display."""
    parts = t.strip().split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return float(t)


def get_ffmpeg_commands(prompt, input_file):
    """Ask Claude to convert a natural language prompt to FFmpeg commands."""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": f'Video file: {input_file}\nRequest: {prompt}'}
        ]
    )

    raw = response.content[0].text.strip()

    # Extract JSON even if Claude wraps it in markdown
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        raise ValueError(f"Could not parse Claude response:\n{raw}")

    data = json.loads(match.group())
    return data


def run_commands(commands, input_file):
    """Execute FFmpeg commands, replacing placeholder filenames."""
    base, ext = os.path.splitext(input_file)
    output_file = f"{base}_edited{ext}"

    for cmd in commands:
        cmd = cmd.replace("input.mp4", input_file)
        cmd = cmd.replace("output.mp4", output_file)
        print(f"\nKjører: {cmd}")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Feil:\n{result.stderr}")
            sys.exit(1)

    return output_file


def main():
    if len(sys.argv) < 3:
        print("Bruk: python editor.py <videofil> \"<prompt>\"")
        print("Eks:  python editor.py video.mp4 \"klipp fra 0:10 til 0:30\"")
        sys.exit(1)

    input_file = sys.argv[1]
    prompt = sys.argv[2]

    if not os.path.exists(input_file):
        print(f"Finner ikke fil: {input_file}")
        sys.exit(1)

    print(f"Videofil: {input_file}")
    print(f"Prompt:   {prompt}")
    print("\nSpør Claude om FFmpeg-kommandoer...")

    result = get_ffmpeg_commands(prompt, input_file)
    print(f"\nBeskrivelse: {result['description']}")
    print(f"Kommandoer:  {result['commands']}")

    output = run_commands(result["commands"], input_file)
    print(f"\nFerdig! Lagret som: {output}")


if __name__ == "__main__":
    main()
