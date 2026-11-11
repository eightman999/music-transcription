"""Backend registry and execution."""

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Discover backends automatically: every backends/<name>/run.py is a backend
_BACKEND_REGISTRY: Dict[str, Path] = {}


def _discover_backends():
    """Discover all backends in the backends directory."""
    global _BACKEND_REGISTRY
    
    if _BACKEND_REGISTRY:
        return  # Already discovered
    
    # Get the repository root (parent of mt directory)
    repo_root = Path(__file__).resolve().parents[1]
    backends_dir = repo_root / "backends"
    
    if backends_dir.exists():
        for backend_dir in backends_dir.iterdir():
            if backend_dir.is_dir():
                run_script = backend_dir / "run.py"
                if run_script.exists():
                    backend_name = backend_dir.name
                    _BACKEND_REGISTRY[backend_name] = run_script


def register_backend(name: str, run_script: str) -> None:
    """Register a backend manually.
    
    Args:
        name: Backend name (e.g., "naive")
        run_script: Path to run.py
    """
    _BACKEND_REGISTRY[name] = Path(run_script)


def get_backend_python(backend_name: str) -> str:
    """Get the Python executable for a backend.
    
    If backends/<name>/.venv/bin/python exists, use it.
    Otherwise, use the core .venv/bin/python.
    """
    # Get the repository root
    repo_root = Path(__file__).resolve().parents[1]
    
    backend_venv = repo_root / "backends" / backend_name / ".venv" / "bin" / "python"
    if backend_venv.exists():
        return str(backend_venv)
    
    core_venv = repo_root / ".venv" / "bin" / "python"
    if core_venv.exists():
        return str(core_venv)
    
    return "python"  # fallback


def run_backend(
    backend_name: str,
    wav_path: str,
    out_json: str,
) -> Tuple[float, float]:
    """Run a backend as a separate process.
    
    Args:
        backend_name: Name of the backend
        wav_path: Input WAV file path
        out_json: Output JSON file path
    
    Returns:
        Tuple of (wall_time_seconds, peak_rss_mb)
    
    Raises:
        ValueError: If backend is unknown
        RuntimeError: If backend fails (non-zero exit code)
    """
    # Discover backends if not already done
    if not _BACKEND_REGISTRY:
        _discover_backends()
    
    if backend_name not in _BACKEND_REGISTRY:
        raise ValueError(f"Unknown backend: {backend_name}")
    
    run_script = _BACKEND_REGISTRY[backend_name]
    python_exec = get_backend_python(backend_name)
    
    # Build command
    cmd = [python_exec, str(run_script), wav_path, out_json]
    
    # Start time
    start_time = time.time()
    
    # Run the backend as a subprocess
    import platform
    import os
    is_mac = platform.system() == 'Darwin'
    
    # Start the process
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    
    # Wait for the process to finish and get resource usage
    pid = proc.pid
    
    # Use os.wait4 to get resource usage before reaping the process
    # On macOS: ru_maxrss is in bytes
    # On Linux: ru_maxrss is in kilobytes
    try:
        _, status, rusage = os.wait4(pid, 0)
        if is_mac:
            peak_rss_bytes = rusage.ru_maxrss
        else:
            peak_rss_bytes = rusage.ru_maxrss * 1024
    except (AttributeError, OSError):
        # Fallback for systems without os.wait4
        # Wait for process to finish
        stdout, stderr = proc.communicate()
        
        # Try resource.getrusage for children
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_CHILDREN)
            if is_mac:
                peak_rss_bytes = usage.ru_maxrss
            else:
                peak_rss_bytes = usage.ru_maxrss * 1024
        except Exception:
            peak_rss_bytes = 0
        
        # Read stdout/stderr
        stdout = proc.stdout.read() if proc.stdout else ""
        stderr = proc.stderr.read() if proc.stderr else ""
    else:
        # Successfully got resource usage via os.wait4
        # Now read stdout/stderr from the process
        stdout, stderr = proc.communicate()
    
    end_time = time.time()
    wall_time = end_time - start_time
    
    # Convert to MB
    peak_rss_mb = peak_rss_bytes / (1024 * 1024)
    
    # Check exit code
    if proc.returncode != 0:
        # Get last lines of stderr
        stderr_lines = stderr.split('\n') if stderr else []
        last_lines = '\n'.join(stderr_lines[-5:]) if len(stderr_lines) > 5 else stderr
        raise RuntimeError(
            f"Backend {backend_name} failed with exit code {proc.returncode}. "
            f"stderr: {last_lines}"
        )
    
    # Ensure output file exists
    if not os.path.exists(out_json):
        raise RuntimeError(f"Backend {backend_name} did not create output file {out_json}")
    
    return wall_time, peak_rss_mb


def list_backends() -> List[str]:
    """List all registered backends."""
    if not _BACKEND_REGISTRY:
        _discover_backends()
    return list(_BACKEND_REGISTRY.keys())


# Auto-discover backends on import
_discover_backends()
