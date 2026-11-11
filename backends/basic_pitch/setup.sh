#!/bin/bash
# Setup script for basic_pitch backend
# Creates venv with Python 3.11, installs dependencies, and fetches weights

set -e

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$BACKEND_DIR/.venv"

# Create venv with Python 3.11 using uv
echo "Creating venv with Python 3.11 using uv..."
if [ ! -d "$VENV_PATH" ]; then
    echo "Creating venv at $VENV_PATH"
    uv venv --python 3.11 "$VENV_PATH"
else
    echo "Venv already exists at $VENV_PATH"
fi

VENV_PYTHON="$VENV_PATH/bin/python"

# Install basic-pitch and its dependencies with pinned versions using uv pip
echo "Installing basic-pitch and dependencies with uv pip..."
uv pip install --python "$VENV_PYTHON" --no-cache-dir \
    basic-pitch==0.4.0 \
    numpy==1.26.4 \
    scipy==1.12.0 \
    librosa==0.10.2 \
    pretty-midi==0.2.11 \
    mir-eval==0.8.2 \
    resampy==0.4.2 \
    onnxruntime==1.16.3 \
    scikit-learn==1.4.2 \
    soundfile==0.12.1 \
    tqdm==4.66.4 \
    typing-extensions==4.11.0 \
    setuptools==69.5.1

# Generate requirements.lock using uv pip freeze
echo "Generating requirements.lock..."
uv pip freeze --python "$VENV_PYTHON" > "$BACKEND_DIR/requirements.lock"

echo "Setup completed successfully!"
echo "Venv location: $VENV_PATH"
echo "Python: $VENV_PYTHON"
echo "Model: Using ONNX model (bundled with basic-pitch package)"
