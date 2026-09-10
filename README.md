# Spider-Man 2 DLSS 5 Manager

A Windows GUI manager for the **Marvel's Spider-Man 2** DLSS 5 / ReShade setup.

## Features

- Steam library auto-detection
- ReShade 6.8.0 Add-on installer flow
- DLSS + Streamline package installation
- patched `nvngx_dlssnr.dll` installation
- `renodx-dlss.addon64` installation
- automatic backups and restore
- safe ZIP extraction with traversal, duplicate-name, file-count and size checks
- HTTPS-only downloads
- SHA-256 verification when hashes are configured
- Windows Authenticode verification for the ReShade installer
- remote `config/components.json` so component URLs/versions can be changed without rebuilding the app
- remote `config/version.json` for manager updates
- self-update helper for the packaged EXE
- PyArmor source obfuscation in release builds
- Nuitka native compilation in release builds
- GitHub Actions Windows EXE build and release workflow

## Repository

```text
Spiderman-2-DLSS-5/
├── README.md
├── LICENSE
├── .gitignore
├── config/
│   ├── components.json
│   └── version.json
├── src/
│   ├── DLSS5Manager.py
│   └── updater.py
└── .github/
    └── workflows/
        └── build.yml
```

## Remote configuration

The manager reads:

- `https://raw.githubusercontent.com/Kubixpro1/Spiderman-2-DLSS-5/main/config/components.json`
- `https://raw.githubusercontent.com/Kubixpro1/Spiderman-2-DLSS-5/main/config/version.json`

If the remote component manifest cannot be downloaded, the manager falls back to the built-in component definitions.

### ReShade

Official ReShade Add-on installer:

`https://reshade.me/downloads/ReShade_Setup_6.8.0_Addon.exe`

The manager will **not silently execute it**. The downloaded installer must pass Windows Authenticode verification and the user must explicitly approve launching it.

### Third-party components

The DLSS archive, patched `nvngx_dlssnr.dll`, and RenoDX add-on are third-party files. They are kept as URLs in the manifest rather than bundled into this repository. Verify that you have the right to redistribute/use any third-party files before publishing them.

## SHA-256 verification

Hashes are intentionally blank until independently verified against the exact files. A blank hash is reported as `SHA-256 not configured`; it is never presented as verified.

Once a file has been independently verified, put its lowercase SHA-256 in `config/components.json` or `config/version.json`.

## Release build / protection

Release builds use this pipeline:

```text
src/*.py
   ↓
PyArmor obfuscation
   ↓
Nuitka native compilation
   ↓
DLSS5Manager.exe
   ↓
SHA-256
   ↓
GitHub Release
```

PyArmor makes the Python source substantially harder to inspect, while Nuitka compiles the obfuscated application into a native Windows executable. This is defense-in-depth, not absolute protection against reverse engineering.

The generated `obfuscated/`, `build/`, and `dist/` directories are ignored by Git and are not published as source artifacts.

## Building

The GitHub Actions workflow installs PyArmor and Nuitka, obfuscates the application, then compiles the obfuscated entry point with Nuitka. A tagged build creates `DLSS5Manager.exe` as a GitHub Release asset.

Create a release by pushing a tag such as:

```powershell
git tag v2.2.0
git push origin v2.2.0
```

For local development without the protected release pipeline:

```powershell
py -m pip install pyinstaller
pyinstaller --clean --noconfirm --onefile --windowed --name DLSS5Manager src/DLSS5Manager.py
```

The output is `dist\DLSS5Manager.exe`.

## Updating the manager

The packaged EXE checks `version.json`. If a newer version is advertised, it downloads the release asset, verifies the configured SHA-256 when available, starts a small replacement helper, and restarts the new EXE after the old process exits.

Do not put GitHub tokens, private keys, passwords, or other secrets in this repository.

## Security model

The manager is designed to reduce accidental execution of untrusted downloads, not to magically make third-party files trustworthy. HTTPS, file-type checks, optional SHA-256 verification, Authenticode verification for ReShade, and explicit user confirmation are used together.

The application only changes the selected game directory and its own `.dlss_manager_backups` directory.

## License

MIT. See `LICENSE`.
