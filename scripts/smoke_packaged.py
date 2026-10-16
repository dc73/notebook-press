"""Test a frozen GUI executable through its file-based worker interface."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

import nbformat
from pypdf import PdfReader


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument('--executable', type=Path)
    args = parser.parse_args()
    if args.executable:
        executable = args.executable.resolve()
    elif sys.platform == 'win32' and (root / 'dist' / 'NotebookPress.exe').is_file():
        executable = root / 'dist' / 'NotebookPress.exe'
    elif sys.platform == 'darwin':
        executable = root / 'dist' / 'Notebook Press.app' / 'Contents' / 'MacOS' / 'NotebookPress'
    else:
        executable = root / 'dist' / 'NotebookPress' / ('NotebookPress.exe' if sys.platform == 'win32' else 'NotebookPress')
    with tempfile.TemporaryDirectory(prefix='notebook-press-smoke-') as temporary:
        work = Path(temporary)
        desktop_result = work / 'desktop.json'
        desktop_command = [str(executable), '--check-desktop', str(desktop_result)]
        if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'):
            assert shutil.which('xvfb-run'), 'Install Xvfb for the packaged desktop check.'
            desktop_command = ['xvfb-run', '-a', *desktop_command]
        desktop = subprocess.run(desktop_command, timeout=120)
        assert desktop.returncode == 0 and desktop_result.is_file(), 'Packaged desktop did not open'
        assert json.loads(desktop_result.read_text()) == {'desktop': 'ready'}
        source = work / 'sample.ipynb'
        nbformat.write(nbformat.v4.new_notebook(cells=[
            nbformat.v4.new_markdown_cell('# Packaged export\n\nA formula: $E=mc^2$.'),
            nbformat.v4.new_code_cell('raise Exception("Must not run")', outputs=[nbformat.v4.new_output('stream', name='stdout', text='Saved output: 42')])
        ]), source)
        request = work / 'request.json'
        request.write_text(json.dumps({'source': str(source), 'destination': str(work / 'exports')}))
        events = work / 'events.jsonl'
        process = subprocess.run([str(executable), '--worker', str(request), '--events', str(events)], timeout=180)
        assert events.exists(), f'Packaged worker did not start (exit {process.returncode})'
        rows = [json.loads(line) for line in events.read_text(encoding='utf-8').splitlines()]
        assert process.returncode == 0 and rows[-1]['event'] == 'done', rows
        result = Path(rows[-1]['path'])
        assert (result / 'latex' / 'notebook.tex').is_file()
        pdf = PdfReader(result / 'notebook.pdf')
        assert 'Packaged export' in pdf.pages[0].extract_text()
        assert 'Saved output: 42' in '\n'.join(page.extract_text() for page in pdf.pages)
        assert (result / 'overleaf.zip').is_file()
        # The app's bundled Python cannot serve as an arbitrary notebook kernel.
        # Exercise a real external interpreter, as desktop users will select.
        unrun = work / 'unrun.ipynb'
        nbformat.write(nbformat.v4.new_notebook(cells=[
            nbformat.v4.new_markdown_cell('# Generated figures'),
            nbformat.v4.new_code_cell('import matplotlib.pyplot as plt\nplt.plot([1,2,3], [3,1,4])\nplt.title("Fresh plot")\nplt.show()\nprint("Generated result: 8")'),
        ]), unrun)
        original = unrun.read_bytes()
        request.write_text(json.dumps({'source': str(unrun), 'destination': str(work / 'exports'),
                                       'execute': True, 'python_executable': sys.executable, 'include_code': False}))
        process = subprocess.run([str(executable), '--worker', str(request), '--events', str(events)], timeout=180)
        rows = [json.loads(line) for line in events.read_text(encoding='utf-8').splitlines()]
        assert process.returncode == 0 and rows[-1]['event'] == 'done', rows
        generated = Path(rows[-1]['path'])
        assert (generated / 'executed.ipynb').is_file()
        assert list((generated / 'latex').rglob('*.png'))
        with zipfile.ZipFile(generated / 'overleaf.zip') as bundle:
            assert 'notebook.tex' in bundle.namelist()
            assert any(name.endswith('.png') for name in bundle.namelist())
        pdf = PdfReader(generated / 'notebook.pdf')
        assert sum(len(page.images) for page in pdf.pages) >= 1
        assert 'Generated result: 8' in '\n'.join(page.extract_text() for page in pdf.pages)
        assert unrun.read_bytes() == original
        print('Packaged desktop, saved outputs, execution, generated figures, Overleaf ZIP, PDF and LaTeX passed.')


if __name__ == '__main__':
    main()
