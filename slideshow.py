#!/usr/bin/env python3
"""
Narrasjon-synkronisert slideshow generator.
Transkriberer voiceover, matcher bilder til innhold, lager video.

Bruk:
  python3 slideshow.py --audio vo1.mp3 vo2.mp3 --images ./bilder/ --output video.mp4
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from anthropic import Anthropic

client = Anthropic()

SUPPORTED_IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def transcribe(audio_path: str) -> list[dict]:
    """Transcribe audio with word-level timestamps using whisper."""
    try:
        import whisper
    except ImportError:
        print("Installerer openai-whisper...")
        subprocess.run([sys.executable, "-m", "pip", "install", "openai-whisper"], check=True)
        import whisper

    print(f"Transkriberer {Path(audio_path).name}...")
    model = whisper.load_model("base")
    result = model.transcribe(audio_path, word_timestamps=True, language="no")

    segments = []
    for seg in result["segments"]:
        segments.append({
            "start": round(seg["start"], 2),
            "end": round(seg["end"], 2),
            "text": seg["text"].strip()
        })
    return segments


def get_audio_duration(audio_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", audio_path],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def match_images_to_segments(segments: list[dict], image_files: list[str], total_duration: float) -> list[dict]:
    """Ask Claude to match images to transcript segments with durations."""

    image_names = [Path(f).name for f in image_files]
    transcript_text = "\n".join(
        f"[{s['start']}s - {s['end']}s]: {s['text']}" for s in segments
    )

    prompt = f"""Du skal lage en synkronisert slideshow.

TOTAL VARIGHET: {total_duration:.1f} sekunder

TRANSKRIPSJON MED TIDSSTEMPLER:
{transcript_text}

TILGJENGELIGE BILDER:
{json.dumps(image_names, indent=2, ensure_ascii=False)}

Oppgave: Match hvert bilde til den delen av narrasjonen det passer best til, basert på filnavnet.
Hvert bilde skal vises i den tidsperioden narrasjonen snakker om det relevante temaet.
Alle sekunder i lydfilen MÅ dekkes av et bilde. Du kan bruke samme bilde flere ganger.

Returner KUN et JSON-array slik:
[
  {{"image": "filnavn.jpg", "start": 0.0, "duration": 5.5}},
  {{"image": "filnavn2.jpg", "start": 5.5, "duration": 3.2}},
  ...
]

Start alltid på 0.0 og dekk nøyaktig {total_duration:.1f} sekunder totalt."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    # Extract JSON array
    import re
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not match:
        raise ValueError(f"Kunne ikke parse Claude-svar:\n{raw}")
    return json.loads(match.group())


def build_concat_file(timeline: list[dict], image_dir: str, tmp_path: str) -> str:
    """Write FFmpeg concat file."""
    lines = []
    for entry in timeline:
        img_path = os.path.join(image_dir, entry["image"])
        if not os.path.exists(img_path):
            # Try finding it case-insensitively
            for f in os.listdir(image_dir):
                if f.lower() == entry["image"].lower():
                    img_path = os.path.join(image_dir, f)
                    break
        lines.append(f"file '{img_path}'")
        lines.append(f"duration {entry['duration']:.3f}")
    # Repeat last image to avoid ffmpeg concat bug
    if timeline:
        lines.append(f"file '{os.path.join(image_dir, timeline[-1]['image'])}'")

    concat_file = os.path.join(tmp_path, "concat.txt")
    with open(concat_file, "w") as f:
        f.write("\n".join(lines))
    return concat_file


def merge_audio_files(audio_paths: list[str], tmp_path: str) -> str:
    """Merge multiple audio files into one."""
    if len(audio_paths) == 1:
        return audio_paths[0]

    print("Slår sammen lydfiler...")
    list_file = os.path.join(tmp_path, "audio_list.txt")
    with open(list_file, "w") as f:
        for p in audio_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    merged = os.path.join(tmp_path, "merged_audio.mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
         "-c", "copy", merged],
        check=True, capture_output=True
    )
    return merged


def render_video(concat_file: str, audio_file: str, output_path: str):
    """Render final video with FFmpeg."""
    print("Renderer video...")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_file,
        "-i", audio_file,
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k",
        "-map", "0:v", "-map", "1:a",
        "-shortest",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg feil:\n{result.stderr}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Narrasjon-synkronisert slideshow")
    parser.add_argument("--audio", nargs="+", required=True, help="Lydfil(er) i rekkefølge")
    parser.add_argument("--images", required=True, help="Mappe med bilder")
    parser.add_argument("--output", default="slideshow.mp4", help="Utdatafil")
    args = parser.parse_args()

    # Validate
    for a in args.audio:
        if not os.path.exists(a):
            print(f"Finner ikke lydfil: {a}")
            sys.exit(1)
    if not os.path.isdir(args.images):
        print(f"Finner ikke bildemappen: {args.images}")
        sys.exit(1)

    image_files = sorted([
        os.path.join(args.images, f)
        for f in os.listdir(args.images)
        if Path(f).suffix.lower() in SUPPORTED_IMAGES
    ])
    if not image_files:
        print(f"Ingen bilder funnet i {args.images}")
        sys.exit(1)

    print(f"Fant {len(image_files)} bilder")

    with tempfile.TemporaryDirectory() as tmp:
        # Merge audio if multiple files
        merged_audio = merge_audio_files(args.audio, tmp)
        total_duration = get_audio_duration(merged_audio)
        print(f"Total lydvarighet: {total_duration:.1f} sekunder")

        # Transcribe
        all_segments = []
        offset = 0.0
        for audio_path in args.audio:
            segments = transcribe(audio_path)
            for seg in segments:
                seg["start"] += offset
                seg["end"] += offset
            all_segments.extend(segments)
            offset += get_audio_duration(audio_path)

        print(f"\nTranskripsjon ({len(all_segments)} segmenter):")
        for seg in all_segments:
            print(f"  [{seg['start']}s-{seg['end']}s] {seg['text']}")

        # Match images to transcript
        print("\nMatcher bilder til narrasjon med Claude...")
        timeline = match_images_to_segments(all_segments, image_files, total_duration)

        print("\nTimeline:")
        for entry in timeline:
            print(f"  {entry['start']}s ({entry['duration']}s): {entry['image']}")

        # Build concat and render
        concat_file = build_concat_file(timeline, args.images, tmp)
        render_video(concat_file, merged_audio, args.output)

    print(f"\nFerdig! Video lagret som: {args.output}")


if __name__ == "__main__":
    main()
