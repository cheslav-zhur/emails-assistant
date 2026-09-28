#!/usr/bin/env bash
# Mac host: refresh Gmail access tokens from Keychain and hand off access tokens only.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE="${EMAILS_ASSISTANT_KEYCHAIN_SERVICE:-emails-assistant}"
RELOGIN_NOTICE="Login is required. The refresh token was rejected."
LEGACY_DIR="$ROOT/.creds"

read -r -d '' HOST_PY <<'PY' || true
import json
import sys
from datetime import datetime, timedelta
from urllib.parse import urlencode

THRESHOLD = timedelta(minutes=3, seconds=45)


def fail(code):
    sys.stderr.write("refresh payload was rejected\n")
    raise SystemExit(code)


def parts(expected):
    data = sys.stdin.buffer.read().split(b"\0")
    if data and data[-1] == b"":
        data = data[:-1]
    if len(data) != expected:
        fail(1)
    try:
        return [item.decode("utf-8") for item in data]
    except Exception:
        fail(1)


def parse_expiry(raw):
    if not isinstance(raw, str) or not raw.endswith("Z"):
        return None
    body = raw[:-1]
    if "+" in body or body.count("-") != 2:
        return None
    try:
        return datetime.strptime(body.split(".")[0], "%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None


def parse_now(raw):
    parsed = parse_expiry(raw.strip())
    if parsed is None:
        fail(1)
    return parsed


def loads(raw):
    try:
        value = json.loads(raw)
    except Exception:
        fail(1)
    if not isinstance(value, dict):
        fail(1)
    return value


def access_payload(token, expiry):
    return {"access_token": token, "expiry": expiry}


def main():
    cmd = sys.argv[1]
    if cmd == "needs-refresh":
        existing_raw, now_raw = parts(2)
        existing = loads(existing_raw)
        now = parse_now(now_raw)
        expiry = parse_expiry(existing.get("expiry"))
        due = expiry is None or now >= expiry - THRESHOLD
        sys.stdout.write("yes" if due else "no")
        return
    if cmd == "form-body":
        client_raw, token_raw = parts(2)
        client = loads(client_raw)
        token = loads(token_raw)
        installed = client.get("installed") or client.get("web") or {}
        if not isinstance(installed, dict):
            fail(1)
        fields = {
            "client_id": installed.get("client_id") or token.get("client_id"),
            "client_secret": installed.get("client_secret") or token.get("client_secret"),
            "refresh_token": token.get("refresh_token"),
            "grant_type": "refresh_token",
        }
        if not all(isinstance(fields[key], str) and fields[key] for key in ("client_id", "client_secret", "refresh_token")):
            fail(1)
        sys.stdout.write(urlencode(fields))
        return
    if cmd == "keep-plan":
        existing = loads(parts(1)[0])
        expiry = parse_expiry(existing.get("expiry"))
        token = existing.get("token")
        if expiry is None or not isinstance(token, str) or not token:
            fail(1)
        plan = {"payload": access_payload(token, existing["expiry"]), "write": None}
        sys.stdout.write(json.dumps(plan, separators=(",", ":")))
        return
    if cmd == "merge-plan":
        existing_raw, response_raw, now_raw = parts(3)
        existing = loads(existing_raw)
        try:
            response = json.loads(response_raw)
        except Exception:
            fail(1)
        if not isinstance(response, dict):
            fail(1)
        if "refresh_token" in response:
            fail(2)
        if response.get("error") == "invalid_grant":
            raise SystemExit(3)
        now = parse_now(now_raw)
        try:
            expires_in = int(response["expires_in"])
            access = response["access_token"]
        except Exception:
            fail(1)
        if not isinstance(access, str) or not access or expires_in < 0:
            fail(1)
        expiry = (now + timedelta(seconds=expires_in)).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        updated = dict(existing)
        updated["token"] = access
        updated["expiry"] = expiry
        plan = {"payload": access_payload(access, expiry), "write": updated}
        sys.stdout.write(json.dumps(plan, separators=(",", ":")))
        return
    if cmd == "plan-write":
        plan = loads(sys.stdin.read())
        write = plan.get("write", None)
        if write is None:
            sys.stdout.write("null")
        else:
            sys.stdout.write(json.dumps(write, separators=(",", ":")))
        return
    if cmd == "plan-payload":
        plan = loads(sys.stdin.read())
        payload = plan.get("payload")
        if not isinstance(payload, dict) or set(payload) != {"access_token", "expiry"}:
            fail(1)
        sys.stdout.write(json.dumps({"access_token": payload["access_token"], "expiry": payload["expiry"]}, separators=(",", ":")))
        return
    fail(1)


if __name__ == "__main__":
    main()
PY

host_py() {
  python3 -c "$HOST_PY" "$@"
}

die() {
  echo "error: $*" >&2
  return 1
}

need_macos() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "error: run on Mac host, not in Linux container" >&2
    return 1
  fi
}

security_cmd() {
  need_macos || return 1
  command security "$@"
}

docker_cmd() {
  need_macos || return 1
  command docker "$@"
}

curl_cmd() {
  command curl "$@"
}

now_utc() {
  if [[ -n "${EMAILS_ASSISTANT_NOW:-}" ]]; then
    printf '%s' "$EMAILS_ASSISTANT_NOW"
    return 0
  fi
  python3 -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z", end="")'
}

accounts() {
  local raw="${EMAILS_ASSISTANT_ACCOUNTS:-email1,email2}"
  local IFS=','
  local part
  local -a parts=()
  read -ra parts <<<"$raw"
  for part in "${parts[@]}"; do
    part="${part#"${part%%[![:space:]]*}"}"
    part="${part%"${part##*[![:space:]]}"}"
    if [[ -n "$part" ]]; then
      printf '%s\n' "$part"
    fi
  done
}

clear_legacy_creds() {
  local leftover=0 path nullglob_was=0
  shopt -q nullglob && nullglob_was=1
  shopt -s nullglob
  local paths=("$LEGACY_DIR"/client.json "$LEGACY_DIR"/token-*.json)
  for path in "${paths[@]}"; do
    if [[ -d "$path" && ! -L "$path" ]]; then
      leftover=1
      continue
    fi
    rm -f -- "$path" 2>/dev/null || true
    if [[ -e "$path" ]]; then
      leftover=1
    fi
  done
  if [[ "$nullglob_was" -eq 0 ]]; then
    shopt -u nullglob
  fi
  if [[ "$leftover" -ne 0 ]]; then
    echo "error: leftover credential file remains" >&2
    return 1
  fi
}

refresh_or_keep() {
  local alias="$1" client="$2" now="$3"
  local existing decision body response status
  existing="$(security_cmd find-generic-password -s "$SERVICE" -a "token/${alias}" -w)" || return 1
  decision="$(printf '%s\0%s\0' "$existing" "$now" | host_py needs-refresh)" || return 1
  if [[ "$decision" == "no" ]]; then
    printf '%s\0' "$existing" | host_py keep-plan
    return $?
  fi
  body="$(printf '%s\0%s\0' "$client" "$existing" | host_py form-body)" || return 1
  response="$(
    printf '%s' "$body" | curl_cmd -sS -X POST \
      -H "Content-Type: application/x-www-form-urlencoded" \
      --data-binary @- \
      https://oauth2.googleapis.com/token
  )" || return 1
  printf '%s\0%s\0%s\0' "$existing" "$response" "$now" | host_py merge-plan
}

collect_plans() {
  ALIAS_LIST=()
  PLANS=()
  local now client alias plan status=0
  now="$(now_utc)"
  client="$(security_cmd find-generic-password -s "$SERVICE" -a "oauth-client" -w)" || return 1
  while IFS= read -r alias; do
    [[ -n "$alias" ]] || continue
    status=0
    plan="$(refresh_or_keep "$alias" "$client" "$now")" || status=$?
    if [[ "$status" -ne 0 ]]; then
      if [[ "$status" -eq 3 ]]; then
        echo "$RELOGIN_NOTICE" >&2
      else
        echo "error: refresh was rejected" >&2
      fi
      return 1
    fi
    ALIAS_LIST+=("$alias")
    PLANS+=("$plan")
  done < <(accounts)
}

apply_writes() {
  local i alias write
  for i in "${!ALIAS_LIST[@]}"; do
    alias="${ALIAS_LIST[$i]}"
    write="$(printf '%s' "${PLANS[$i]}" | host_py plan-write)" || return 1
    if [[ "$write" != "null" ]]; then
      security_cmd add-generic-password -s "$SERVICE" -a "token/${alias}" -w "$write" -U >/dev/null || return 1
    fi
  done
}

print_payloads() {
  local i payload
  for i in "${!ALIAS_LIST[@]}"; do
    payload="$(printf '%s' "${PLANS[$i]}" | host_py plan-payload)" || return 1
    if [[ "$i" -gt 0 ]]; then
      printf '\n'
    fi
    printf '%s' "$payload"
  done
}

inject_payloads() {
  local container="$1" i alias payload
  for i in "${!ALIAS_LIST[@]}"; do
    alias="${ALIAS_LIST[$i]}"
    payload="$(printf '%s' "${PLANS[$i]}" | host_py plan-payload)" || return 1
    printf '%s' "$payload" | docker_cmd exec -i -u vscode "$container" python3 -c '
import sys
from emails_assistant.cli import write_access_token_file
write_access_token_file(sys.argv[1], sys.stdin.read())
' "$alias" || return 1
  done
}

cmd_one_shot() {
  clear_legacy_creds || return 1
  collect_plans || return 1
  apply_writes || return 1
  print_payloads
}

cmd_inject() {
  local container="${1:-}"
  if [[ -z "$container" || -n "${2:-}" ]]; then
    echo "error: usage: inject <container>" >&2
    return 1
  fi
  clear_legacy_creds || return 1
  collect_plans || return 1
  apply_writes || return 1
  inject_payloads "$container"
}

cmd_login() {
  local container="${1:-}" alias="${2:-}" client token_json
  if [[ -z "$container" || -z "$alias" || -n "${3:-}" ]]; then
    echo "error: usage: login <container> <alias>" >&2
    return 1
  fi
  clear_legacy_creds || return 1
  client="$(security_cmd find-generic-password -s "$SERVICE" -a "oauth-client" -w)" || return 1
  token_json="$(
    printf '%s' "$client" | docker_cmd exec -i -u vscode "$container" \
      python3 -m emails_assistant.cli login "$alias" --no-browser
  )" || return 1
  if [[ -z "$token_json" ]]; then
    echo "error: login returned no token" >&2
    return 1
  fi
  security_cmd add-generic-password -s "$SERVICE" -a "token/${alias}" -w "$token_json" -U >/dev/null
}

usage() {
  cat <<EOF
usage: $(basename "$0") <command>

  inject <container>     refresh due tokens and write access tokens into the container
  one-shot               refresh due tokens and print one access-token JSON per mailbox
  login <container> <alias>
                         store the mailbox token from container stdout into Keychain

Keychain and docker run on the Mac host. Mail runs receive an access token only.
EOF
}

main() {
  local cmd="${1:-}"
  if [[ -z "$cmd" ]]; then
    usage
    return 0
  fi
  shift
  case "$cmd" in
    inject) cmd_inject "$@" ;;
    one-shot) cmd_one_shot "$@" ;;
    login) cmd_login "$@" ;;
    *)
      usage >&2
      return 1
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
