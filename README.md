# 3ds Max Python Toolbar

This repository provides a collection of Python utilities for Autodesk 3ds Max (tested with 3ds Max 2020 and newer). The main entry point is `ToolbarMain.py` which launches a dockable window exposing several tools for scene management and quick checks.

## Features

### LOD / Kit Management
* Parses object names such as `LOD0_VARIANT_*` and automatically creates a layer hierarchy.
* Checkboxes allow enabling the filter and switching between LODs and variants.
* Objects with unexpected names are placed in the `WrongNames` layer for review.

### Geometry and Fast Checks
* Buttons for simple geometry sanity checks (e.g. "3.5.2Check" and "NGons").
* Additional utilities found in the "FastChecks" tab.
* Copy/paste helpers for common operations.

### Built-in Auto-updater
* The script `autoupdater.py` downloads updates from GitHub and can restore missing files.
* Activity is logged to `update.log` and the current version is stored in the `VERSION` file.
* Runs automatically when launching `ToolbarMain.py`.

## Installation
1. Copy or clone this repository into a folder included in 3ds Max's Python path (for example `<maxroot>/scripts/python`).
2. Start 3ds Max 2020+.
3. Run `ToolbarMain.py` through **Scripting → Run Script...** or execute the following in MAXScript:

```maxscript
python.executeFile @"C:\\path\\to\\ToolbarMain.py"
```

The toolbar window should appear and the updater will check GitHub for newer versions. If an update is installed the toolbar restarts automatically.

## Manual Update
If you wish to trigger the update process manually you can run:

```python
import autoupdater
autoupdater.check_for_updates()
```

During an update all repository files are replaced except the updater itself and the log file. Key files listed in `filelist.txt` are verified on each start and restored if missing.
Edit the constants `GITHUB_OWNER`, `GITHUB_REPO`, `BRANCH` and `VERSION_FILE` inside `autoupdater.py` if you want to point to a different repository.

## Variant Configuration
The list of available variant buttons is read from `nametags.json`:

```json
{
    "groups": ["variantA", "variantB"]
}
```

Modify this file to define your variants, then use the **Make Layers** button to rebuild the scene layer structure.

---

This repository vendors the `requests` library and its dependencies (`urllib3`, `chardet`, `idna`, `certifi`) so that the tools run out of the box in a clean 3ds Max Python environment.
