from pathlib import Path

root = Path(SPECPATH)
analysis = Analysis(
    [str(root / 'desktop.py')],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / 'templates'), 'templates'), (str(root / 'static'), 'static'), (str(root / 'config.json'), '.')],
    hiddenimports=['uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan.on'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['pytest', 'tkinter'],
    noarchive=False,
)
archive = PYZ(analysis.pure)
exe = EXE(archive, analysis.scripts, [], exclude_binaries=True, name='ADHD HQ', debug=False, strip=False, upx=False, console=False)
bundle = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name='ADHD HQ')
