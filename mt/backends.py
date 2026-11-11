"""Backend registry and execution."""

import json
import os
import subprocess
import time
import resource
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Backend registry: name -> command template
# Command is: <python> <run_script> <in.wav> <out.json>
_BACKEND_REGISTRY: Dict[str, str] = {}


def register_backend(name: str, run_script: str) -> None:
    """Register a backend.
    
    Args:
        name: Backend name (e.g., "naive")
        run_script: Path to run.py relative to repo root or absolute
    """
    _BACKEND_REGISTRY[name] = run_script


def get_backend_python(backend_name: str) -> str:
    """Get the Python executable for a backend.
    
    If backends/<name>/.venv/bin/python exists, use it.
    Otherwise, use the core .venv/bin/python.
    """
    backend_venv = Path(f"backends/{backend_name}/.venv/bin/python")
    if backend_venv.exists():
        return str(backend_venv)
    
    core_venv = Path(".venv/bin/python")
    if core_venv.exists():
        return str(core_venv)
    
    return "python"  # fallback


def run_backend(
    backend_name: str,
    wav_path: str,
    out_json: str,
) -> Tuple[float, int]:
    """Run a backend as a separate process.
    
    Args:
        backend_name: Name of the backend
        wav_path: Input WAV file path
        out_json: Output JSON file path
    
    Returns:
        Tuple of (wall_time_seconds, peak_rss_kb)
    """
    if backend_name not in _BACKEND_REGISTRY:
        raise ValueError(f"Unknown backend: {backend_name}")
    
    run_script = _BACKEND_REGISTRY[backend_name]
    python_exec = get_backend_python(backend_name)
    
    # Build command
    cmd = [python_exec, run_script, wav_path, out_json]
    
    # Get peak RSS before starting
    def get_rss():
        try:
            return resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        except (AttributeError, ValueError):
            # On macOS, ru_maxrss is in bytes
            try:
                return resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss // 1024
            except:
                return 0
    
    start_rss = get_rss()
    start_time = time.time()
    
    # Run the backend
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
    )
    
    end_time = time.time()
    end_rss = get_rss()
    
    wall_time = end_time - start_time
    peak_rss_kb = max(end_rss, start_rss) - start_rss
    
    # Ensure output file exists
    if not os.path.exists(out_json):
        raise RuntimeError(f"Backend {backend_name} did not create output file {out_json}")
    
    return wall_time, peak_rss_kb


def list_backends() -> List[str]:
    """List all registered backends."""
    return list(_BACKEND_REGISTRY.keys())


# Auto-register built-in backends
# This will be called when the module is imported
# We register the naive backend by default
try:
    naive_script = Path("backends/naive/run.py")
    if naive_script.exists():
        register_backend("naive", str(naive_script))
except:
    pass
