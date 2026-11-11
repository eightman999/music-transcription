#!/bin/bash
# Setup script for transkun backend
# Creates venv with Python 3.11, installs dependencies, and fetches weights

set -e

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="${BACKEND_DIR}/.venv"

# Use Python 3.11 explicitly
if [ ! -d "$VENV_PATH" ]; then
    echo "Creating virtual environment with Python 3.11..."
    uv venv --python 3.11 "$VENV_PATH"
else
    echo "Virtual environment already exists at $VENV_PATH"
fi

# Get the venv Python path
VENV_PYTHON="${VENV_PATH}/bin/python"

echo "Installing dependencies..."
uv pip install --python "$VENV_PYTHON" \
    transkun==2.0.1 \
    torch \
    torchaudio \
    pretty-midi \
    'setuptools<80'

# Generate requirements.lock
echo "Generating requirements.lock..."
uv pip freeze --python "$VENV_PYTHON" > "${BACKEND_DIR}/requirements.lock"

echo "Setup complete!"
echo "Venv: $VENV_PATH"
echo "Python: $VENV_PYTHON"
