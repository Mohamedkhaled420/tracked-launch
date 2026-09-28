#!/usr/bin/env bash
# /home/z/my-project/scripts/brag_vo.sh
# Generates 5 voiceover lines via z-ai TTS (jam voice, deadpan English gentleman)
set -euo pipefail

AUDIO_DIR="${BRAG_OUT}/work/audio"
mkdir -p "$AUDIO_DIR"

declare -a LINES=(
  "It tracks things."
  "So you don't have to think about things."
  "The line goes up."
  "tracked."
  "Backed by people you've heard of."
)

for i in "${!LINES[@]}"; do
  n=$((i+1))
  line="${LINES[$i]}"
  out="${AUDIO_DIR}/vo_${n}.wav"
  echo "[$n/5] generating: $line"
  z-ai tts -i "$line" -o "$out" --voice jam --speed 0.92 --format wav 2>&1 | tail -2
done

echo "--- generated VO lines ---"
for i in 1 2 3 4 5; do
  f="${AUDIO_DIR}/vo_${i}.wav"
  dur=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$f")
  printf "  vo_%d.wav  duration=%ss\n" "$i" "$dur"
done
