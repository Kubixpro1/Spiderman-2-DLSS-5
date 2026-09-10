# Source

- `DLSS5Manager.py` — main Tkinter application
- `updater.py` — packaged-EXE self-update helper

The manager loads component metadata from `config/components.json` and update metadata from `config/version.json` at runtime.

The application intentionally does not embed verified SHA-256 values until the exact binaries have been independently checked. Blank hashes are treated as unavailable verification, never as proof of trust.

For a release build, GitHub Actions runs PyInstaller with:

```powershell
pyinstaller --clean --noconfirm --onefile --windowed --name DLSS5Manager src/DLSS5Manager.py
```

The resulting asset is `DLSS5Manager.exe`.
