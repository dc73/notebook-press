# Build on each target OS: python scripts/build.py [--with-browser]
import os
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH)
datas = collect_data_files('notebook_press') + collect_data_files('pypandoc')
datas += [(str(Path(sys.prefix) / 'share' / 'jupyter' / 'nbconvert'), 'share/jupyter/nbconvert')]
for package in ('nbconvert', 'nbformat', 'jupyter_core', 'jupyterlab_pygments', 'jsonschema', 'pandocfilters'):
    datas += copy_metadata(package)
hidden = collect_submodules('nbconvert') + collect_submodules('pygments.lexers')
hidden += ['playwright.async_api', 'playwright.sync_api', 'playwright.__main__']
analysis = Analysis(
    [str(root / 'launch.py')], pathex=[str(root)], binaries=[], datas=datas,
    hiddenimports=hidden, hookspath=[], hooksconfig={},
    runtime_hooks=[str(root / 'scripts' / 'frozen_runtime.py')],
    excludes=['pytest', 'IPython', 'matplotlib', 'scipy', 'pandas', 'numpy', 'jupyter_book', 'mystmd'],
    noarchive=False,
)
if os.environ.get('NOTEBOOK_PRESS_BUNDLE_BROWSER') != '1':
    # A prior hermetic install must not silently enlarge a standard build.
    analysis.datas = [entry for entry in analysis.datas if '.local-browsers' not in entry[0]]
    analysis.binaries = [entry for entry in analysis.binaries if '.local-browsers' not in entry[0]]
pyz = PYZ(analysis.pure)
options = dict(name='NotebookPress', debug=False, bootloader_ignore_signals=False,
               strip=False, upx=False, console=False, disable_windowed_traceback=False,
               argv_emulation=False,
               icon=str(root / 'notebook_press' / 'assets' / 'app.ico') if sys.platform == 'win32' else None,
               version=str(root / 'scripts' / 'windows_version.txt') if sys.platform == 'win32' else None)
if os.environ.get('NOTEBOOK_PRESS_ONEFILE') == '1':
    exe = EXE(pyz, analysis.scripts, analysis.binaries, analysis.datas, [], **options)
else:
    exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, **options)
    collection = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name='NotebookPress')
if sys.platform == 'darwin' and os.environ.get('NOTEBOOK_PRESS_ONEFILE') != '1':
    app = BUNDLE(collection, name='Notebook Press.app', icon=str(root / 'notebook_press' / 'assets' / 'app.icns'),
                 bundle_identifier='app.notebookpress.desktop',
                 info_plist={'NSHighResolutionCapable': True, 'CFBundleShortVersionString': '0.1.0'})
