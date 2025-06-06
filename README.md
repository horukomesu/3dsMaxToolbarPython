# 3ds Max Toolbar Python Tools

This repository contains helper scripts for the custom 3ds Max toolbar.  
A small auto-update module is provided to keep the scripts in sync with the
GitHub repository.

## Auto-updater

The module `autoupdater.py` can be imported and used to automatically check
for new versions of this repository on GitHub. By default it checks the
`main` branch of the repository specified in the module constants. The
function returns `True` when an update has been installed and accepts an
optional callback for progress reporting.

```
import autoupdater
autoupdater.check_for_updates()
```

During an update the existing files are backed up in the `backup` folder next
to the scripts and the current commit hash is stored in the file `VERSION`.
All actions are logged to `update.log`.

`ToolbarMain.py` performs this check automatically on startup and shows a
progress dialog when downloading an update. If an update is installed the
script is restarted.

Edit the constants `GITHUB_OWNER` and `GITHUB_REPO` inside `autoupdater.py`
to point to the desired repository.
