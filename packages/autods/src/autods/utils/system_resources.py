import os
import platform
import subprocess
from shutil import which

import psutil
from pydantic import BaseModel


class GPUInfo(BaseModel):
    available: bool
    type: str
    count: int
    names: list[str]


class MemoryInfo(BaseModel):
    total: int | None
    available: int | None


class SystemInfo(BaseModel):
    cpu_count: int | None
    gpu: GPUInfo
    memory: MemoryInfo
    os_system: str


def get_memory_info() -> MemoryInfo:
    """Get memory information in GB using psutil (primary) with basic fallback."""
    try:
        mem = psutil.virtual_memory()
        return MemoryInfo(
            total=int(mem.total / (1024**3)),
            available=int(mem.available / (1024**3)),
        )
    except Exception:
        pass

    return MemoryInfo(total=None, available=None)


def nvidia_gpus() -> tuple[int, list[str]]:
    """Detect NVIDIA GPUs via nvidia-smi or PyTorch."""
    if which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "-L"], capture_output=True, text=True, timeout=1.5
            )
            if out.returncode == 0 and out.stdout:
                lines = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
                count = len(lines)
                names = []
                for ln in lines:
                    try:
                        after_colon = ln.split(":", 1)[1].strip()
                        name = after_colon.split("(")[0].strip()
                        names.append(name)
                    except Exception:
                        names.append(ln)
                return count, names
        except Exception:
            pass

    try:
        import torch

        if torch.cuda.is_available():
            count = torch.cuda.device_count()
            names = [torch.cuda.get_device_name(i) for i in range(count)]
            return count, names
    except Exception:
        pass

    return 0, []


def mac_gpu_available() -> bool:
    """Detect Apple MPS availability."""
    try:
        import torch

        return bool(
            getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()
        )
    except Exception:
        return platform.system() == "Darwin" and platform.machine() in {
            "arm64",
            "aarch64",
        }


def get_system_info() -> SystemInfo:
    """Get comprehensive system information."""
    n_count, n_names = nvidia_gpus()
    mps_available = mac_gpu_available()
    memory_info = get_memory_info()

    # GPU info with NVIDIA priority over MPS
    if n_count > 0:
        gpu_info = GPUInfo(
            available=True,
            type="nvidia",
            count=n_count,
            names=n_names,
        )
    elif mps_available:
        gpu_info = GPUInfo(
            available=True,
            type="mps",
            count=1,
            names=["Apple MPS"],
        )
    else:
        gpu_info = GPUInfo(available=False, type="none", count=0, names=[])

    return SystemInfo(
        cpu_count=os.cpu_count(),
        gpu=gpu_info,
        memory=memory_info,
        os_system=platform.system(),
    )
