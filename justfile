# BadSeed justfile

# Run a basic scan of ~/dev and global system locations
scan:
    python3 badseed.py

# Find all uses of tracked libraries regardless of version
scan-all:
    python3 badseed.py --all-versions --output all_results.csv

# Scan specific directories
scan-dir path:
    python3 badseed.py {{path}}

# Output results to a CSV file
scan-csv output="results.csv":
    python3 badseed.py --output {{output}}

# Format the python file consistently
format:
    uv run --group dev ruff format badseed.py

# Lint the python file
lint:
    uv run --group dev ruff check badseed.py
    uv run --group dev ruff format --check badseed.py

# Fix fixable lint errors
lint-fix:
    uv run --group dev ruff check --fix badseed.py

# Run a quick test against a mock project
test:
    mkdir -p test_mock && echo '{"dependencies": {"axios": "1.14.1"}}' > test_mock/package.json
    python3 badseed.py test_mock
    rm -rf test_mock

# Edit the config file
config:
    $EDITOR config.json

# Run everything (format, lint, and a basic scan)
all: format lint-fix lint scan
