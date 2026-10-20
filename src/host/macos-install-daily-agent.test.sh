#!/usr/bin/env bash
# Installs the daily LaunchAgent into a temp home. launchctl is a stub.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$ROOT/src/host/macos-install-daily-agent.sh"
BIN="$(mktemp -d)"
IO_DIR="$(mktemp -d)"
HOME_DIR="$(mktemp -d)"

fail() { echo "FAIL: $*" >&2; exit 1; }

cat >"$BIN/launchctl-stub" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
dir="${EMAILS_ASSISTANT_STUB_DIR:?}"
printf '%s\n' "$*" >>"$dir/calls"
if [[ "$1" == "bootout" ]]; then
  exit 1
fi
EOF
cat >"$BIN/docker-stub" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
dir="${EMAILS_ASSISTANT_STUB_DIR:?}"
printf '%s\n' "$1" >>"$dir/docker_cmds"
if [[ "$1" == "image" ]]; then
  exit 1
fi
if [[ "$1" == "build" ]]; then
  exit 0
fi
exit 1
EOF
chmod +x "$BIN/launchctl-stub" "$BIN/docker-stub"

[[ -f "$SCRIPT" ]] || fail "missing $SCRIPT"

HOME="$HOME_DIR" \
EMAILS_ASSISTANT_LAUNCHCTL="$BIN/launchctl-stub" \
EMAILS_ASSISTANT_DOCKER="$BIN/docker-stub" \
EMAILS_ASSISTANT_STUB_DIR="$IO_DIR" \
  "$SCRIPT"

installed="$HOME_DIR/Library/LaunchAgents/com.emails-assistant.daily.plist"
[[ -f "$installed" ]] || fail "plist was not installed"
[[ "$(cat "$installed")" != *REPLACE_WITH_REPO* ]] || fail "placeholder left in the installed plist"
[[ "$(cat "$installed")" == *"$ROOT/src/host/macos-daily.sh"* ]] || fail "script path was not substituted"
[[ "$(cat "$ROOT/src/host/com.emails-assistant.daily.plist")" == *REPLACE_WITH_REPO* ]] || fail "repo plist was rewritten"

domain="gui/$(id -u)"
[[ "$(sed -n '1p' "$IO_DIR/calls")" == "bootout ${domain} ${installed}" ]] || fail "bootout: $(sed -n '1p' "$IO_DIR/calls")"
[[ "$(sed -n '2p' "$IO_DIR/calls")" == "bootstrap ${domain} ${installed}" ]] || fail "bootstrap: $(sed -n '2p' "$IO_DIR/calls")"
[[ "$(grep -c '^build$' "$IO_DIR/docker_cmds")" -eq 1 ]] || fail "install did not build the image"

echo "ok"
