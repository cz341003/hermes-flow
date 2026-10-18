"""adapters 包：内核后端适配（自研 SQLite / LoopX）。"""
from .loopx_adapter import (
    LoopXBridge,
    LoopXKernel,
    create_kernel,
)

__all__ = ["LoopXBridge", "LoopXKernel", "create_kernel"]
