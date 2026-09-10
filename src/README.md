# Source

Place the current `DLSS5Manager.py` source here.

The application should load component metadata from:

```text
https://raw.githubusercontent.com/Kubixpro1/Spiderman-2-DLSS-5/main/config/components.json
```

and application update metadata from:

```text
https://raw.githubusercontent.com/Kubixpro1/Spiderman-2-DLSS-5/main/config/version.json
```

Recommended update flow:

1. Fetch `version.json` over HTTPS.
2. Compare the remote semantic version with the local version.
3. Download the new executable to a temporary file.
4. Verify SHA-256.
5. Verify the Authenticode signature where available.
6. Start a small updater helper.
7. Exit the current application.
8. Replace the old executable and restart it.

The manager should never trust a downloaded executable or DLL solely because the URL is reachable.
