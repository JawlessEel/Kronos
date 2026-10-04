# Kronos desktop launchers

These launch the existing browser workbench in Google Chrome. The real four-model WebGPU pipeline is unchanged. They bundle local assets, serve only `127.0.0.1`, and stop when the launcher closes. They do not install Python, runtimes, system services, startup tasks, firewall rules, browser extensions, or remote access.

## Install

Windows: double-click `Kronos-WebGPU-Setup-1.0.0.exe`, then **Install and launch Kronos**. Files go into `%LOCALAPPDATA%\KronosWebGPU\1.0.0`, with a desktop shortcut if that name is free. Existing installations or unrelated folders are not overwritten. Windows 10/11's .NET Framework and Chrome are required. This prototype is not Authenticode signed; Windows may show a publisher warning.

Mac: open `Kronos-WebGPU-Mac-1.0.0.dmg`, drag the app into Applications (or your user's Applications folder), then launch it. The binary contains arm64 and x86_64 slices, targets macOS 12 or later, and uses only system frameworks. Actual WebGPU support still depends on Chrome and hardware. The app is ad-hoc signed, not Apple-notarized: Gatekeeper may require manual approval through Apple's normal first-launch flow. No protections are disabled. See [Apple's app-opening guidance](https://support.apple.com/102445).

The launcher has **Open Kronos in Chrome**, **Show Chrome extension folder**, and **Read setup instructions**. The server selects the first available port from 7090–7099. Close the launcher to stop it. Internet access is still needed for market feeds and the pinned ONNX Runtime Web module. Optional Perchance AI Analyst requires the Perchance plugin environment; native local launching does not supply that remote plugin.

The TradingView extension remains a separate manual Chrome **Load unpacked** step. Select the entire `chrome-bridge/extension` folder shown by the launcher. Install the included Pine source separately, reload existing source/chart tabs after extension installation, and match the symbol/exchange/timeframe/session. User browser presets remain in Chrome storage, outside the application install folder.

## Build

Supply the reviewed combined package ZIP containing one root folder with `workbench/`, `chrome-bridge/`, `perchance/`, and `START-HERE.txt`.

Windows PowerShell:

```powershell
.\build-windows.ps1 -PayloadZip 'C:\packages\payload.zip' -OutputDirectory 'C:\packages\built'
```

macOS Terminal (Command Line Tools required to build, not run):

```sh
sh build-mac.sh /path/to/payload.zip /path/to/new-output-directory
```

No global dependencies are installed by these build scripts. Outputs are not tracked in Git. Signing and notarization for wider distribution require separate certificates and authorization; the build never downloads credentials or suppresses Gatekeeper.

## Checks

Both native binaries provide a bounded 60-second `--serve CONTENT_ROOT PORT_FILE` mode for verification without opening a browser. Windows also has `--extract-test NEW_DIRECTORY` to validate embedded extraction without desktop changes. `test-http.py PORT` checks the root page, JS MIME type, all four model sizes/hashes, HEAD behavior, extension assets, traversal rejection, unsupported methods, and Host-header validation.

## Remove

Close Kronos first. Windows: delete only its managed version folder and its desktop shortcut after saving any files you placed there. Mac: move only the installed Kronos app to Trash. Disable/remove the Chrome extension before deleting its source folder. Browser presets and model cache remain until separately removed through the workbench/browser controls. No unrelated installations are modified.
