# BadSeed 🌱

`BadSeed` is a lightweight, high-performance, and zero-dependency Python CLI tool built to detect known compromised Python and Javascript/Typescript libraries on a local machine. It was designed to quickly identify specific targets and high-risk versions of libraries that have been identified in recent supply chain attacks.

It was designed to run on MacOS but could be easily adapted to run on Windows or Linux machines.

## Features

- **Multi-Ecosystem Support:** Scans for both Python (`pip`, `poetry`, `pipenv`, `venv`, `uv`, `pixi`) and Node.js (`npm`, `yarn`, `pnpm`) dependencies.
- **Deep Scanning:** Recursively searches development directories for lockfiles (`package-lock.json`, `yarn.lock`, `poetry.lock`, `uv.lock`, `pixi.lock`), `package.json`, and `pyproject.toml`.
- **System-Level Checks:** Interrogates global environments including `npm -g`, global `pip`, and Homebrew-installed packages.
- **Installation Verification:** Directly inspects `node_modules` and Python `site-packages` within virtual environments to confirm actual installed versions.
- **CSV Output:** Generates a structured report for easy auditing and automation.

## Configuration

The tool uses a `config.json` file in the same directory as the script to configure default scan paths, system paths, and the list of compromised packages.

### Format
```json
{
    "default_paths": ["~/dev"],
    "system_paths": [
        "/usr/local/lib/node_modules",
        "/opt/homebrew/lib/node_modules",
        "/opt/homebrew/Cellar",
        "/usr/local/Cellar"
    ],
    "compromised": {
        "python": {
            "litellm": ["~1.82.8"]
        },
        "npm": {
            "axios": ["~1.14.1", "~0.30.4"]
        }
    }
}
```

- **`default_paths`**: Directories scanned by default when no paths are provided on the command line.
- **`system_paths`**: Additional system-level directories to scan if they exist.
- **`compromised`**: The list of compromised packages and their version specs, organized by ecosystem.

## Target Compromises

Currently tracks the following high-risk versions:
- **Python:** `litellm==1.82.8`
- **npm:** `axios@1.14.1`, `axios@0.30.4`

## Installation

The tool is a standalone Python script with no external dependencies (uses only the Python standard library).

```bash
# Clone the repository (or copy badseed.py)
chmod +x badseed.py
```

## Usage

### Basic Scan
Scan default development directories (`~/dev`), global package managers, and Homebrew:
```bash
./badseed.py
```

### Scan Specific Directories
```bash
./badseed.py ~/projects /path/to/other/code
```

### Export to CSV
```bash
./badseed.py --output findings.csv
```

### Skip Global/System Checks
If you only want to scan local project files and skip calls to `npm`, `pip`, and `brew`:
```bash
./badseed.py --no-global
```

## How It Works

1. **Global Interrogation:** Runs system commands (`npm list -g`, `pip list`, `brew list`) to find globally installed packages.
2. **Recursive Walk:** Efficiently traverses directories, skipping heavy folders like `.git` and `__pycache__`.
3. **Lockfile Parsing:** Extracts exact pinned versions from `package-lock.json`, `poetry.lock`, `Pipfile.lock`, and `requirements.txt`.
4. **Metadata Inspection:** Reads `.dist-info` in Python virtual environments and `package.json` inside `node_modules` to verify the "ground truth" of what is actually on disk.

## Output Format

The tool outputs a CSV with the following columns:
- `Library`: The name of the package.
- `Version`: The specific version found.
- `Location`: The file path or system environment where it was detected.
- `Ecosystem`: The package manager or system (e.g., `npm`, `python`, `homebrew`).
