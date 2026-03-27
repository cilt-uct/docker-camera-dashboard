#!/bin/bash
set -euo pipefail

RTSP_URL="$1"
CAMERA_NAME="$2"
OUTPUT_IMAGE="$3"
THUMB_IMAGE="$4"
LOGFILE="$5"

# Hard timeout in seconds
CAPTURE_TIMEOUT=15

# Thumbnail size for UI
THUMB_WIDTH=640
THUMB_HEIGHT=480

# Temp files (same filesystem = atomic mv)
TMP_FULL="$(dirname "$OUTPUT_IMAGE")/.tmp_$(basename "$OUTPUT_IMAGE")"
TMP_THUMB="$(dirname "$THUMB_IMAGE")/.tmp_$(basename "$THUMB_IMAGE")"

# Capture full-resolution frame with timeout + low latency
timeout "${CAPTURE_TIMEOUT}" ffmpeg \
  -rtsp_transport tcp \
  -fflags nobuffer \
  -flags low_delay \
  -analyzeduration 500000 \
  -probesize 500000 \
  -i "$RTSP_URL" \
  -frames:v 1 -q:v 2 -update 1 \
  -vf "drawtext=text='${CAMERA_NAME}  %{localtime}':\
       x=10:y=10:\
       fontsize=min(w\,h)/40:\
       fontcolor=white:\
       box=1:boxcolor=black@0.5:\
       boxborderw=min(w\,h)/150" \
  "$TMP_FULL" \
  > "$LOGFILE" 2>&1 || {
    echo "$(date) ERROR: Capture timed out or failed" >> "$LOGFILE"
    rm -f "$TMP_FULL"
    exit 1
  }

# Atomic move for full image
mv -f "$TMP_FULL" "$OUTPUT_IMAGE"

# Generate thumbnail (aspect-safe, padded)
ffmpeg -y -i "$OUTPUT_IMAGE" \
  -vf "scale=${THUMB_WIDTH}:${THUMB_HEIGHT}:force_original_aspect_ratio=decrease,\
       pad=${THUMB_WIDTH}:${THUMB_HEIGHT}:(ow-iw)/2:(oh-ih)/2" \
  -q:v 3 \
  "$TMP_THUMB" \
  >> "$LOGFILE" 2>&1

# Atomic replace of thumbnail
mv -f "$TMP_THUMB" "$THUMB_IMAGE"
