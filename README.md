# Claude Video Editor

Rediger videoer med naturlige prompts på norsk eller engelsk — Claude oversetter til FFmpeg.

## Krav

- Python 3.9+
- FFmpeg installert (`brew install ffmpeg` / `apt install ffmpeg`)
- Anthropic API-nøkkel

## Installasjon

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="din-nøkkel-her"
```

## Bruk

```bash
python editor.py <videofil> "<prompt>"
```

## Eksempler

```bash
# Klipp ut et segment
python editor.py video.mp4 "klipp fra 0:10 til 0:30"

# Legg til tekst
python editor.py video.mp4 "legg til teksten 'Hei verden' øverst i 10 sekunder"

# Fjern lyd
python editor.py video.mp4 "fjern lyden"

# Dobbel hastighet
python editor.py video.mp4 "gjør videoen dobbelt så rask"

# Roter
python editor.py video.mp4 "roter 90 grader"

# Resize
python editor.py video.mp4 "skaler til 1080p"

# Kombiner
python editor.py video.mp4 "klipp fra 0:05 til 0:45 og legg til fade inn i starten"
```

Utdatafilen lagres automatisk som `<original>_edited.mp4`.
