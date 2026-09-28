#!/usr/bin/env bash
# Host refresh parser and handoff. No live Google, Keychain, or docker.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT/scripts/macos-access-token.sh"
# shellcheck source=../scripts/macos-access-token.sh
source "$SCRIPT"

REFRESH_SENTINEL='1//fixture+refresh='
SECRET_SENTINEL='fixture/client+secret='
NOW="2026-09-28T12:00:00Z"

fail() { echo "FAIL: $*" >&2; exit 1; }

IO_DIR=""

sec_file() {
  printf '%s\n' "$IO_DIR/sec_$(printf '%s' "$1" | tr '/' '_')"
}

security_cmd() {
  local account="" password=""
  if [[ "$1" == "find-generic-password" ]]; then
    shift
    while [[ $# -gt 0 ]]; do
      case "$1" in
        -a) account="$2"; shift 2 ;;
        *) shift ;;
      esac
    done
    [[ -f "$(sec_file "$account")" ]] || return 1
    cat "$(sec_file "$account")"
    return 0
  fi
  if [[ "$1" == "add-generic-password" ]]; then
    shift
    while [[ $# -gt 0 ]]; do
      case "$1" in
        -a) account="$2"; shift 2 ;;
        -w) password="$2"; shift 2 ;;
        *) shift ;;
      esac
    done
    printf '%s' "$password" >"$(sec_file "$account")"
    printf '%s\n' "$account" >>"$IO_DIR/sec_writes"
    return 0
  fi
  return 1
}

curl_cmd() {
  local n
  n="$(cat "$IO_DIR/curl_n")"
  printf '%s\n' "$*" >"$IO_DIR/curl_args.$n"
  cat >"$IO_DIR/curl_stdin.$n"
  echo $((n + 1)) >"$IO_DIR/curl_n"
  if [[ -f "$IO_DIR/resp.$n" ]]; then
    cat "$IO_DIR/resp.$n"
  fi
}

docker_cmd() {
  local n
  n="$(cat "$IO_DIR/docker_n")"
  printf '%s\n' "$*" >"$IO_DIR/docker_args.$n"
  cat >"$IO_DIR/docker_stdin.$n"
  echo $((n + 1)) >"$IO_DIR/docker_n"
  if [[ -n "${DOCKER_STDERR:-}" ]]; then
    printf '%s' "$DOCKER_STDERR" >&2
  fi
  if [[ -n "${DOCKER_STDOUT:-}" ]]; then
    printf '%s' "$DOCKER_STDOUT"
  fi
}

reset_io() {
  IO_DIR="$(mktemp -d)"
  echo 0 >"$IO_DIR/curl_n"
  echo 0 >"$IO_DIR/docker_n"
  echo 0 >"$IO_DIR/queue_n"
  : >"$IO_DIR/sec_writes"
  unset DOCKER_STDERR DOCKER_STDOUT
  export EMAILS_ASSISTANT_NOW="$NOW"
  export EMAILS_ASSISTANT_ACCOUNTS="email1,email2"
  export EMAILS_ASSISTANT_KEYCHAIN_SERVICE="emails-assistant"
}

queue_curl() {
  local n
  n="$(cat "$IO_DIR/queue_n")"
  printf '%s' "$1" >"$IO_DIR/resp.$n"
  echo $((n + 1)) >"$IO_DIR/queue_n"
}

curl_calls() { cat "$IO_DIR/curl_n"; }
docker_calls() { cat "$IO_DIR/docker_n"; }
sec_writes() { wc -l <"$IO_DIR/sec_writes" | tr -d ' '; }
sec_get() { cat "$(sec_file "$1")"; }

client_json() {
  printf '%s' "{\"installed\":{\"client_id\":\"client-id\",\"client_secret\":\"${SECRET_SENTINEL}\",\"token_uri\":\"https://oauth2.googleapis.com/token\"}}"
}

token_json() {
  local token="$1" expiry="$2" refresh="${3:-$REFRESH_SENTINEL}"
  printf '%s' "{\"token\":\"${token}\",\"refresh_token\":\"${refresh}\",\"token_uri\":\"https://oauth2.googleapis.com/token\",\"client_id\":\"client-id\",\"client_secret\":\"${SECRET_SENTINEL}\",\"expiry\":\"${expiry}\"}"
}

install_mailbox() {
  local alias="$1" token="$2" expiry="$3"
  token_json "$token" "$expiry" >"$(sec_file "token/${alias}")"
  client_json >"$(sec_file "oauth-client")"
}

assert_no_secret_output() {
  local blob="$1"
  [[ "$blob" != *"$REFRESH_SENTINEL"* ]] || fail "refresh token leaked: $blob"
  [[ "$blob" != *"$SECRET_SENTINEL"* ]] || fail "client secret leaked: $blob"
}

assert_access_only() {
  python3 -c '
import json, sys
obj = json.loads(sys.argv[1])
if set(obj) != {"access_token", "expiry"}:
    raise SystemExit("payload keys: %s" % sorted(obj))
if "refresh_token" in sys.argv[1] or "client_secret" in sys.argv[1]:
    raise SystemExit("secret field in payload")
' "$1"
}

repo_has_sentinel() {
  if grep -R -n -e "$REFRESH_SENTINEL" -e "$SECRET_SENTINEL" \
    --exclude-dir=.git \
    --exclude=test_host_refresh.sh \
    "$ROOT" >/dev/null
  then
    return 0
  fi
  return 1
}

if grep -n '\.creds/' "$SCRIPT" >/dev/null; then
  fail "script contains a .creds/ path"
fi
[[ ! -f "$ROOT/scripts/macos-keychain-bridge.sh" ]] || fail "old bridge script still exists"

# Parser runs without the Darwin guard.
decision="$(printf '%s\0%s\0' "$(token_json ya29-old "$NOW")" "$NOW" | host_py needs-refresh)"
[[ "$decision" == "yes" ]] || fail "parser did not run off the Mac (got $decision)"

reset_io
install_mailbox email1 ya29-still-good "2026-09-28T12:10:00Z"
install_mailbox email2 ya29-still-good-2 "2026-09-28T12:10:00Z"
stdout="$(cmd_one_shot)"
[[ "$(curl_calls)" -eq 0 ]] || fail "fresh token was refreshed"
[[ "$(docker_calls)" -eq 0 ]] || fail "one-shot called docker"
mapfile -t lines <<<"$stdout"
[[ "${#lines[@]}" -eq 2 ]] || fail "expected two payloads, got ${#lines[@]}"
assert_access_only "${lines[0]}"
assert_access_only "${lines[1]}"
[[ "${lines[0]}" == *'ya29-still-good'* ]] || fail "email1 payload missing"
[[ "${lines[1]}" == *'ya29-still-good-2'* ]] || fail "email2 payload missing"
assert_no_secret_output "$stdout"

reset_io
install_mailbox email1 ya29-old-access "2026-09-28T12:02:00Z"
install_mailbox email2 ya29-old-access-2 "2026-09-28T12:02:00Z"
queue_curl '{"access_token":"ya29-new-access","expires_in":3600,"token_type":"Bearer","scope":"mail"}'
queue_curl '{"access_token":"ya29-new-access-2","expires_in":3600,"token_type":"Bearer"}'
TZ=Asia/Ho_Chi_Minh stdout="$(cmd_one_shot)"
[[ "$(curl_calls)" -eq 2 ]] || fail "due tokens were not both refreshed"
[[ "$(cat "$IO_DIR/curl_stdin.0")" == *'1%2F%2Ffixture%2Brefresh%3D'* ]] || fail "refresh token was not form-encoded"
[[ "$(cat "$IO_DIR/curl_stdin.0")" != *"$REFRESH_SENTINEL"* ]] || fail "raw refresh token was on curl stdin"
[[ "$(cat "$IO_DIR/curl_stdin.0")" != *"$SECRET_SENTINEL"* ]] || fail "raw client secret was on curl stdin"
[[ "$(cat "$IO_DIR/curl_args.0")" != *"$REFRESH_SENTINEL"* ]] || fail "refresh token was a curl argument"
[[ "$(cat "$IO_DIR/curl_args.0")" != *"$SECRET_SENTINEL"* ]] || fail "client secret was a curl argument"
stored="$(sec_get token/email1)"
python3 -c '
import json, sys
obj = json.loads(sys.argv[1])
if obj["token"] != "ya29-new-access":
    raise SystemExit("token not updated")
if obj["expiry"] != "2026-09-28T13:00:00Z":
    raise SystemExit("expiry %s" % obj["expiry"])
if "+" in obj["expiry"] or not obj["expiry"].endswith("Z"):
    raise SystemExit("expiry is not naive UTC Z")
for key in ("refresh_token", "client_id", "client_secret", "token_uri"):
    if obj[key] != sys.argv[2] and key == "refresh_token":
        raise SystemExit("refresh_token changed")
if obj["refresh_token"] != sys.argv[2]:
    raise SystemExit("refresh_token changed")
if obj["client_id"] != "client-id" or obj["client_secret"] != sys.argv[3]:
    raise SystemExit("client fields changed")
if obj["token_uri"] != "https://oauth2.googleapis.com/token":
    raise SystemExit("token_uri changed")
' "$stored" "$REFRESH_SENTINEL" "$SECRET_SENTINEL"
mapfile -t lines <<<"$stdout"
assert_access_only "${lines[0]}"
assert_access_only "${lines[1]}"
[[ "${lines[0]}" == *'ya29-new-access'* ]] || fail "new access token was not passed on"
[[ "${lines[1]}" == *'ya29-new-access-2'* ]] || fail "email2 new token missing"
assert_no_secret_output "$stdout"
repo_has_sentinel && fail "refresh left a secret file in the repo"

reset_io
install_mailbox email1 ya29-email1-old "2026-09-28T12:02:00Z"
install_mailbox email2 ya29-email2-old "2026-09-28T12:02:00Z"
queue_curl '{"access_token":"ya29-email1-new","expires_in":3600,"token_type":"Bearer"}'
queue_curl '{"error":"invalid_grant","error_description":"ya29-should-not-leak"}'
set +e
stdout="$(cmd_one_shot 2>/tmp/ea-host-err.$$)"
status=$?
set -e
err="$(cat /tmp/ea-host-err.$$)"
rm -f /tmp/ea-host-err.$$
[[ "$status" -ne 0 ]] || fail "invalid_grant exited 0"
[[ "$stdout" != *'ya29-'* ]] || fail "one-shot stdout was a token"
[[ "$err" == *"Login is required."* ]] || fail "missing re-login notice: $err"
[[ "$err" != *'ya29-should-not-leak'* ]] || fail "error body leaked"
assert_no_secret_output "${stdout}${err}"
[[ "$(sec_get token/email1)" == *'ya29-email1-old'* ]] || fail "email1 token was replaced"
[[ "$(sec_writes)" -eq 0 ]] || fail "keychain write on failed refresh"
repo_has_sentinel && fail "failed refresh left a secret file in the repo"

reset_io
install_mailbox email1 ya29-old-access "2026-09-28T12:02:00Z"
export EMAILS_ASSISTANT_ACCOUNTS="email1"
queue_curl '{"access_token":"ya29-new-access","expires_in":3600,"refresh_token":"new-refresh-should-not-store"}'
set +e
cmd_one_shot >/tmp/ea-host-out.$$ 2>/tmp/ea-host-err.$$
status=$?
set -e
[[ "$status" -ne 0 ]] || fail "unexpected refresh_token was accepted"
[[ "$(sec_writes)" -eq 0 ]] || fail "keychain write after refresh_token response"
rm -f /tmp/ea-host-out.$$ /tmp/ea-host-err.$$

reset_io
install_mailbox email1 ya29-old-access "2026-09-28T19:00:00+07:00"
export EMAILS_ASSISTANT_ACCOUNTS="email1"
queue_curl '{"access_token":"ya29-from-offset","expires_in":3600,"token_type":"Bearer"}'
TZ=Asia/Ho_Chi_Minh stdout="$(cmd_one_shot)"
[[ "$(curl_calls)" -eq 1 ]] || fail "+07 expiry was treated as a future UTC expiry"
[[ "$stdout" == *'ya29-from-offset'* ]] || fail "offset expiry did not refresh"
[[ "$(sec_get token/email1)" == *'2026-09-28T13:00:00Z'* ]] || fail "stored expiry was not UTC Z"
[[ "$(sec_get token/email1)" != *'+07'* ]] || fail "stored +07 timestamp"

reset_io
install_mailbox email1 ya29-inject-access "2026-09-28T12:10:00Z"
export EMAILS_ASSISTANT_ACCOUNTS="email1"
container_copy="/dev/shm/emails-assistant/access-email1.json"
mkdir -p "$(dirname "$container_copy")"
printf '%s' 'dev-container-token-original' >"$container_copy"
stdout="$(cmd_one_shot)"
[[ "$(cat "$container_copy")" == "dev-container-token-original" ]] || fail "one-shot wrote the dev container token"
[[ "$(docker_calls)" -eq 0 ]] || fail "one-shot touched docker"
assert_access_only "$stdout"

set +e
cmd_inject "box-name" "$SECRET_SENTINEL" >/dev/null 2>&1
status=$?
set -e
[[ "$status" -ne 0 ]] || fail "token argument was accepted"
[[ "$(docker_calls)" -eq 0 ]] || fail "dry inject called docker"

reset_io
install_mailbox email1 ya29-inject-access "2026-09-28T12:10:00Z"
export EMAILS_ASSISTANT_ACCOUNTS="email1"
cmd_inject "box-name" >/tmp/ea-host-out.$$
[[ "$(docker_calls)" -eq 1 ]] || fail "inject did not exec"
[[ "$(cat "$IO_DIR/docker_args.0")" == *"exec -i -u vscode box-name"* ]] || fail "inject args: $(cat "$IO_DIR/docker_args.0")"
[[ "$(cat "$IO_DIR/docker_args.0")" == *"write_access_token_file"* ]] || fail "inject does not use the 0600 writer"
[[ "$(cat "$IO_DIR/docker_args.0")" != *'ya29-inject-access'* ]] || fail "access token was a docker argument"
assert_access_only "$(cat "$IO_DIR/docker_stdin.0")"
[[ "$(cat "$IO_DIR/docker_stdin.0")" == *'ya29-inject-access'* ]] || fail "inject stdin missing token"
rm -f /tmp/ea-host-out.$$ "$container_copy"

legacy="$ROOT/.creds"
mkdir -p "$legacy"
printf '%s' "$SECRET_SENTINEL" >"$legacy/client.json"
printf '%s' "$REFRESH_SENTINEL" >"$legacy/token-email1.json"
clear_out="$(clear_legacy_creds 2>&1)"
[[ ! -e "$legacy/client.json" ]] || fail "client.json remains"
[[ ! -e "$legacy/token-email1.json" ]] || fail "token file remains"
assert_no_secret_output "$clear_out"

mkdir -p "$legacy/token-email2.json/keep"
printf '%s' "$SECRET_SENTINEL" >"$legacy/token-email2.json/keep/hidden"
set +e
clear_err="$(clear_legacy_creds 2>&1)"
status=$?
set -e
[[ "$status" -ne 0 ]] || fail "remaining credential file exited 0"
assert_no_secret_output "$clear_err"
rm -rf "$legacy"

reset_io
install_mailbox email1 ya29-login-old "2026-09-28T12:10:00Z"
export EMAILS_ASSISTANT_ACCOUNTS="email1"
login_json="$(token_json ya29-login-new "2026-09-28T13:00:00Z")"
DOCKER_STDOUT="$login_json"
DOCKER_STDERR="https://accounts.google.com/o/oauth2/auth?test=1"
stdout="$(cmd_login box-name email1 2>/tmp/ea-login-err.$$)"
err="$(cat /tmp/ea-login-err.$$)"
rm -f /tmp/ea-login-err.$$
[[ -z "$stdout" ]] || fail "login echoed the mailbox token"
[[ "$err" == *"https://accounts.google.com/o/oauth2/auth?test=1"* ]] || fail "auth URL missing on stderr"
assert_no_secret_output "$err"
[[ "$(cat "$IO_DIR/docker_stdin.0")" == *"$SECRET_SENTINEL"* ]] || fail "client secret was not on docker stdin"
[[ "$(cat "$IO_DIR/docker_args.0")" != *"$SECRET_SENTINEL"* ]] || fail "client secret was a docker argument"
[[ "$(sec_get token/email1)" == "$login_json" ]] || fail "login stdout was not stored unchanged"
repo_has_sentinel && fail "login left a secret file in the repo"

echo "ok"
