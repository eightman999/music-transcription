#!/bin/bash
# Kong backend setup script
# Creates venv with Python 3.11, installs dependencies, verifies checkpoint at data/models/kong/

set -e

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$(dirname "$BACKEND_DIR")")"
VENV_PATH="$BACKEND_DIR/.venv"

# Use MT_MODELS_DIR if set, otherwise default to repo data/models
MODEL_DIR="${MT_MODELS_DIR:-$REPO_ROOT/data/models}/kong"
CHECKPOINT_FILE="CRNN_note_F1=0.9677_pedal_F1=0.9186.pth"
CHECKPOINT_URL="https://zenodo.org/record/4034264/files/CRNN_note_F1%3D0.9677_pedal_F1%3D0.9186.pth?download=1"
EXPECTED_SIZE=171966578
EXPECTED_SHA256="c3fa9730725bf4a762f1c14bc80cd5986eacda01b026f5a4a2525cd607876141"

echo "=== Kong Backend Setup ==="
echo "Backend dir: $BACKEND_DIR"
echo "Venv path: $VENV_PATH"
echo "Model dir: $MODEL_DIR"

# Create venv with Python 3.11
if [ ! -d "$VENV_PATH" ]; then
    echo "Creating venv with Python 3.11..."
    uv venv --python 3.11 "$VENV_PATH"
else
    echo "Venv already exists at $VENV_PATH"
fi

# Create model directory if it doesn't exist
mkdir -p "$MODEL_DIR"

# Checkpoint path
CHECKPOINT_PATH="$MODEL_DIR/$CHECKPOINT_FILE"

# Download checkpoint if it doesn't exist or has wrong size/sha256
if [ ! -f "$CHECKPOINT_PATH" ]; then
    echo "Checkpoint not found at $CHECKPOINT_PATH"
    echo "Attempting to download from $CHECKPOINT_URL..."
    # Try to download - this may fail in sandbox if data/ points outside workspace
    if curl -L -o "$CHECKPOINT_PATH" "$CHECKPOINT_URL" 2>/dev/null; then
        echo "Download complete"
    else
        echo "ERROR: Failed to download checkpoint to $CHECKPOINT_PATH"
        echo "The data/models/ directory may be outside the sandbox write area."
        echo "Please ensure the checkpoint file exists at:"
        echo "  $CHECKPOINT_PATH"
        echo "You can download it manually from:"
        echo "  $CHECKPOINT_URL"
        exit 1
    fi
elif [ "$(stat -f%z "$CHECKPOINT_PATH" 2>/dev/null || stat -c%s "$CHECKPOINT_PATH" 2>/dev/null)" -ne "$EXPECTED_SIZE" ]; then
    echo "Checkpoint exists but has wrong size, redownloading..."
    rm "$CHECKPOINT_PATH"
    if curl -L -o "$CHECKPOINT_PATH" "$CHECKPOINT_URL" 2>/dev/null; then
        echo "Download complete"
    else
        echo "ERROR: Failed to download checkpoint"
        exit 1
    fi
else
    echo "Checkpoint already exists with correct size"
fi

# Verify SHA256 checksum
ACTUAL_SHA256=$(sha256sum "$CHECKPOINT_PATH" 2>/dev/null | awk '{print $1}' || shasum -a 256 "$CHECKPOINT_PATH" 2>/dev/null | awk '{print $1}')
if [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
    echo "ERROR: SHA256 checksum mismatch!"
    echo "Expected: $EXPECTED_SHA256"
    echo "Actual:   $ACTUAL_SHA256"
    echo "The downloaded file may be corrupted."
    exit 1
fi

echo "Checkpoint verified (SHA256: $ACTUAL_SHA256)"

# Install dependencies with uv pip
VENV_PYTHON="$VENV_PATH/bin/python"
echo "Installing dependencies with uv pip..."

uv pip install --python "$VENV_PYTHON" \
    torch \
    piano-transcription-inference==0.0.6 \
    librosa==0.10.1 \
    numpy==1.24.4 \
    scipy==1.11.4 \
    soundfile \
    mido \
    matplotlib \
    torchlibrosa \
    audioread \
    ffmpeg-python \
    'setuptools<80'

echo "Dependencies installed"

# Generate requirements.lock using uv pip freeze
uv pip freeze --python "$VENV_PYTHON" > "$BACKEND_DIR/requirements.lock"

echo "=== Kong Backend Setup Complete ==="
echo "Checkpoint: $CHECKPOINT_PATH"
echo "Venv: $VENV_PATH"
