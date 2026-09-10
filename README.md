# Spider-Man 2 DLSS 5 Manager

A Windows utility for managing the DLSS 5 / ReShade setup for **Marvel's Spider-Man 2**.

## Features

- ReShade Add-on installation flow
- DLSS / Streamline component management
- Patched `nvngx_dlssnr.dll` support
- `renodx-dlss.addon64` support
- Backup and restore support
- Remote component configuration through `components.json`
- Remote application update information through `version.json`
- SHA-256 verification fields for downloaded files

## Repository structure

```text
Spiderman-2-DLSS-5/
├── README.md
├── LICENSE
├── .gitignore
├── config/
│   ├── components.json
│   └── version.json
└── src/
    └── README.md
```

## Remote configuration

The manager can read the following files directly from the `main` branch:

- `config/components.json` — URLs and versions of external components
- `config/version.json` — current manager version and release information

Raw configuration base:

`https://raw.githubusercontent.com/Kubixpro1/Spiderman-2-DLSS-5/main/config/`

## ReShade

The configured ReShade package is the official **ReShade 6.8.0 Add-on** installer:

`https://reshade.me/downloads/ReShade_Setup_6.8.0_Addon.exe`

The manager should verify the Windows Authenticode signature before launching the installer.

## Important

This repository stores configuration and source code. Third-party components should remain hosted by their respective owners unless redistribution is explicitly permitted.

Do not put GitHub tokens, signing keys, passwords, or other secrets in this repository or inside the distributed application.

## Updating components

To update a component, change its `version`, `url`, and preferably `sha256` in `config/components.json`. The manager can then use the new configuration without requiring a new application build.

## License

The manager source is released under the MIT License. Third-party software remains subject to its own licenses and terms.
