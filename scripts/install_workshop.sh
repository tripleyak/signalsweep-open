#!/usr/bin/env bash
set -euo pipefail

VERSION="3.28.3"
SKILL_URL="https://github.com/tripleyak/signalsweep-open/releases/download/v${VERSION}/signalsweep-open.skill"
EXPECTED_SHA256="15a066b1b38b8f7bbc516c40a85540a5ed8f6fa2b089efc5f2cf90dcca720524"

export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-}"

log() {
  printf '%s\n' "$*"
}

fail() {
  printf 'SignalSweep install failed: %s\n' "$*" >&2
  exit 1
}

need_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

python_ok() {
  "$1" - "$2" <<'PY' >/dev/null 2>&1
import sys
minimum = tuple(map(int, sys.argv[1].split(".")))
raise SystemExit(0 if sys.version_info[:2] >= minimum else 1)
PY
}

find_python() {
  for candidate in python3.13 python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && python_ok "$candidate" "3.12"; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

ensure_python() {
  if py="$(find_python)"; then
    printf '%s\n' "$py"
    return 0
  fi

  if command -v brew >/dev/null 2>&1; then
    printf '%s\n' "Installing Python 3.12 with Homebrew..." >&2
    HOMEBREW_NO_AUTO_UPDATE=1 brew install python@3.12 >/dev/null
    if py="$(find_python)"; then
      printf '%s\n' "$py"
      return 0
    fi
  fi

  fail "SignalSweep needs Python 3.12+. Install Homebrew and run: brew install python@3.12"
}

sha256_file() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    fail "missing checksum tool: shasum or sha256sum"
  fi
}

backup_if_private_or_unknown() {
  skill_dir="$1/signalsweep"
  if [ ! -d "$skill_dir" ]; then
    return 0
  fi
  if [ -f "$skill_dir/SKILL.md" ] && grep -q '^public-profile: true' "$skill_dir/SKILL.md"; then
    return 0
  fi

  stamp="$(date +%Y%m%d-%H%M%S)"
  backup="${skill_dir}.backup-${stamp}"
  log "Existing non-public SignalSweep install found; backing it up to ${backup}"
  mv "$skill_dir" "$backup"
}

install_into() {
  target_root="$1"
  mkdir -p "$target_root"
  backup_if_private_or_unknown "$target_root"
  unzip -q -o "$SKILL_FILE" -d "$target_root"
}

need_command curl
need_command unzip

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
SKILL_FILE="$TMP_DIR/signalsweep-open.skill"

log "Downloading SignalSweep Open v${VERSION}..."
curl -L --fail --silent --show-error -o "$SKILL_FILE" "$SKILL_URL"

actual_sha="$(sha256_file "$SKILL_FILE")"
if [ "$actual_sha" != "$EXPECTED_SHA256" ]; then
  fail "checksum mismatch. Expected ${EXPECTED_SHA256}, got ${actual_sha}"
fi
log "Checksum verified: ${actual_sha}"

SIGNALSWEEP_PYTHON="$(ensure_python)"
py_version="$("$SIGNALSWEEP_PYTHON" - <<'PY'
import sys
print(sys.version.split()[0])
PY
)"
log "Using Python ${py_version}: ${SIGNALSWEEP_PYTHON}"

install_into "$HOME/.claude/skills"
install_into "$HOME/.codex/skills"

"$SIGNALSWEEP_PYTHON" "$HOME/.claude/skills/signalsweep/scripts/signalsweep.py" setup --free-public-keys --write-template >/dev/null
if [ -f "$HOME/.config/signalsweep/.env" ]; then
  chmod 600 "$HOME/.config/signalsweep/.env" 2>/dev/null || true
fi

log ""
log "SignalSweep Open v${VERSION} installed for Claude Code and Codex."
log "Free public-key template: $HOME/.config/signalsweep/.env"
log ""
log "Restart Claude Code and Codex, then test with:"
log "  /signalsweep pickleball paddle grip sweaty hands"
