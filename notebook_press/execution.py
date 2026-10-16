"""Run Python notebooks with an external kernel, including from frozen apps."""

from pathlib import Path
import os
import shutil
import subprocess
import sys


def default_python() -> str:
    if not getattr(sys, "frozen", False):
        return sys.executable
    return shutil.which("python3" if os.name != "nt" else "python") or shutil.which("python") or ""


def execute_notebook(notebook, source: Path, interpreter: str, timeout: int, log):
    from jupyter_client import AsyncKernelManager
    from jupyter_client.kernelspec import KernelSpec, KernelSpecManager
    from nbclient import NotebookClient

    from .engine import ExportError, external_environment

    language = notebook.metadata.get("language_info", {}).get("name", notebook.metadata.get("kernelspec", {}).get("language", "python"))
    if not str(language).lower().startswith("python"):
        raise ExportError("Run notebook currently supports Python. Use saved outputs for other languages.")
    python = interpreter.strip() or default_python()
    python = shutil.which(python) or str(Path(python).expanduser()) if python else ""
    if not python or not Path(python).is_file():
        raise ExportError("Choose a Python interpreter to generate figures. It needs ipykernel and your notebook's libraries.")
    if getattr(sys, "frozen", False) and Path(python).resolve() == Path(sys.executable).resolve():
        raise ExportError("Choose your Python environment, rather than the Notebook Press executable.")
    environment = external_environment()
    environment["MPLBACKEND"] = "module://matplotlib_inline.backend_inline"
    try:
        probe = subprocess.run([python, "-c", "import ipykernel"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=environment, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ExportError(f"Could not start the selected Python interpreter: {error}") from error
    if probe.returncode:
        raise ExportError(f"The selected Python needs ipykernel. Install it with:\n{python} -m pip install ipykernel\n\n{probe.stderr[-1500:]}")

    class InterpreterSpecs(KernelSpecManager):
        # A frozen executable is not a Python kernel. Do not manufacture a
        # native kernel spec pointing back into the app or rely on registration.
        def get_kernel_spec(self, kernel_name):
            return KernelSpec(argv=[python, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                              language="python", display_name="Notebook Press Python")

    manager = AsyncKernelManager(kernel_name="notebook-press-python",
        kernel_spec_manager=InterpreterSpecs(ensure_native_kernel=False))
    client = NotebookClient(notebook, km=manager, timeout=timeout, startup_timeout=60,
        allow_errors=False, force_raise_errors=True,
        resources={"metadata": {"path": str(source.parent)}},
        on_cell_execute=lambda cell, cell_index: log(f"Running cell {cell_index + 1} of {len(notebook.cells)}…"))
    log(f"Running notebook with {python}. Working folder: {source.parent}")
    try:
        options = {"env": environment, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        client.execute(cleanup_kc=True, **options)
    except Exception as error:
        raise ExportError(f"Notebook execution failed. Check the cell error, Python packages, and data files.\n{error}") from error
    return notebook
