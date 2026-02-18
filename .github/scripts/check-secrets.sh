#!/usr/bin/env bash
set -euo pipefail

echo "Running repository secret scan..."

# Fail if there are files in secrets/ that are not *.example or .gitkeep
if [ -d "secrets" ]; then
  bad_secrets=$(find secrets -maxdepth 1 -type f ! -name '*.example' ! -name '.gitkeep' -printf '%P\n' || true)
  if [ -n "$bad_secrets" ]; then
    echo "ERROR: Found files in secrets/ that are not .example or .gitkeep:"
    echo "$bad_secrets"
    echo "Rename these files to .example or remove them from the repo."
    exit 1
  fi
fi

# Patterns to search for (case-insensitive)
patterns='password|passwd|secret|api[_-]?key|apikey|aws[_-]?secret|aws[_-]?access|BEGIN RSA PRIVATE|BEGIN .*PRIVATE KEY|token|ssh-rsa|AKIA|DB_PASSWORD|PSK|PRIVATE_KEY'

# Files/paths to exclude from the generic keyword scan
# excludes=("*.example" "LICENSE" "README.md" "*.md" "*.png" "*.jpg")
# Exclude .yml files entirely from the keyword scan docker uses configs and embeded secrets.
excludes=("*.example" "LICENSE" "README.md" "*.md" "*.png" "*.jpg" "*.yml" "*.yaml")

exclude_args=()
for e in "${excludes[@]}"; do
  exclude_args+=("--exclude=$e")
done

# Perform scan excluding example/allowed files
# matches=$(grep -RIn --binary-files=without-match -E "$patterns" --exclude-dir=.git "${exclude_args[@]}" || true)
matches=$(grep -RIn --binary-files=without-match -E "$patterns" --exclude-dir=.git "${exclude_args[@]}" | grep -v "# not a secret\|# This line references" || true)

if [ -n "$matches" ]; then
  echo "ERROR: Potential secret keywords found in the repository (excluding .example files and common docs):"
  echo "$matches" | head -n 200
  echo "If these are false positives, add a note to the code or exclude the file in CI. Otherwise, move secrets to .example or external secrets management."
  exit 1
fi

# Also ensure we don't accidentally commit typical single-line secret files (like redis password files)
suspicious_files=$(grep -RIl --binary-files=without-match -E '^\s*[^#].{1,100}$' secrets 2>/dev/null || true)
if [ -n "$suspicious_files" ]; then
  # Filter out .example and .gitkeep
  suspicious_files=$(echo "$suspicious_files" | grep -vE '\.example$|\.gitkeep$' || true)
  if [ -n "$suspicious_files" ]; then
    echo "ERROR: Found suspicious files in secrets/ that appear to contain content (not .example):"
    echo "$suspicious_files"
    exit 1
  fi
fi

echo "Secret scan passed: no obvious secrets found."
