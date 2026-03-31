#!/usr/bin/env python3
import argparse
import csv
import glob
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

# Configuration
SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_FILE = SCRIPT_DIR / 'config.json'


def load_config() -> Dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f'Warning: Failed to load {CONFIG_FILE}: {e}', file=sys.stderr)
    return {}


CONFIG = load_config()
TRACKED_LIBRARIES = CONFIG.get('libraries', {})


@dataclass
class Finding:
    library: str
    version: str
    location: str
    ecosystem: str


class BadSeed:
    def __init__(self, root_paths: List[str], scan_global: bool = True, all_versions: bool = False):
        self.root_paths = [Path(p).expanduser() for p in root_paths]
        self.scan_global = scan_global
        self.all_versions = all_versions
        self.findings: List[Finding] = []
        self._seen: set = set()

    def run(self):
        if self.scan_global:
            self._scan_npm_global()
            self._scan_pip_global()
            self._scan_homebrew()

        for path in self.root_paths:
            if path.exists():
                self._scan_directory(path)

    def _scan_npm_global(self):
        try:
            output = subprocess.check_output(['npm', 'list', '-g', '--depth=0', '--json'], stderr=subprocess.DEVNULL)
            data = json.loads(output)
            deps = data.get('dependencies', {})
            for name, info in deps.items():
                version = info.get('version')
                if self._is_tracked('npm', name, version):
                    self._add_finding(Finding(name, version, 'Global NPM', 'npm'))
        except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
            pass

    def _scan_pip_global(self):
        try:
            output = subprocess.check_output(
                [sys.executable, '-m', 'pip', 'list', '--format=json'], stderr=subprocess.DEVNULL
            )
            data = json.loads(output)
            for pkg in data:
                name = pkg.get('name')
                version = pkg.get('version')
                if self._is_tracked('python', name, version):
                    self._add_finding(Finding(name, version, 'Global Python', 'python'))
        except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
            pass

    def _scan_homebrew(self):
        try:
            output = subprocess.check_output(['brew', 'list', '--versions'], stderr=subprocess.DEVNULL).decode()
            for line in output.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0]
                    versions = parts[1:]
                    for version in versions:
                        if self._is_tracked('npm', name, version) or self._is_tracked('python', name, version):
                            self._add_finding(Finding(name, version, 'Homebrew', 'homebrew'))
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    _SKIP_DIRS = {'.git', '__pycache__', '.tox', '.nox', '.mypy_cache', '.pytest_cache', '.ruff_cache', 'dist', 'build', '.eggs'}

    def _scan_directory(self, root_path: Path):
        for root, dirs, files in os.walk(root_path):
            dirs[:] = [d for d in dirs if d not in self._SKIP_DIRS]

            for file in files:
                path = Path(root) / file
                if file == 'package.json':
                    self._parse_package_json(path)
                elif file == 'package-lock.json':
                    self._parse_package_lock(path)
                elif file == 'yarn.lock':
                    self._parse_yarn_lock(path)
                elif file == 'requirements.txt':
                    self._parse_requirements_txt(path)
                elif file == 'poetry.lock':
                    self._parse_poetry_lock(path)
                elif file == 'pyproject.toml':
                    self._parse_pyproject_toml(path)
                elif file == 'Pipfile.lock':
                    self._parse_pipfile_lock(path)
                elif file == 'uv.lock':
                    self._parse_uv_lock(path)
                elif file == 'pixi.lock':
                    self._parse_pixi_lock(path)

            if 'node_modules' in dirs:
                self._scan_node_modules(Path(root) / 'node_modules')
                dirs.remove('node_modules')

            for venv_name in ('venv', '.venv', 'env', '.env'):
                if venv_name in dirs:
                    self._scan_venv(Path(root) / venv_name)
                    dirs.remove(venv_name)

    def _add_finding(self, finding: Finding):
        key = (finding.library, finding.version, finding.location, finding.ecosystem)
        if key not in self._seen:
            self._seen.add(key)
            self.findings.append(finding)

    def _is_tracked(self, ecosystem: str, name: str, version: str) -> bool:
        if not name:
            return False
        name = name.lower().strip()
        targets = TRACKED_LIBRARIES.get(ecosystem, {})
        if self.all_versions:
            return name in targets
        if not version:
            return False
        version = version.lstrip('v').strip()
        specs = targets.get(name, [])
        for spec in specs:
            if self._matches_spec(version, spec):
                return True
        return False

    def _version_to_tuple(self, v: str) -> tuple:
        parts = []
        for x in re.split(r'[^0-9]', v):
            if x.isdigit():
                parts.append(int(x))
        return tuple(parts)

    def _matches_spec(self, version: str, spec: str) -> bool:
        version = version.lstrip('^~>=<v').strip()
        spec = spec.strip()
        match = re.match(r'^([<>~^=!]+)?\s*(.*)$', spec)
        if not match:
            return False
        op, spec_ver = match.groups()
        spec_ver = spec_ver.lstrip('v').strip()

        if not op or op == '==':
            return version == spec_ver

        v_parts = self._version_to_tuple(version)
        s_parts = self._version_to_tuple(spec_ver)

        if op == '>':
            return v_parts > s_parts
        if op == '>=':
            return v_parts >= s_parts
        if op == '<':
            return v_parts < s_parts
        if op == '<=':
            return v_parts <= s_parts
        if op == '!=':
            return v_parts != s_parts
        if op == '~':
            # ~1.2.3 matches >=1.2.3 <1.3.0
            if len(s_parts) >= 2:
                upper = list(s_parts[:2])
                upper[1] += 1
                return v_parts >= s_parts and v_parts < tuple(upper)
            return v_parts >= s_parts
        if op == '^':
            # ^1.2.3 matches >=1.2.3 <2.0.0
            if len(s_parts) >= 1:
                upper = [s_parts[0] + 1]
                return v_parts >= s_parts and v_parts < tuple(upper)
            return v_parts >= s_parts
        return False

    def _parse_package_json(self, path: Path):
        try:
            with open(path) as f:
                data = json.load(f)
                for dep_type in ['dependencies', 'devDependencies']:
                    deps = data.get(dep_type, {})
                    for name, version in deps.items():
                        if self._is_tracked('npm', name, version):
                            self._add_finding(Finding(name, version, str(path), 'npm'))
        except (json.JSONDecodeError, OSError):
            pass

    def _parse_package_lock(self, path: Path):
        try:
            with open(path) as f:
                data = json.load(f)
                packages = data.get('packages', {})
                for pkg_path, info in packages.items():
                    name = pkg_path.split('node_modules/')[-1] if 'node_modules/' in pkg_path else info.get('name')
                    version = info.get('version')
                    if self._is_tracked('npm', name, version):
                        self._add_finding(Finding(name or 'unknown', version, str(path), 'npm'))
                deps = data.get('dependencies', {})
                for name, info in deps.items():
                    version = info.get('version')
                    if self._is_tracked('npm', name, version):
                        self._add_finding(Finding(name, version, str(path), 'npm'))
        except (json.JSONDecodeError, OSError):
            pass

    def _parse_yarn_lock(self, path: Path):
        try:
            with open(path) as f:
                content = f.read()
                for name in TRACKED_LIBRARIES.get('npm', {}):
                    escaped = re.escape(name)
                    # Yarn v1
                    v1_matches = re.findall(
                        rf'^"?{escaped}@.*:$\n\s+version\s+"([^"]+)"', content, re.MULTILINE
                    )
                    # Yarn v2+ (berry)
                    v2_matches = re.findall(
                        rf'"?{escaped}@npm:[^"]+\":\n\s+version:\s+([^\n\s]+)', content, re.MULTILINE
                    )
                    for version in v1_matches + v2_matches:
                        if self._is_tracked('npm', name, version):
                            self._add_finding(Finding(name, version, str(path), 'npm'))
        except OSError:
            pass

    def _parse_requirements_txt(self, path: Path):
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    # Handle common operators in requirements.txt
                    match = re.match(r'^([a-zA-Z0-9\[\]_-]+)\s*([<>~=!].*)$', line)
                    if match:
                        name, version = match.groups()
                        name = name.split('[')[0].strip()
                        version = version.split(';')[0].strip()
                        if self._is_tracked('python', name, version):
                            self._add_finding(Finding(name, version, str(path), 'python'))
                    elif '==' in line:
                        name, version = line.split('==', 1)
                        name = name.split('[')[0].strip()
                        version = version.split(';')[0].strip()
                        if self._is_tracked('python', name, version):
                            self._add_finding(Finding(name, version, str(path), 'python'))
        except OSError:
            pass

    def _parse_poetry_lock(self, path: Path):
        try:
            with open(path) as f:
                content = f.read()
                packages = re.findall(r'\[\[package\]\]\nname = "(.*?)"\nversion = "(.*?)"', content, re.MULTILINE)
                for name, version in packages:
                    if self._is_tracked('python', name, version):
                        self._add_finding(Finding(name, version, str(path), 'python'))
        except OSError:
            pass

    def _parse_uv_lock(self, path: Path):
        # uv.lock is TOML, similar structure to poetry.lock
        self._parse_poetry_lock(path)

    def _parse_pixi_lock(self, path: Path):
        try:
            with open(path) as f:
                content = f.read()
                for name in TRACKED_LIBRARIES.get('python', {}):
                    escaped = re.escape(name)
                    matches = re.findall(
                        rf'pypi/{escaped}:\s*\n\s+version:\s+([^\s\n]+)', content, re.MULTILINE
                    )
                    for version in matches:
                        if self._is_tracked('python', name, version):
                            self._add_finding(Finding(name, version, str(path), 'python'))
        except OSError:
            pass

    def _parse_pyproject_toml(self, path: Path):
        try:
            with open(path) as f:
                content = f.read()
                # Poetry-style: name = "version" or name = { version = "..." }
                matches = re.findall(r'([a-zA-Z0-9_-]+)\s*=\s*(?:"|{ version = ")(.*?)(?:"|")(\s*[,}])?', content)
                for name, version, *_ in matches:
                    if self._is_tracked('python', name, version):
                        self._add_finding(Finding(name, version, str(path), 'python'))
                # PEP 621-style: dependencies = ["litellm>=1.82.8", ...]
                pep621 = re.findall(r'"([a-zA-Z0-9_-]+)\s*([<>~=!][^"]*?)"', content)
                for name, version in pep621:
                    if self._is_tracked('python', name, version):
                        self._add_finding(Finding(name, version, str(path), 'python'))
        except OSError:
            pass

    def _parse_pipfile_lock(self, path: Path):
        try:
            with open(path) as f:
                data = json.load(f)
                for section in ['default', 'develop']:
                    pkgs = data.get(section, {})
                    for name, info in pkgs.items():
                        version = info.get('version', '').strip()
                        if self._is_tracked('python', name, version):
                            self._add_finding(Finding(name, version, str(path), 'python'))
        except (json.JSONDecodeError, OSError):
            pass

    def _scan_node_modules(self, nm_path: Path):
        for ecosystem, targets in TRACKED_LIBRARIES.items():
            if ecosystem != 'npm':
                continue
            for name in targets:
                pkg_json = nm_path / name / 'package.json'
                if pkg_json.exists():
                    try:
                        with open(pkg_json) as f:
                            data = json.load(f)
                            version = data.get('version')
                            if self._is_tracked('npm', name, version):
                                self._add_finding(Finding(name, version, str(pkg_json), 'npm'))
                    except (json.JSONDecodeError, OSError):
                        pass

    def _scan_venv(self, venv_path: Path):
        lib_dir = venv_path / 'lib'
        if not lib_dir.exists():
            return
        for py_dir in lib_dir.glob('python*'):
            site_packages = py_dir / 'site-packages'
            if site_packages.exists():
                for dist in site_packages.glob('*.dist-info'):
                    try:
                        name_ver = dist.stem.split('-')
                        if len(name_ver) >= 2:
                            name, version = name_ver[0], name_ver[1]
                            if self._is_tracked('python', name, version):
                                self._add_finding(Finding(name, version, str(site_packages), 'python'))
                    except (IndexError, ValueError):
                        pass

    def export_csv(self, output_path: Optional[str] = None):
        fieldnames = ['Library', 'Version', 'Location', 'Ecosystem']
        out = open(output_path, 'w', newline='') if output_path else sys.stdout
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        for f in self.findings:
            writer.writerow(
                {'Library': f.library, 'Version': f.version, 'Location': f.location, 'Ecosystem': f.ecosystem}
            )
        if output_path:
            out.close()


def main():
    parser = argparse.ArgumentParser(description='BadSeed: Scan for compromised libraries in your supply chain.')
    user_paths = list(CONFIG.get('user_paths', ['~/dev']))
    for p in CONFIG.get('system_paths', []):
        expanded = os.path.expanduser(p)
        matched = glob.glob(expanded)
        if matched:
            user_paths.extend(matched)
        elif os.path.exists(expanded):
            user_paths.append(expanded)
    parser.add_argument('paths', nargs='*', default=user_paths, help='Directories to scan recursively')
    parser.add_argument('--output', '-o', help='Output CSV file path')
    parser.add_argument('--no-global', action='store_true', help='Skip global/system level scans')
    parser.add_argument('--all-versions', '-a', action='store_true', help='Find all uses of tracked libraries regardless of version')
    args = parser.parse_args()
    paths = [os.path.expanduser(p) if p.startswith('~') else p for p in args.paths]
    scanner = BadSeed(paths, scan_global=not args.no_global, all_versions=args.all_versions)
    scanner.run()
    scanner.export_csv(args.output)


if __name__ == '__main__':
    main()
