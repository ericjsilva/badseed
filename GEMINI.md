# GEMINI.md - BadSeed

## Project Overview
`BadSeed` is a high-performance, zero-dependency Python CLI tool built to detect compromised supply chain libraries on a local machine. It was designed to quickly identify specific targets and high-risk versions of libraries that have been identified in recent supply chain attacks.

### Main Technologies
- **Language:** Python 3 (Standard Library only)
- **Ecosystems:** Node.js (npm, yarn, pnpm) and Python (pip, poetry, pipenv, uv, pixi)
- **Scanning Targets:** Global installations (npm global, pip global, Homebrew) and recursive local directory scanning (lockfiles including `uv.lock`, `pixi.lock`, `yarn.lock`).

## Data Source
The tool uses a `config.json` file located in the same directory as the script. This file contains the list of compromised packages, default scan paths, and system paths.

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
      "litellm": ["1.82.8"]
    },
    "npm": {
      "axios": ["1.14.1", "0.30.4"]
    }
  }
}
```

## Building and Running
As a standalone script, no compilation or build process is necessary.

### Running the Tool
```bash
# Basic scan (targets ~/dev and system locations)
python3 badseed.py

# Scan specific directories
python3 badseed.py /path/to/projects

# Output results to a CSV file
python3 badseed.py --output results.csv

# Skip global system-level commands
python3 badseed.py --no-global
```

### Testing
- **Manual Verification:** Create a mock project with a `package.json` containing `"axios": "1.14.1"` and run the tool against it.
- **Verification Script:** (TODO) Implement a `test_badseed.sh` to automate the creation of mock compromised environments and verify detections.

## Development Conventions

### Zero Dependencies
To ensure the tool is fast and can run on any system without installation overhead, it **must not** use any non-standard library packages (e.g., no `requests`, `pandas`, or `toml`).

### Performance-First Scanning
- **Directory Walking:** Uses `os.walk` while explicitly removing heavy directories like `.git`, `node_modules` (internals), and `__pycache__` from the walk to prevent deep recursion into irrelevant files.
- **Targeted Lockfile Parsing:** Instead of full JSON/TOML parsing for all files, it uses targeted `json.load` for standard files and specialized regex for others (like `poetry.lock` or `pyproject.toml`) to maintain speed.
- **System Interrogation:** Executes ecosystem-specific commands (`npm list -g`, `pip list`, `brew list`) once per run to gather global state efficiently.

### Version Matching Logic
- **Semantic Versioning:** Supports standard semver operators in `compromised.json` including `==`, `>`, `>=`, `<`, `<=`, `~` (tilde), and `^` (caret).
- **Normalization:** Automatically strips common version prefixes (like `v`, `^`, `~`) from detected versions before comparison to ensure robust matching.
- **Ecosystem Isolation:** Maintain separate compromise lists for Python and npm to avoid false positives across ecosystems.
