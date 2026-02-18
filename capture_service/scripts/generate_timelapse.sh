#!/bin/bash
set -euo pipefail

# ---- Inputs ----
IMAGE_DIR="$1"
CAMERA_NAME="$2"
OUTPUT_BASENAME="$3"   # without extension
LOGFILE="$4"

# ---- Config ----
MAX_FRAMES=288
FPS=10
TARGET_W=640
TARGET_H=360
DEFAULT_CRF=30          # global CRF for both WebM and MP4

# ---- Temp files for atomic writes ----
IMAGE_LIST=$(mktemp)
TMP_WEBM="$(dirname "$OUTPUT_BASENAME")/.tmp_$(basename "$OUTPUT_BASENAME").webm"
TMP_MP4="$(dirname "$OUTPUT_BASENAME")/.tmp_$(basename "$OUTPUT_BASENAME").mp4"
TMP_POSTER="$(dirname "$OUTPUT_BASENAME")/.tmp_$(basename "$OUTPUT_BASENAME").jpg"

CONCAT_FILE=$(mktemp)

while read -r img; do
    echo "file '$img'" >> "$CONCAT_FILE"
    echo "duration $(echo "1/$FPS" | bc -l)" >> "$CONCAT_FILE"
done < "$IMAGE_LIST"

# Repeat last image (required by ffmpeg)
LAST_IMAGE=$(tail -n1 "$IMAGE_LIST")
echo "file '$LAST_IMAGE'" >> "$CONCAT_FILE"

cleanup() {
  rm -f "$IMAGE_LIST" "$TMP_WEBM" "$TMP_MP4" "$TMP_POSTER"
}
trap cleanup EXIT

# ---- Build sorted list of recent images ----
find "$IMAGE_DIR" -type f -name "*.jpg" -mtime -1 | sort | tail -n "$MAX_FRAMES" > "$IMAGE_LIST"

if [[ ! -s "$IMAGE_LIST" ]]; then
  echo "$(date) ERROR: No images found" >> "$LOGFILE"
  exit 1
fi

# ---- Generate poster thumbnail (first image) ----
FIRST_IMAGE=$(head -n1 "$IMAGE_LIST")
ffmpeg -y -i "$FIRST_IMAGE" \
  -vf "scale=${TARGET_W}:${TARGET_H}:force_original_aspect_ratio=decrease,\
       pad=${TARGET_W}:${TARGET_H}:(ow-iw)/2:(oh-ih)/2" \
  -q:v 2 \
  "$TMP_POSTER" >> "$LOGFILE" 2>&1

# ---- Generate WebM ----
ffmpeg -y \
  -f concat -safe 0 \
  -i "$CONCAT_FILE" \
  -vf "scale=${TARGET_W}:${TARGET_H}:force_original_aspect_ratio=decrease,\
       pad=${TARGET_W}:${TARGET_H}:(ow-iw)/2:(oh-ih)/2" \
  -c:v libvpx-vp9 \
  -b:v 0 \
  -crf "$DEFAULT_CRF" \
  -pix_fmt yuv420p \
  -row-mt 1 \
  -deadline good \
  -an \
  "$TMP_WEBM" >> "$LOGFILE" 2>&1


# ---- Generate MP4 fallback ----
ffmpeg -y \
  -f concat -safe 0 \
  -i <(awk '{print "file \x27" $0 "\x27"}' "$IMAGE_LIST") \
  -vf "scale=${TARGET_W}:${TARGET_H}:force_original_aspect_ratio=decrease,\
       pad=${TARGET_W}:${TARGET_H}:(ow-iw)/2:(oh-ih)/2" \
  -r "$FPS" \
  -c:v libx264 \
  -preset veryfast \
  -crf "$DEFAULT_CRF" \
  -pix_fmt yuv420p \
  "$TMP_MP4" >> "$LOGFILE" 2>&1

# ---- Atomic replacement ----
mv -f "$TMP_WEBM" "${OUTPUT_BASENAME}.webm"
mv -f "$TMP_MP4" "${OUTPUT_BASENAME}.mp4"
mv -f "$TMP_POSTER" "${OUTPUT_BASENAME}.jpg"
