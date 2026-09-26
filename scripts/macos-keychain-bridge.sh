#!/usr/bin/env bash
# Mac host only: Keychain ↔ .creds/ files for Dev Container Python (no host pip).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CREDS="${EMAILS_ASSISTANT_CREDS_DIR:-$ROOT/.creds}"
SERVICE="${EMAILS_ASSISTANT_KEYCHAIN_SERVICE:-emails-assistant}"
CLIENT_ACCOUNT="oauth-client"

die() { echo "error: $*" >&2; exit 1; }

need_macos() {
  [[ "$(uname -s)" == "Darwin" ]] || die "run on Mac host, not in Linux container"
}

cmd="${1:-}"
shift || true

case "$cmd" in
  export-client)
    need_macos
    mkdir -p "$CREDS"
    chmod 700 "$CREDS"
    out="$CREDS/client.json"
    security find-generic-password -s "$SERVICE" -a "$CLIENT_ACCOUNT" -w >"$out"
    chmod 600 "$out"
    echo "wrote $out"
    ;;
  export-token)
    need_macos
    alias="${1:-}"
    [[ -n "$alias" ]] || die "usage: $0 export-token <email1|email2>"
    mkdir -p "$CREDS"
    chmod 700 "$CREDS"
    out="$CREDS/token-${alias}.json"
    security find-generic-password -s "$SERVICE" -a "token/${alias}" -w >"$out"
    chmod 600 "$out"
    echo "wrote $out"
    ;;
  import-token)
    need_macos
    alias="${1:-}"
    [[ -n "$alias" ]] || die "usage: $0 import-token <email1|email2>"
    src="$CREDS/token-${alias}.json"
    [[ -f "$src" ]] || die "missing $src (run login in Dev Container first)"
    security add-generic-password -s "$SERVICE" -a "token/${alias}" -w "$(cat "$src")" -U
    echo "stored Keychain token/${alias}"
    ;;
  cleanup)
    need_macos
    if [[ -d "$CREDS" ]]; then
      rm -f "$CREDS"/client.json "$CREDS"/token-*.json
      rmdir "$CREDS" 2>/dev/null || true
      echo "cleared $CREDS"
    else
      echo "nothing to clear"
    fi
    ;;
  *)
    cat <<EOF
usage: $0 <command>

Mac host (Keychain) ↔ .creds/ bridge — Python runs in Dev Container.

  export-client          Keychain oauth-client → .creds/client.json
  export-token <alias>   Keychain token/<alias> → .creds/token-<alias>.json
  import-token <alias>   .creds/token-<alias>.json → Keychain
  cleanup                delete .creds client/token files

Login flow:
  1) Mac:  $0 export-client
  2) Dev Container:
       python -m emails_assistant.cli login email1 \\
         --client-file .creds/client.json \\
         --token-file .creds/token-email1.json \\
         --oauth-port 8765 --no-browser
     Open the printed URL on the Mac; allow port 8765 forward if asked.
  3) Mac:  $0 import-token email1 && $0 cleanup

Smoke flow:
  1) Mac:  $0 export-token email1
  2) Dev Container:
       python -m emails_assistant.cli smoke email1 \\
         --token-file .creds/token-email1.json
  3) Mac:  $0 import-token email1 && $0 cleanup
     (re-import in case the access token was refreshed)
EOF
    [[ -n "$cmd" ]] && exit 1 || exit 0
    ;;
esac
