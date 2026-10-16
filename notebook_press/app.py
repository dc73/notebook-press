"""Native Tk desktop interface; all conversions run in a separate process."""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .engine import ExportError, ExportRequest, dependency_report, source_kind

BG = "#F4F3EE"
INK = "#202D2A"
MUTED = "#66736E"
GREEN = "#245D4D"
PANEL = "#FFFFFF"


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


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Notebook Press")
        self.geometry("1020x820")
        self.minsize(880, 760)
        self.configure(bg=BG)
        self.brand_icon = tk.PhotoImage(file=str(Path(__file__).parent / "assets" / "icon-64.png"))
        self.iconphoto(True, self.brand_icon)
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

    def _style(self):
        self.option_add("*Font", ("Segoe UI" if sys.platform == "win32" else "Helvetica", 10))
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=INK)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Card.TLabel", background=PANEL, foreground=INK)
        style.configure("CardMuted.TLabel", background=PANEL, foreground=MUTED)
        style.configure("TButton", padding=(14, 9), background="#E8EAE4", foreground=INK, borderwidth=0)
        style.map("TButton", background=[("active", "#DCE3DC")])
        style.configure("Primary.TButton", background=GREEN, foreground="white", font=("Helvetica", 11, "bold"))
        style.map("Primary.TButton", background=[("active", "#194335"), ("disabled", "#ABBDB5")])
        style.configure("TEntry", padding=8, fieldbackground="#FAFBF8", bordercolor="#D5DDD6")
        style.configure("TCheckbutton", background=PANEL, foreground=INK, padding=5)
        style.map("TCheckbutton", background=[("active", PANEL)])
        style.configure("TCombobox", padding=6, fieldbackground="#FAFBF8")
        style.configure("TProgressbar", background=GREEN, troughcolor="#E0E6DF", borderwidth=0)

    def _layout(self):
        sidebar = tk.Frame(self, bg=INK, width=194)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(sidebar, image=self.brand_icon, bg=INK).pack(anchor="w", padx=25, pady=(26, 10))
        tk.Label(sidebar, text="NOTEBOOK\nPRESS", justify="left", fg="white", bg=INK, font=("Helvetica", 17, "bold")).pack(anchor="w", padx=25)
        tk.Label(sidebar, text="From working notes\nto finished pages.", justify="left", fg="#B9C9C1", bg=INK, font=("Helvetica", 10), pady=24).pack(anchor="w", padx=25)
        tk.Frame(sidebar, height=1, bg="#40534B").pack(fill="x", padx=25, pady=12)
        tk.Label(sidebar, text="01   Choose source\n\n02   Set your formats\n\n03   Export & share", justify="left", fg="#D4DFD7", bg=INK).pack(anchor="w", padx=25, pady=16)
        tk.Button(sidebar, text="Setup & tools  ↗", command=self._setup, bg="#32483F", fg="white", activebackground=GREEN, activeforeground="white", relief="flat", padx=12, pady=10, cursor="hand2").pack(side="bottom", fill="x", padx=20, pady=(10, 28))
        tk.Label(sidebar, text=f"WINDOWS · MAC · LINUX\nv{__version__}", justify="left", fg="#9AAFA4", bg=INK, font=("Helvetica", 8)).pack(side="bottom", anchor="w", padx=25, pady=10)
        main = ttk.Frame(self, padding=(30, 26))
        main.pack(side="left", fill="both", expand=True)
        ttk.Label(main, text="THE EXPORT DESK", style="Muted.TLabel", font=("Helvetica", 9, "bold")).pack(anchor="w")
        ttk.Label(main, text="Make it a document.", font=("Helvetica", 27, "bold")).pack(anchor="w", pady=(7, 5))
        ttk.Label(main, text="Turn notebooks and books into PDF and editable LaTeX.", style="Muted.TLabel").pack(anchor="w", pady=(0, 20))

        source_card = self._card(main, "01", "Your source")
        row = ttk.Frame(source_card, style="Card.TFrame")
        row.pack(fill="x", pady=(8, 6))
        ttk.Entry(row, textvariable=self.source).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Notebook…", command=self._choose_notebook).pack(side="left", padx=(8, 4))
        ttk.Button(row, text="Book folder…", command=self._choose_book).pack(side="left")
        ttk.Label(source_card, textvariable=self.source_detail, style="CardMuted.TLabel", wraplength=650).pack(anchor="w")

        options = self._card(main, "02", "Export options")
        row = ttk.Frame(options, style="Card.TFrame")
        row.pack(fill="x", pady=(6, 5))
        ttk.Checkbutton(row, text="PDF document", variable=self.want_pdf).pack(side="left", padx=(0, 22))
        ttk.Checkbutton(row, text="LaTeX source + figures", variable=self.want_latex).pack(side="left")
        row = ttk.Frame(options, style="Card.TFrame")
        row.pack(fill="x", pady=(3, 6))
        ttk.Label(row, text="PDF engine", style="Card.TLabel").pack(side="left", padx=(0, 10))
        self.engine_picker = ttk.Combobox(row, textvariable=self.pdf_engine, values=("browser", "latex"), state="readonly", width=12)
        self.engine_picker.pack(side="left")
        ttk.Label(row, text="Paper", style="Card.TLabel").pack(side="left", padx=(20, 8))
        self.paper_picker = ttk.Combobox(row, textvariable=self.paper, values=("A4", "Letter"), state="readonly", width=8)
        self.paper_picker.pack(side="left")
        self.code_check = ttk.Checkbutton(row, text="Include code", variable=self.include_code)
        self.code_check.pack(side="left", padx=(12, 0))
        self.engine_hint = ttk.Label(options, text="Browser PDF needs Chromium; LaTeX PDF needs a TeX installation.", style="CardMuted.TLabel", wraplength=650)
        self.engine_hint.pack(anchor="w", pady=(0, 6))
        row = ttk.Frame(options, style="Card.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text="Save to", style="Card.TLabel").pack(side="left", padx=(0, 10))
        ttk.Entry(row, textvariable=self.destination).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse…", command=self._choose_destination).pack(side="left", padx=(8, 0))

        action = ttk.Frame(main)
        action.pack(fill="x", pady=(3, 10))
        self.export_button = ttk.Button(action, text="Export documents  →", style="Primary.TButton", command=self._start)
        self.export_button.pack(side="left")
        self.cancel_button = ttk.Button(action, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=8)
        self.open_button = ttk.Button(action, text="Open export folder", command=self._open_result, state="disabled")
        self.open_button.pack(side="right")
        self.progress = ttk.Progressbar(main, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 9))
        ttk.Label(main, textvariable=self.status).pack(anchor="w", pady=(0, 7))
        log_frame = ttk.Frame(main)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, height=7, bg="#EAEDE6", fg="#40544B", relief="flat", borderwidth=0,
                           padx=12, pady=10, font=("Consolas" if sys.platform == "win32" else "Courier", 9), wrap="word", state="disabled")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)
        self._append("Saved cell outputs are used. Run and save your notebook before exporting.\nEach export gets its own folder.")

    def _card(self, parent, number, title):
        card = ttk.Frame(parent, style="Card.TFrame", padding=17)
        card.pack(fill="x", pady=(0, 13))
        ttk.Label(card, text=f"{number}  /  {title}", style="Card.TLabel", font=("Helvetica", 12, "bold")).pack(anchor="w")
        return card

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
        self.engine_picker.configure(state="disabled" if book else "readonly")
        self.paper_picker.configure(state="disabled" if book else "readonly")
        self.code_check.configure(state="disabled" if book else "normal")
        self.engine_hint.configure(text="Book exports use the paper, template, and PDF engine in the book configuration." if book else "Browser PDF needs Chromium; LaTeX PDF needs a TeX installation.")

    def _request(self):
        try:
            book = source_kind(Path(self.source.get()).expanduser()) != "notebook"
        except ExportError:
            book = False
        return ExportRequest(source=self.source.get(), destination=self.destination.get(), pdf=self.want_pdf.get(),
                             latex=self.want_latex.get(), pdf_engine=self.pdf_engine.get(),
                             include_code=True if book else self.include_code.get(), paper=self.paper.get(),
                             book_command=self.book_command.get().strip())

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
        self.export_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.open_button.configure(state="disabled")
        self.progress.start(12)
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
            self.status.set("Cancelled" if self.cancelled else "Export stopped unexpectedly. Check Setup & tools.")
            self._append(self.status.get())
        self.process = None
        self.progress.stop()
        self.export_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
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
                elif event["event"] == "error":
                    self.completed = True
                    self.status.set("Export failed — see the log for details")
                    self._append(event.get("detail", ""))

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

    def _setup(self):
        dialog = tk.Toplevel(self)
        dialog.title("Notebook Press · Setup & tools")
        dialog.geometry("780x620")
        dialog.configure(bg=BG)
        content = ttk.Frame(dialog, padding=22)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="Your publishing tools", font=("Helvetica", 20, "bold")).pack(anchor="w", pady=(0, 10))
        ttk.Label(content, text="Notebook LaTeX includes Pandoc. Browser PDF uses a one-time Chromium download.\nBook engines and TeX / Typst are separate installations.", wraplength=720).pack(anchor="w", pady=(0, 12))
        report = tk.Text(content, height=13, relief="flat", bg="white", fg=INK, padx=12, pady=12, wrap="word")
        report.pack(fill="both", expand=True)
        report.insert("end", "Checking installed tools…")
        report.configure(state="disabled")
        messages = queue.Queue()

        def check():
            try:
                messages.put(dependency_report())
            except Exception as error:
                messages.put([("Dependency check", False, str(error))])

        threading.Thread(target=check, daemon=True).start()

        def poll_report():
            if not dialog.winfo_exists():
                return
            try:
                rows = messages.get_nowait()
            except queue.Empty:
                dialog.after(150, poll_report)
                return
            report.configure(state="normal")
            report.delete("1.0", "end")
            for name, ready, detail in rows:
                report.insert("end", f"{'OK' if ready else '—'}  {name}\n     {detail}\n\n")
            report.configure(state="disabled")

        dialog.after(150, poll_report)
        ttk.Label(content, text="Book engine executable (optional full path; auto-detected when blank)").pack(anchor="w", pady=(15, 5))
        ttk.Entry(content, textvariable=self.book_command).pack(fill="x")
        ttk.Label(content, text='Book 1: python -m pip install "jupyter-book>=1,<2"\nBook 2: python -m pip install mystmd\nLinux may also need: python -m playwright install-deps chromium', foreground=MUTED).pack(anchor="w", pady=10)
        row = ttk.Frame(content)
        row.pack(fill="x")

        def install():
            if self.process:
                messagebox.showinfo("Job running", "Wait for the current job to finish before installing Chromium.", parent=dialog)
                return
            dialog.destroy()
            self._run_job()

        ttk.Button(row, text="Install PDF browser", style="Primary.TButton", command=install).pack(side="left")
        ttk.Button(row, text="Done", command=lambda: (self._save_settings(), dialog.destroy())).pack(side="right")

    def _close(self):
        self._save_settings()
        if self.process:
            self.closing = True
            self._cancel()
        else:
            self.destroy()
