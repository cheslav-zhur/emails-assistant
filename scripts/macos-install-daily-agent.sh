#!/usr/bin/env bash
# Install the per-user LaunchAgent for the daily digest. Run on the Mac.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.emails-assistant.daily"
SRC="$ROOT/scripts/${LABEL}.plist"
DEST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
DOMAIN="gui/$(id -u)"

launchctl_cmd() {
  if [[ -n "${EMAILS_ASSISTANT_LAUNCHCTL:-}" ]]; then
    "$EMAILS_ASSISTANT_LAUNCHCTL" "$@"
    return
  fi
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "error: run on the Mac, not in the Dev Container" >&2
    return 1
  fi
  command launchctl "$@"
}

mkdir -p "${HOME}/Library/LaunchAgents"
"$ROOT/scripts/macos-daily.sh" build-image
python3 -c '
import pathlib, sys
src, dst, root = sys.argv[1:]
text = pathlib.Path(src).read_text(encoding="utf-8")
if "REPLACE_WITH_REPO" not in text:
    raise SystemExit("plist is missing REPLACE_WITH_REPO")
path = root + "/scripts/macos-daily.sh"
pathlib.Path(dst).write_text(text.replace("REPLACE_WITH_REPO", root), encoding="utf-8")
if path not in pathlib.Path(dst).read_text(encoding="utf-8"):
    raise SystemExit("installed plist is missing the script path")
' "$SRC" "$DEST" "$ROOT"

# A second run replaces the already loaded agent. bootout fails when it is not loaded.
launchctl_cmd bootout "$DOMAIN" "$DEST" || true
launchctl_cmd bootstrap "$DOMAIN" "$DEST"
