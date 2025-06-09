# lrelease Setup Guide

The Elevator Control System uses the `lrelease` tool to compile translation files for multi-language support. This document explains how the system finds and uses `lrelease`.

## Automatic Detection

The system automatically searches for `lrelease` in the following order:

1. **Environment Variable**: `LRELEASE_PATH`
2. **Python Scripts Directory**: `{python_prefix}/Scripts/`
3. **System PATH**: Standard executable search paths

## Search Priority

The system searches for these executables in order:

- `lrelease` (or `lrelease.exe` on Windows)
- `pyside6-lrelease` (or `pyside6-lrelease.exe` on Windows)

## Setup Options

### Option 1: Install PySide6 (Recommended)

```shell
uv add PySide6
# or
pip install PySide6
```

This will install `pyside6-lrelease` in your Python Scripts directory.

### Option 2: Use Environment Variable

Set the `LRELEASE_PATH` environment variable to point to your custom `lrelease` executable:

```powershell
# PowerShell (Windows)
$env:LRELEASE_PATH = "C:\Qt\6.5.0\bin\lrelease.exe"

# Or add to your system environment variables permanently
```

```bash
# Bash (Linux/macOS)
export LRELEASE_PATH="/usr/local/bin/lrelease"
```

### Option 3: Add to System PATH

Ensure your `lrelease` executable is available in the system PATH.

## Programmatic Usage

You can also provide a custom path directly when creating the TranslationManager:

```python
from system.gui.i18n import TranslationManager
from qtpy.QtCore import QCoreApplication

app = QCoreApplication()
tm = TranslationManager(app, lrelease_path="/custom/path/to/lrelease")
```

## Troubleshooting

If you see warnings like "lrelease not found", it means:

1. No `lrelease` tool was found in any of the search locations
2. Translation files will not be automatically compiled
3. You can still use pre-compiled `.qm` files if they exist

The simplest solution is to install PySide6, which includes `pyside6-lrelease`.
