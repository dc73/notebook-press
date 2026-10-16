"""Native Tk desktop interface; all conversions run in a separate process."""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox

from .engine import ExportError, ExportRequest, source_kind
from .ui import Workspace


def settings_path() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", str(Path.home())))
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return root / "NotebookPress" / "settings.json"


def launcher() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "notebook_press"]


class App(Workspace):
    def __init__(self):
        super().__init__()
        self.title("Notebook Press")
        self.geometry("1180x850")
        self.minsize(1080, 720)
        self.brand_icon = tk.PhotoImage(file=str(Path(__file__).parent / "assets" / "icon-64.png"))
        self.iconphoto(True, self.brand_icon)
        if sys.platform == "win32":
            self.iconbitmap(str(Path(__file__).parent / "assets" / "app.ico"))
        self.process = None
        self.work = None
        self.events_file = None
        self.event_position = 0
        self.result = None
        self.completed = False
        self.cancelled = False
        self.closing = False
        self.settings = {}
        try:
            self.settings = json.loads(settings_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        self.source = tk.StringVar(value=self.settings.get("source", ""))
        self.destination = tk.StringVar(value=self.settings.get("destination", str(Path.home() / "Documents" / "Notebook Press Exports")))
        self.want_pdf = tk.BooleanVar(value=self.settings.get("pdf", True))
        self.want_latex = tk.BooleanVar(value=self.settings.get("latex", True))
        self.include_code = tk.BooleanVar(value=self.settings.get("include_code", True))
        self.pdf_engine = tk.StringVar(value=self.settings.get("pdf_engine", "browser"))
        self.paper = tk.StringVar(value=self.settings.get("paper", "A4"))
        self.book_command = tk.StringVar(value=self.settings.get("book_command", ""))
        self.run_notebook = tk.BooleanVar(value=self.settings.get("execute", False))
        self.python_executable = tk.StringVar(value=self.settings.get("python_executable", ""))
        self.execution_timeout = tk.StringVar(value=str(self.settings.get("execution_timeout", 600)))
        self.source_detail = tk.StringVar(value="Choose a notebook or a Jupyter Book project to begin.")
        self.status = tk.StringVar(value="Ready when you are")
        self._style()
        self._layout()
        self.source.trace_add("write", self._source_changed)
        self._source_changed()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Control-o>", lambda event: self._choose_notebook())
        self.bind("<Control-Return>", lambda event: self._start())
        if sys.platform == "darwin":
            self.bind("<Command-o>", lambda event: self._choose_notebook())
            self.bind("<Command-Return>", lambda event: self._start())

    def _append(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", str(text) + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _choose_notebook(self):
        path = filedialog.askopenfilename(title="Choose a Jupyter notebook", filetypes=[("Jupyter notebook", "*.ipynb")])
        if path:
            self.source.set(path)

    def _choose_book(self):
        path = filedialog.askdirectory(title="Choose the book folder containing its configuration")
        if path:
            self.source.set(path)

    def _choose_destination(self):
        path = filedialog.askdirectory(title="Choose export destination")
        if path:
            self.destination.set(path)

    def _source_changed(self, *_):
        kind = None
        try:
            kind = source_kind(Path(self.source.get()).expanduser())
            label = {"notebook": "Jupyter notebook · saved outputs", "book-v1": "Jupyter Book 1 · Sphinx project", "book-v2": "Jupyter Book 2 / MyST project"}[kind]
            self.source_detail.set(label)
        except ExportError:
            self.source_detail.set("Choose an .ipynb file or a folder with a Jupyter Book configuration.")
        book = kind in {"book-v1", "book-v2"}
        self.engine_picker.configure(state="disabled" if book or not self.want_pdf.get() else "normal")
        self.paper_picker.configure(state="disabled" if book else "normal")
        self.code_check.configure(state="disabled" if book else "normal")
        self.run_check.configure(state="disabled" if book else "normal")
        self._execution_changed(book=book)
        self._source_summary(kind)
        self.engine_hint.configure(text="Book exports use the paper, template, and PDF engine in the book configuration." if book else "Browser uses Chromium. LaTeX typesetting needs TeX.")

    def _request(self):
        try:
            book = source_kind(Path(self.source.get()).expanduser()) != "notebook"
        except ExportError:
            book = False
        try:
            timeout = int(self.execution_timeout.get())
        except ValueError:
            timeout = 0
        return ExportRequest(source=self.source.get(), destination=self.destination.get(), pdf=self.want_pdf.get(),
                             latex=self.want_latex.get(), pdf_engine=self.pdf_engine.get(),
                             include_code=True if book else self.include_code.get(), paper=self.paper.get(),
                             book_command=self.book_command.get().strip(), execute=self.run_notebook.get() and not book,
                             python_executable=self.python_executable.get().strip(), execution_timeout=timeout)

    def _save_settings(self):
        try:
            path = settings_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(asdict(self._request()), indent=2), encoding="utf-8")
        except OSError:
            pass

    def _start(self):
        if self.process:
            return
        request = self._request()
        try:
            request.validate()
        except ExportError as error:
            messagebox.showerror("Choose export settings", str(error), parent=self)
            return
        self._save_settings()
        self._run_job(request)

    def _run_job(self, request=None):
        if self.process:
            return
        self.work = Path(tempfile.mkdtemp(prefix="notebook-press-job-"))
        events = self.work / "events.jsonl"
        args = launcher()
        if request:
            request_file = self.work / "request.json"
            request_file.write_text(json.dumps(asdict(request)), encoding="utf-8")
            args += ["--worker", str(request_file)]
        else:
            args += ["--install-browser"]
        args += ["--events", str(events)]
        self.events_file = events
        self.stage_workspace = None
        self.job_destination = Path(request.destination).expanduser().resolve() if request else None
        self.event_position = 0
        self.completed = self.cancelled = False
        self.result = None
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        try:
            self.process = subprocess.Popen(args, cwd=str(Path(__file__).resolve().parent.parent),
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except OSError as error:
            shutil.rmtree(self.work, ignore_errors=True)
            self.work = None
            messagebox.showerror("Could not start export", str(error), parent=self)
            return
        self._busy(True)
        self.open_button.configure(state="disabled")
        self.overleaf_button.configure(state="disabled")
        self.progress.start()
        self.status.set("Exporting…" if request else "Installing PDF browser…")
        self.after(100, self._poll)

    def _poll(self):
        if not self.process:
            return
        self._read_events()
        if self.process.poll() is None:
            self.after(120, self._poll)
            return
        self._read_events()
        if not self.completed:
            self.status.set("Cancelled" if self.cancelled else "Export stopped unexpectedly. Check Settings & tools.")
            self._append(self.status.get())
        self.process = None
        self.progress.stop()
        self._busy(False)
        self.progress.set(0)
        if self.work:
            shutil.rmtree(self.work, ignore_errors=True)
            self.work = None
        if self.stage_workspace and self.stage_workspace.is_dir():
            # Only remove the exact workspace announced by this job, with its
            # expected name and resolved parent. Never delete a computed root.
            path = self.stage_workspace.resolve()
            if path.parent == self.job_destination and path.name.startswith(".notebook-press-"):
                shutil.rmtree(path, ignore_errors=True)
        if self.closing:
            self.destroy()

    def _read_events(self):
        if not self.events_file.exists():
            return
        with self.events_file.open("rb") as stream:
            stream.seek(self.event_position)
            while True:
                line = stream.readline()
                if not line or not line.endswith(b"\n"):
                    break
                self.event_position = stream.tell()
                try:
                    event = json.loads(line.decode("utf-8"))
                except (ValueError, UnicodeError):
                    continue
                self._append(event.get("message", ""))
                if event["event"] == "workspace":
                    self.stage_workspace = Path(event["path"])
                elif event["event"] == "done":
                    self.completed = True
                    self.result = event.get("path") or None
                    self.status.set(event["message"])
                    if self.result:
                        self._append(self.result)
                        self.open_button.configure(state="normal")
                        self.overleaf_button.configure(state="normal" if (Path(self.result) / "open-in-overleaf.html").is_file() else "disabled")
                elif event["event"] == "error":
                    self.completed = True
                    self.status.set("Export failed — see the log for details")
                    self._append(event.get("detail", ""))
                    if not self.details_visible:
                        self._toggle_details()

    def _cancel(self):
        if not self.process:
            return
        import psutil

        self.cancelled = True
        self.status.set("Cancelling…")
        try:
            parent = psutil.Process(self.process.pid)
            children = parent.children(recursive=True)
            for child in reversed(children):
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            parent.kill()
        except psutil.NoSuchProcess:
            pass

    def _open_result(self):
        if self.result:
            if sys.platform == "win32":
                os.startfile(self.result)
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", self.result])

    def _open_overleaf(self):
        if self.result:
            page = Path(self.result) / "open-in-overleaf.html"
            if page.is_file():
                webbrowser.open(page.resolve().as_uri())

    def _choose_python(self):
        path = filedialog.askopenfilename(title="Choose your Python interpreter",
            filetypes=[("Python executable", "*.exe"), ("All files", "*")] if os.name == "nt" else [("All files", "*")])
        if path:
            self.python_executable.set(path)

    def _close(self):
        self._save_settings()
        if self.process:
            self.closing = True
            self._cancel()
        else:
            self.destroy()
