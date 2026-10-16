"""Sage desktop workspace. Conversion and process handling live in app.py."""

from __future__ import annotations

import json
from pathlib import Path
import queue
import sys
import threading
import webbrowser

import customtkinter as ctk
from PIL import Image
import tkinter as tk
from tkinter import messagebox

from . import __version__
from .engine import dependency_report

BG = "#FAFBF9"
SIDEBAR = "#EDF2EB"
PANEL = "#FFFFFF"
INK = "#25332A"
MUTED = "#657368"
GREEN = "#52745B"
HOVER = "#42634B"
SOFT = "#DFE9DD"
LINE = "#E2E8DF"


class Workspace(ctk.CTk):
    """Native, scalable controls shared by the workspace and tools window."""

    def _style(self):
        ctk.set_appearance_mode("light")
        self.family = "Segoe UI" if sys.platform == "win32" else ("SF Pro Text" if sys.platform == "darwin" else "DejaVu Sans")
        self.configure(fg_color=BG)

    def _label(self, parent, text="", size=13, bold=False, color=INK, **kwargs):
        return ctk.CTkLabel(parent, text=text, text_color=color, anchor="w",
                            font=(self.family, size, "bold" if bold else "normal"), **kwargs)

    def _button(self, parent, text, command, primary=False, **kwargs):
        return ctk.CTkButton(parent, text=text, command=command, height=36, corner_radius=8,
                             fg_color=GREEN if primary else SOFT,
                             hover_color=HOVER if primary else "#D1DECE",
                             text_color="white" if primary else INK,
                             text_color_disabled="#88968A", font=(self.family, 13), **kwargs)

    def _entry(self, parent, variable):
        return ctk.CTkEntry(parent, textvariable=variable, height=38, corner_radius=8,
                            fg_color=BG, border_color=LINE, border_width=1,
                            text_color=INK, font=(self.family, 13))

    def _segment(self, parent, values, **kwargs):
        return ctk.CTkSegmentedButton(parent, values=values, height=36, corner_radius=8,
                                      border_width=3, fg_color=SIDEBAR,
                                      selected_color=PANEL, selected_hover_color=BG,
                                      unselected_color=SIDEBAR, unselected_hover_color=SOFT,
                                      text_color=INK, text_color_disabled="#88968A",
                                      font=(self.family, 13), **kwargs)

    def _card(self, parent):
        return ctk.CTkFrame(parent, fg_color=PANEL, border_width=1,
                            border_color=LINE, corner_radius=14)

    def _layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        sidebar = ctk.CTkFrame(self, width=200, corner_radius=0, fg_color=SIDEBAR)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(5, weight=1)
        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(28, 32))
        self.wordmark_icon = ctk.CTkImage(Image.open(Path(__file__).parent / "assets" / "logo.png"), size=(32, 32))
        ctk.CTkLabel(brand, text="", image=self.wordmark_icon).pack(side="left")
        self._label(brand, "Notebook\nPress", 14, True, justify="left").pack(side="left", padx=10)
        selected = ctk.CTkFrame(sidebar, fg_color=SOFT, corner_radius=8, height=40)
        selected.grid(row=1, column=0, sticky="ew", padx=12)
        self._label(selected, "  Export", 13, True).pack(anchor="w", padx=14, pady=6)
        self._label(sidebar, "SOURCES", 10, True, MUTED).grid(row=2, column=0, sticky="w", padx=26, pady=(30, 10))
        for row, text, action in [(3, "Open notebook", self._choose_notebook), (4, "Open book folder", self._choose_book)]:
            button = self._button(sidebar, text, action, width=170, anchor="w")
            button.configure(fg_color="transparent", hover_color=SOFT)
            button.grid(row=row, column=0, padx=12, pady=2, sticky="ew")
        bottom = ctk.CTkFrame(sidebar, fg_color="transparent")
        bottom.grid(row=6, column=0, sticky="ew", padx=16, pady=22)
        for text, action in [("Settings & tools", self._setup), ("Help & guide", lambda: webbrowser.open("https://github.com/dc73/notebook-press/blob/main/docs/usage.md"))]:
            button = self._button(bottom, text, action, width=160, anchor="w")
            button.configure(fg_color="transparent", hover_color=SOFT)
            button.pack(fill="x", pady=2)
        self._label(bottom, f"Notebook Press  {__version__}", 10, color=MUTED).pack(anchor="w", padx=6, pady=(16, 0))

        main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)
        heading = ctk.CTkFrame(main, fg_color="transparent")
        heading.grid(row=0, column=0, sticky="ew", padx=32, pady=(24, 20))
        self._label(heading, "Workspace  /  Export", 11, color=MUTED).pack(anchor="w")
        self.page_title = self._label(heading, "Export notebook", 29, True)
        self.page_title.pack(anchor="w", pady=(10, 2))
        self._label(heading, "A finished document, from the work you’ve already done.", color=MUTED).pack(anchor="w")

        body = ctk.CTkScrollableFrame(main, fg_color=BG, corner_radius=0,
                                     scrollbar_fg_color=BG, scrollbar_button_color=LINE,
                                     scrollbar_button_hover_color=SOFT)
        body.grid(row=1, column=0, sticky="nsew", padx=(26, 16))
        body.grid_columnconfigure(0, weight=1)
        source = self._card(body)
        source.grid(row=0, column=0, sticky="ew", padx=6, pady=(0, 16))
        source.grid_columnconfigure(0, weight=1)
        self._label(source, "Source", 15, True).grid(row=0, column=0, sticky="w", padx=20, pady=(15, 8))
        field = ctk.CTkFrame(source, fg_color="transparent")
        field.grid(row=1, column=0, sticky="ew", padx=20)
        field.grid_columnconfigure(0, weight=1)
        self.source_entry = self._entry(field, self.source)
        self.source_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self._button(field, "Choose file", self._choose_notebook, width=100).grid(row=0, column=1)
        self._button(field, "Book folder", self._choose_book, width=100).grid(row=0, column=2, padx=(8, 0))
        self._label(source, "", 11, color=MUTED, textvariable=self.source_detail).grid(row=2, column=0, sticky="w", padx=20, pady=(6, 13))

        middle = ctk.CTkFrame(body, fg_color="transparent")
        middle.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 16))
        middle.grid_columnconfigure(0, weight=1)
        options = self._card(middle)
        options.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        options.grid_columnconfigure(0, weight=1)
        self._label(options, "Format & appearance", 15, True).grid(row=0, column=0, sticky="w", padx=20, pady=(16, 10))
        self.format_picker = self._segment(options, ["PDF", "LaTeX", "Both"], command=self._set_format)
        self.format_picker.grid(row=1, column=0, sticky="ew", padx=20)
        self.format_hint = self._label(options, "", 11, color=MUTED, wraplength=400, justify="left")
        self.format_hint.grid(row=2, column=0, sticky="w", padx=20, pady=(6, 12))
        controls = ctk.CTkFrame(options, fg_color="transparent")
        controls.grid(row=3, column=0, sticky="ew", padx=20)
        controls.grid_columnconfigure((0, 1), weight=1, uniform="options")
        self._label(controls, "Paper size", 11, color=MUTED).grid(row=0, column=0, sticky="w")
        self._label(controls, "PDF engine", 11, color=MUTED).grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.paper_picker = self._segment(controls, ["A4", "Letter"], variable=self.paper, dynamic_resizing=False)
        self.paper_picker.grid(row=1, column=0, sticky="ew")
        self.engine_choice = tk.StringVar(value="LaTeX" if self.pdf_engine.get() == "latex" else "Browser")
        self.engine_picker = ctk.CTkOptionMenu(controls, values=["Browser", "LaTeX"], variable=self.engine_choice,
            command=lambda value: self.pdf_engine.set(value.lower()), height=36, corner_radius=8,
            fg_color=SIDEBAR, button_color=SOFT, button_hover_color="#D1DECE", text_color=INK,
            text_color_disabled="#88968A", font=(self.family, 13), dropdown_font=(self.family, 13),
            dropdown_fg_color=PANEL, dropdown_hover_color=SIDEBAR, dropdown_text_color=INK)
        self.engine_picker.grid(row=1, column=1, sticky="ew", padx=(12, 0))
        self.engine_hint = self._label(options, "", 11, color=MUTED, wraplength=390, justify="left")
        self.engine_hint.grid(row=4, column=0, sticky="w", padx=20, pady=(6, 10))
        ctk.CTkFrame(options, height=1, fg_color=LINE).grid(row=5, column=0, sticky="ew", padx=20)
        code_row = ctk.CTkFrame(options, fg_color="transparent")
        code_row.grid(row=6, column=0, sticky="ew", padx=20, pady=(10, 15))
        self._label(code_row, "Include code", 13).pack(side="left")
        self.code_check = ctk.CTkSwitch(code_row, text="", variable=self.include_code, width=46,
            switch_width=34, switch_height=20, fg_color="#CCD5C9", progress_color=GREEN,
            border_width=2, border_color="#B6C8B1", button_color="white", button_hover_color=BG)
        self.code_check.pack(side="right")

        summary = ctk.CTkFrame(middle, width=246, fg_color=SIDEBAR, corner_radius=14)
        summary.grid(row=0, column=1, sticky="nsew")
        summary.grid_columnconfigure(0, weight=1)
        self._label(summary, "YOUR EXPORT", 10, True, MUTED).grid(row=0, column=0, sticky="w", padx=22, pady=(20, 12))
        self.document_name = self._label(summary, "Choose a notebook", 19, True, wraplength=202, justify="left")
        self.document_name.grid(row=1, column=0, sticky="w", padx=22)
        self.document_info = self._label(summary, "Saved outputs and figures", 11, color=MUTED, wraplength=202, justify="left")
        self.document_info.grid(row=2, column=0, sticky="w", padx=22, pady=(4, 16))
        ctk.CTkFrame(summary, height=1, fg_color="#D6E0D3").grid(row=3, column=0, sticky="ew", padx=22)
        self.bundle_label = self._label(summary, "", 13, wraplength=202, justify="left")
        self.bundle_label.grid(row=4, column=0, sticky="nw", padx=22, pady=12)
        self.overleaf_button = self._button(summary, "Open in Overleaf", self._open_overleaf, width=202, state="disabled")
        self.overleaf_button.grid(row=5, column=0, padx=22, pady=(0, 8))
        self.execution_note = self._label(summary, "Uses saved outputs.\nNo cells are rerun.", 11, color=MUTED, justify="left")
        self.execution_note.grid(row=6, column=0, sticky="sw", padx=22, pady=(0, 18))
        summary.grid_rowconfigure(4, weight=1)

        execution = self._card(body)
        execution.grid(row=2, column=0, sticky="ew", padx=6, pady=(0, 16))
        execution.grid_columnconfigure(0, weight=1)
        run_row = ctk.CTkFrame(execution, fg_color="transparent")
        run_row.grid(row=0, column=0, sticky="ew", padx=20, pady=(12, 0))
        self._label(run_row, "Run notebook to generate figures", 15, True).pack(side="left")
        self.run_check = ctk.CTkSwitch(run_row, text="", variable=self.run_notebook, width=46,
            switch_width=34, switch_height=20, fg_color="#CCD5C9", progress_color=GREEN,
            border_width=2, border_color="#B6C8B1", button_color="white", button_hover_color=BG)
        self.run_check.pack(side="right")
        self.run_hint = self._label(execution, "", 11, color=MUTED, wraplength=720, justify="left")
        self.run_hint.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 12))
        self.python_row = ctk.CTkFrame(execution, fg_color="transparent")
        self.python_row.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 16))
        self.python_row.grid_columnconfigure(0, weight=1)
        self._label(self.python_row, "Python interpreter (blank = auto-detect)", 11, color=MUTED).grid(row=0, column=0, sticky="w")
        self._entry(self.python_row, self.python_executable).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        self._button(self.python_row, "Choose", self._choose_python, width=80).grid(row=1, column=1, sticky="s")
        self._label(self.python_row, "Cell timeout (s)", 11, color=MUTED).grid(row=0, column=2, sticky="w", padx=(16, 0))
        timeout_entry = self._entry(self.python_row, self.execution_timeout)
        timeout_entry.configure(width=88)
        timeout_entry.grid(row=1, column=2, sticky="s", padx=(16, 0))
        self.run_notebook.trace_add("write", self._source_changed)

        destination = self._card(body)
        destination.grid(row=3, column=0, sticky="ew", padx=6, pady=(0, 12))
        destination.grid_columnconfigure(0, weight=1)
        self._label(destination, "Save to", 15, True).grid(row=0, column=0, sticky="w", padx=20, pady=(12, 6))
        row = ctk.CTkFrame(destination, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 15))
        row.grid_columnconfigure(0, weight=1)
        self._entry(row, self.destination).grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self._button(row, "Browse", self._choose_destination, width=88).grid(row=0, column=1)

        self.details_button = self._button(body, "Show export details", self._toggle_details, width=160, anchor="w")
        self.details_button.configure(fg_color="transparent", text_color=MUTED)
        self.details_button.grid(row=4, column=0, sticky="w", padx=6, pady=(0, 8))
        self.log = ctk.CTkTextbox(body, height=150, fg_color=SIDEBAR, text_color=INK, corner_radius=10,
            font=("Consolas" if sys.platform == "win32" else "Menlo" if sys.platform == "darwin" else "DejaVu Sans Mono", 11),
            wrap="word", state="disabled")
        self.log.grid(row=5, column=0, sticky="ew", padx=6, pady=(0, 14))
        self.log.grid_remove()
        self.details_visible = False
        self._append("Saved outputs are used by default. Enable Run notebook to generate figures. Each export gets its own folder.")

        footer = ctk.CTkFrame(main, fg_color=PANEL, corner_radius=0)
        footer.grid(row=2, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        self.progress = ctk.CTkProgressBar(footer, height=2, corner_radius=0, mode="determinate",
                                          progress_color=GREEN, fg_color=LINE)
        self.progress.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.progress.set(0)
        self._label(footer, "", 12, color=MUTED, textvariable=self.status, wraplength=320,
                    justify="left").grid(row=1, column=0, sticky="w", padx=32, pady=(12, 0))
        self._label(footer, "Each export is saved in a new folder.", 10, color=MUTED).grid(row=2, column=0, sticky="w", padx=32, pady=(0, 18))
        actions = ctk.CTkFrame(footer, fg_color="transparent")
        actions.grid(row=1, column=1, rowspan=2, sticky="e", padx=28, pady=14)
        self.cancel_button = self._button(actions, "Cancel", self._cancel, width=70)
        self.cancel_button.pack(side="left", padx=(0, 8))
        self.cancel_button.pack_forget()
        self.open_button = self._button(actions, "Open folder", self._open_result, width=110, state="disabled")
        self.open_button.pack(side="left", padx=(0, 8))
        self.export_button = self._button(actions, "Export documents", self._start, primary=True, width=156)
        self.export_button.pack(side="left")
        self.want_pdf.trace_add("write", self._sync_format)
        self.want_latex.trace_add("write", self._sync_format)
        self.pdf_engine.trace_add("write", self._sync_format)
        self._sync_format()

    def _set_format(self, value):
        self.want_pdf.set(value in {"PDF", "Both"})
        self.want_latex.set(value in {"LaTeX", "Both"})

    def _sync_format(self, *_):
        pdf, latex = self.want_pdf.get(), self.want_latex.get()
        self.format_picker.set("Both" if pdf and latex else "PDF" if pdf else "LaTeX" if latex else "")
        self.format_hint.configure(text="A readable PDF and an editable LaTeX project." if pdf and latex else
                                   "A document ready to read and share." if pdf else "Editable source with saved figures included.")
        self.bundle_label.configure(text=("PDF document\n" if pdf else "") + ("LaTeX source + figures" if latex else ""))
        self.engine_choice.set("LaTeX" if self.pdf_engine.get() == "latex" else "Browser")
        self._source_changed()

    def _execution_changed(self, book=False):
        run = self.run_notebook.get() and not book
        if run:
            self.python_row.grid()
        else:
            self.python_row.grid_remove()
        self.run_hint.configure(text="Book exports use saved outputs. Run book pages in Jupyter first." if book else
            "Runs all cells with your Python packages. Cells can read or write files in the notebook’s folder." if run else
            "Off: use saved outputs. Turn on for an unrun notebook or to refresh figures.")
        self.execution_note.configure(text="Runs cells before export.\nOriginal notebook preserved." if run else "Uses saved outputs.\nNo cells are rerun.")

    def _source_summary(self, kind):
        path = Path(self.source.get()).expanduser()
        self.page_title.configure(text="Export book" if kind in {"book-v1", "book-v2"} else "Export notebook")
        name = path.stem.replace("_", " ")
        self.document_name.configure(text=(name[:61] + "…" if len(name) > 64 else name) if kind else "Choose a notebook")
        info = "PDF and LaTeX, your way."
        if kind == "notebook":
            try:
                stat = path.stat()
                key = (str(path), stat.st_mtime_ns, stat.st_size)
                if getattr(self, "_summary_key", None) != key:
                    notebook = json.loads(path.read_text(encoding="utf-8"))
                    cells = notebook.get("cells", [])
                    figures = sum(any(mime.startswith("image/") for mime in output.get("data", {}))
                                  for cell in cells for output in cell.get("outputs", []))
                    self._summary_info = f"{len(cells)} cells · {figures} saved figures"
                    self._summary_unrun = sum(cell.get("cell_type") == "code" and bool(cell.get("source"))
                                              and cell.get("execution_count") is None and not cell.get("outputs") for cell in cells)
                    self._summary_key = key
                info = self._summary_info
                if self._summary_unrun and not self.run_notebook.get():
                    self.run_hint.configure(text=f"{self._summary_unrun} code cells have no saved outputs. Turn on to generate their results and figures.")
            except (OSError, ValueError, AttributeError, TypeError):
                info = "Jupyter notebook"
        elif kind:
            info = "Jupyter Book project"
        self.document_info.configure(text=info)

    def _toggle_details(self):
        self.details_visible = not self.details_visible
        if self.details_visible:
            self.log.grid()
        else:
            self.log.grid_remove()
        self.details_button.configure(text="Hide export details" if self.details_visible else "Show export details")

    def _busy(self, running):
        self.export_button.configure(state="disabled" if running else "normal")
        self.progress.configure(mode="indeterminate" if running else "determinate")
        if running:
            self.cancel_button.pack(side="left", before=self.open_button, padx=(0, 8))
            self.cancel_button.configure(state="normal")
        else:
            self.cancel_button.pack_forget()

    def _setup(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Notebook Press · Settings & tools")
        if sys.platform == "win32":
            dialog.iconbitmap(str(Path(__file__).parent / "assets" / "app.ico"))
        dialog.geometry("760x680")
        dialog.minsize(660, 580)
        dialog.configure(fg_color=BG)
        content = ctk.CTkFrame(dialog, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=28, pady=24)
        self._label(content, "Settings & tools", 25, True).pack(anchor="w")
        self._label(content, "Check the publishing tools available on this device.", color=MUTED).pack(anchor="w", pady=(4, 18))
        report = ctk.CTkTextbox(content, height=240, fg_color=PANEL, text_color=INK,
            border_color=LINE, border_width=1, corner_radius=12, wrap="word", font=(self.family, 12))
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
                report.insert("end", f"{'Ready' if ready else 'Not installed'}  ·  {name}\n{detail}\n\n")
            report.configure(state="disabled")

        dialog.after(150, poll_report)
        self._label(content, "Book engine executable", 13, True).pack(anchor="w", pady=(18, 2))
        self._label(content, "Optional full path. Leave blank to detect automatically.", 11, color=MUTED).pack(anchor="w", pady=(0, 6))
        self._entry(content, self.book_command).pack(fill="x")
        self._label(content, 'Book 1: python -m pip install "jupyter-book>=1,<2"\nBook 2: python -m pip install mystmd\nLinux browser libraries: python -m playwright install-deps chromium', 11,
                    color=MUTED, justify="left").pack(anchor="w", pady=14)
        row = ctk.CTkFrame(content, fg_color="transparent")
        row.pack(fill="x")

        def install():
            if self.process:
                messagebox.showinfo("Job running", "Wait for the current job to finish before installing Chromium.", parent=dialog)
                return
            dialog.destroy()
            self._run_job()

        self._button(row, "Install PDF browser", install, primary=True, width=160).pack(side="left")
        self._button(row, "Done", lambda: (self._save_settings(), dialog.destroy()), width=90).pack(side="right")
