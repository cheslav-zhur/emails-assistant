#!/usr/bin/env bash
# Runs the host script as its own process. Stubs are executables, not shell functions.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT/scripts/macos-access-token.sh"
BIN="$(mktemp -d)"

REFRESH_SENTINEL='1//fixture+refresh='
SECRET_SENTINEL='fixture/client+secret='
NOW="2026-09-28T12:00:00Z"
IO_DIR=""

fail() { echo "FAIL: $*" >&2; exit 1; }

cat >"$BIN/security-stub" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
dir="${EMAILS_ASSISTANT_STUB_DIR:?}"
cmd="$1"
shift
account=""
password=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -a) account="$2"; shift 2 ;;
    -w)
      if [[ "$cmd" == "add-generic-password" ]]; then
        password="$2"
        shift 2
      else
        shift
      fi
      ;;
    *) shift ;;
  esac
done
safe="$(printf '%s' "$account" | tr '/' '_')"
if [[ "$cmd" == "find-generic-password" ]]; then
  cat "$dir/sec_$safe"
elif [[ "$cmd" == "add-generic-password" ]]; then
  printf '%s' "$password" >"$dir/sec_$safe"
  printf '%s\n' "$account" >>"$dir/sec_writes"
else
  exit 1
fi
EOF

cat >"$BIN/curl-stub" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
dir="${EMAILS_ASSISTANT_STUB_DIR:?}"
n="$(cat "$dir/curl_n")"
printf '%s\n' "$*" >"$dir/curl_args.$n"
cat >"$dir/curl_stdin.$n"
echo $((n + 1)) >"$dir/curl_n"
if [[ -f "$dir/resp.$n" ]]; then
  cat "$dir/resp.$n"
fi
EOF

cat >"$BIN/docker-stub" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
dir="${EMAILS_ASSISTANT_STUB_DIR:?}"
n="$(cat "$dir/docker_n")"
printf '%s\n' "$*" >"$dir/docker_args.$n"
cat >"$dir/docker_stdin.$n"
echo $((n + 1)) >"$dir/docker_n"
if [[ -f "$dir/docker_stderr" ]]; then
  cat "$dir/docker_stderr" >&2
fi
if [[ -f "$dir/docker_stdout" ]]; then
  cat "$dir/docker_stdout"
fi
args=("$@")
code=""
rest=()
for i in "${!args[@]}"; do
  if [[ "${args[$i]}" == "python3" && "${args[$((i + 1))]:-}" == "-c" ]]; then
    code="${args[$((i + 2))]}"
    rest=("${args[@]:$((i + 3))}")
    break
  fi
done
if [[ -n "$code" ]]; then
  src="${EMAILS_ASSISTANT_SRC:?}"
  if ((${#rest[@]})); then
    PYTHONPATH="$src" python3 -c "$code" "${rest[@]}" <"$dir/docker_stdin.$n"
  else
    PYTHONPATH="$src" python3 -c "$code" <"$dir/docker_stdin.$n"
  fi
fi
EOF
chmod +x "$BIN/security-stub" "$BIN/curl-stub" "$BIN/docker-stub"

reset_io() {
  IO_DIR="$(mktemp -d)"
  echo 0 >"$IO_DIR/curl_n"
  echo 0 >"$IO_DIR/docker_n"
  echo 0 >"$IO_DIR/queue_n"
  : >"$IO_DIR/sec_writes"
  rm -f "$IO_DIR/docker_stdout" "$IO_DIR/docker_stderr"
  export EMAILS_ASSISTANT_ACCOUNTS="${1:-email1,email2}"
}

queue_curl() {
  local n
  n="$(cat "$IO_DIR/queue_n")"
  printf '%s' "$1" >"$IO_DIR/resp.$n"
  echo $((n + 1)) >"$IO_DIR/queue_n"
}

client_json() {
  SECRET_SENTINEL="$SECRET_SENTINEL" python3 -c 'import json, os, sys; json.dump({"installed": {"client_id": "client-id", "client_secret": os.environ["SECRET_SENTINEL"], "token_uri": "https://oauth2.googleapis.com/token"}}, sys.stdout, separators=(",", ":"))'
}

token_json() {
  local token="$1" expiry="$2"
  TOKEN="$token" EXPIRY="$expiry" REFRESH_SENTINEL="$REFRESH_SENTINEL" SECRET_SENTINEL="$SECRET_SENTINEL" python3 -c 'import json, os, sys; json.dump({"token": os.environ["TOKEN"], "refresh_token": os.environ["REFRESH_SENTINEL"], "token_uri": "https://oauth2.googleapis.com/token", "client_id": "client-id", "client_secret": os.environ["SECRET_SENTINEL"], "expiry": os.environ["EXPIRY"]}, sys.stdout, separators=(",", ":"))'
}

install_mailbox() {
  local alias="$1" token="$2" expiry="$3"
  local safe
  safe="$(printf '%s' "token/${alias}" | tr '/' '_')"
  token_json "$token" "$expiry" >"$IO_DIR/sec_$safe"
  client_json >"$IO_DIR/sec_oauth-client"
}

run() {
  EMAILS_ASSISTANT_SECURITY="$BIN/security-stub" \
  EMAILS_ASSISTANT_CURL="$BIN/curl-stub" \
  EMAILS_ASSISTANT_DOCKER="$BIN/docker-stub" \
  EMAILS_ASSISTANT_STUB_DIR="$IO_DIR" \
  EMAILS_ASSISTANT_NOW="$NOW" \
  EMAILS_ASSISTANT_ACCOUNTS="$EMAILS_ASSISTANT_ACCOUNTS" \
  EMAILS_ASSISTANT_KEYCHAIN_SERVICE=emails-assistant \
  EMAILS_ASSISTANT_SRC="$ROOT/src" \
  "$SCRIPT" "$@"
}

assert_no_secret_output() {
  local blob="$1"
  [[ "$blob" != *"$REFRESH_SENTINEL"* ]] || fail "refresh token leaked"
  [[ "$blob" != *"$SECRET_SENTINEL"* ]] || fail "client secret leaked"
}

assert_access_only() {
  python3 -c '
import json, sys
obj = json.loads(sys.argv[1])
if set(obj) != {"access_token", "expiry"}:
    raise SystemExit("payload keys")
' "$1"
}

sec_get() {
  local safe
  safe="$(printf '%s' "$1" | tr '/' '_')"
  cat "$IO_DIR/sec_$safe"
}

if grep -n '\.creds/' "$SCRIPT" >/dev/null; then
  fail "script contains a .creds/ path"
fi
[[ ! -f "$ROOT/scripts/macos-keychain-bridge.sh" ]] || fail "old bridge script still exists"

reset_io
install_mailbox email1 ya29-still-good "2026-09-28T12:10:00Z"
install_mailbox email2 ya29-still-good-2 "2026-09-28T12:10:00Z"
stdout="$(run one-shot)"
[[ "$(cat "$IO_DIR/curl_n")" -eq 0 ]] || fail "fresh token was refreshed"
[[ "$(cat "$IO_DIR/docker_n")" -eq 0 ]] || fail "one-shot called docker"
mapfile -t lines <<<"$stdout"
[[ "${#lines[@]}" -eq 2 ]] || fail "expected two payloads"
assert_access_only "${lines[0]}"
assert_access_only "${lines[1]}"
[[ "${lines[0]}" == *'ya29-still-good'* && "${lines[1]}" == *'ya29-still-good-2'* ]] || fail "payload aliases"
assert_no_secret_output "$stdout"

reset_io
install_mailbox email1 ya29-old-access "2026-09-28T12:02:00Z"
install_mailbox email2 ya29-old-access-2 "2026-09-28T12:02:00Z"
queue_curl '{"access_token":"ya29-new-access","expires_in":3600,"token_type":"Bearer"}'
queue_curl '{"access_token":"ya29-new-access-2","expires_in":3600,"token_type":"Bearer"}'
TZ=Asia/Ho_Chi_Minh stdout="$(run one-shot)"
unset TZ
[[ "$(cat "$IO_DIR/curl_n")" -eq 2 ]] || fail "due tokens were not both refreshed"
stdin0="$(cat "$IO_DIR/curl_stdin.0")"
[[ "$stdin0" == *'1%2F%2Ffixture%2Brefresh%3D'* ]] || fail "refresh token was not form-encoded"
[[ "$stdin0" != *"$REFRESH_SENTINEL"* && "$stdin0" != *"$SECRET_SENTINEL"* ]] || fail "raw secret on curl stdin"
args0="$(cat "$IO_DIR/curl_args.0")"
[[ "$args0" != *"$REFRESH_SENTINEL"* && "$args0" != *"$SECRET_SENTINEL"* ]] || fail "secret was a curl argument"
python3 -c '
import json, sys
obj = json.loads(sys.argv[1])
assert obj["token"] == "ya29-new-access", obj["token"]
assert obj["expiry"] == "2026-09-28T13:00:00Z", obj["expiry"]
assert obj["refresh_token"] == sys.argv[2]
assert obj["client_secret"] == sys.argv[3]
assert obj["client_id"] == "client-id"
assert obj["token_uri"] == "https://oauth2.googleapis.com/token"
' "$(sec_get token/email1)" "$REFRESH_SENTINEL" "$SECRET_SENTINEL"
mapfile -t lines <<<"$stdout"
assert_access_only "${lines[0]}"
assert_access_only "${lines[1]}"
[[ "${lines[0]}" == *'ya29-new-access'* && "${lines[1]}" == *'ya29-new-access-2'* ]] || fail "new tokens were not passed on"
assert_no_secret_output "$stdout"

reset_io
install_mailbox email1 ya29-email1-old "2026-09-28T12:02:00Z"
install_mailbox email2 ya29-email2-old "2026-09-28T12:02:00Z"
queue_curl '{"access_token":"ya29-email1-new","expires_in":3600,"token_type":"Bearer"}'
queue_curl '{"error":"invalid_grant","error_description":"ya29-should-not-leak"}'
set +e
stdout="$(run one-shot 2>"$IO_DIR/err")"
status=$?
set -e
err="$(cat "$IO_DIR/err")"
[[ "$status" -ne 0 ]] || fail "invalid_grant exited 0"
[[ "$stdout" != *'ya29-'* ]] || fail "one-shot stdout was a token"
[[ "$err" == *"Login is required for email2. The refresh token was rejected."* ]] || fail "missing re-login notice"
[[ "$err" != *'ya29-should-not-leak'* ]] || fail "error body leaked"
assert_no_secret_output "${stdout}${err}"
[[ "$(sec_get token/email1)" == *'ya29-email1-old'* ]] || fail "email1 token was replaced"
[[ "$(wc -l <"$IO_DIR/sec_writes" | tr -d ' ')" -eq 0 ]] || fail "keychain write on failed refresh"

reset_io email1
install_mailbox email1 ya29-old-access "2026-09-28T12:02:00Z"
queue_curl '{"access_token":"ya29-new-access","expires_in":3600,"refresh_token":"new-refresh-should-not-store"}'
set +e
run one-shot >"$IO_DIR/out" 2>"$IO_DIR/err"
status=$?
set -e
[[ "$status" -ne 0 ]] || fail "unexpected refresh_token was accepted"
[[ "$(wc -l <"$IO_DIR/sec_writes" | tr -d ' ')" -eq 0 ]] || fail "keychain write after refresh_token response"

reset_io email1
install_mailbox email1 ya29-old-access "2026-09-28T19:00:00+07:00"
queue_curl '{"access_token":"ya29-from-offset","expires_in":3600,"token_type":"Bearer"}'
TZ=Asia/Ho_Chi_Minh stdout="$(run one-shot)"
unset TZ
[[ "$(cat "$IO_DIR/curl_n")" -eq 1 ]] || fail "+07 expiry was treated as a future UTC expiry"
[[ "$stdout" == *'ya29-from-offset'* ]] || fail "offset expiry did not refresh"
stored="$(sec_get token/email1)"
[[ "$stored" == *'2026-09-28T13:00:00Z'* && "$stored" != *'+07'* ]] || fail "stored expiry was not UTC Z"

reset_io email1
install_mailbox email1 ya29-inject-access "2026-09-28T12:10:00Z"
container_copy="/dev/shm/emails-assistant/access-email1.json"
mkdir -p "$(dirname "$container_copy")"
printf '%s' 'dev-container-token-original' >"$container_copy"
stdout="$(run one-shot)"
[[ "$(cat "$container_copy")" == "dev-container-token-original" ]] || fail "one-shot wrote the dev container token"
[[ "$(cat "$IO_DIR/docker_n")" -eq 0 ]] || fail "one-shot touched docker"
assert_access_only "$stdout"
rm -f "$container_copy"

set +e
run inject "box-name" "$SECRET_SENTINEL" >/dev/null 2>&1
status=$?
set -e
[[ "$status" -ne 0 ]] || fail "token argument was accepted"
[[ "$(cat "$IO_DIR/docker_n")" -eq 0 ]] || fail "dry inject called docker"

reset_io email1
install_mailbox email1 ya29-inject-access "2026-09-28T12:10:00Z"
run inject "box-name" >/dev/null
[[ "$(cat "$IO_DIR/docker_n")" -eq 1 ]] || fail "inject did not exec"
args="$(cat "$IO_DIR/docker_args.0")"
[[ "$args" == *"exec -i -u vscode box-name"* ]] || fail "inject args"
[[ "$args" == *"write_access_token_file(sys.argv[1], sys.stdin.read())"* ]] || fail "inject does not use the 0600 writer"
[[ "$args" != *'ya29-inject-access'* ]] || fail "access token was a docker argument"
stdin="$(cat "$IO_DIR/docker_stdin.0")"
assert_access_only "$stdin"
[[ "$stdin" == *'ya29-inject-access'* ]] || fail "inject stdin missing token"
access_file="/dev/shm/emails-assistant/access-email1.json"
[[ -f "$access_file" ]] || fail "inject did not write the access file"
mode="$(stat -c '%a' "$access_file")"
[[ "$mode" == "600" ]] || fail "inject access file mode is $mode"
grep -q 'ya29-inject-access' "$access_file" || fail "inject file missing token"
rm -f "$access_file"

legacy="$ROOT/.creds"
if [[ -e "$legacy" ]]; then
  fail "repo .creds already exists"
fi
cleanup_legacy() {
  rm -f "$ROOT/.creds/client.json" "$ROOT/.creds/token-email1.json"
  rm -rf "$ROOT/.creds/token-email2.json"
  rmdir "$ROOT/.creds" 2>/dev/null || true
}
trap cleanup_legacy EXIT
mkdir -p "$legacy"
printf '%s' "$SECRET_SENTINEL" >"$legacy/client.json"
printf '%s' "$REFRESH_SENTINEL" >"$legacy/token-email1.json"
reset_io email1
install_mailbox email1 ya29-still-good "2026-09-28T12:10:00Z"
clear_out="$(run one-shot 2>&1)"
[[ ! -e "$legacy/client.json" && ! -e "$legacy/token-email1.json" ]] || fail "legacy credential files remain"
assert_no_secret_output "$clear_out"

mkdir -p "$legacy/token-email2.json/keep"
printf '%s' "$SECRET_SENTINEL" >"$legacy/token-email2.json/keep/hidden"
set +e
clear_err="$(run one-shot 2>&1)"
status=$?
set -e
[[ "$status" -ne 0 ]] || fail "remaining credential file exited 0"
assert_no_secret_output "$clear_err"
cleanup_legacy
trap - EXIT
[[ ! -e "$legacy" ]] || fail "legacy cleanup left .creds"

reset_io email1
install_mailbox email1 ya29-login-old "2026-09-28T12:10:00Z"
login_json="$(token_json ya29-login-new "2026-09-28T13:00:00Z")"
printf '%s' "$login_json" >"$IO_DIR/docker_stdout"
printf '%s' "https://accounts.google.com/o/oauth2/auth?test=1" >"$IO_DIR/docker_stderr"
stdout="$(run login box-name email1 2>"$IO_DIR/err")"
err="$(cat "$IO_DIR/err")"
[[ -z "$stdout" ]] || fail "login echoed the mailbox token"
[[ "$err" == *"https://accounts.google.com/o/oauth2/auth?test=1"* ]] || fail "auth URL missing on stderr"
assert_no_secret_output "$err"
[[ "$(cat "$IO_DIR/docker_stdin.0")" == *"$SECRET_SENTINEL"* ]] || fail "client secret was not on docker stdin"
[[ "$(cat "$IO_DIR/docker_args.0")" != *"$SECRET_SENTINEL"* ]] || fail "client secret was a docker argument"
[[ "$(sec_get token/email1)" == "$login_json" ]] || fail "login stdout was not stored unchanged"

if grep -R -n -e "$REFRESH_SENTINEL" -e "$SECRET_SENTINEL" \
  --exclude-dir=.git --exclude=test_host_refresh.sh "$ROOT" >/dev/null
then
  fail "a secret file was left in the repo"
fi

echo "ok"
