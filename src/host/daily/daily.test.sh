#!/usr/bin/env bash
# Host daily agent with stubbed clock, one-shot, docker, and osascript.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SCRIPT="$ROOT/src/host/daily/daily.sh"
PLIST="$ROOT/src/host/com.emails-assistant.daily.plist"
BIN="$(mktemp -d)"
IO_DIR=""
DAY_DIR=""

TOKEN_1="ya29-example-access"
TOKEN_2="ya29-email2"
SUBJECT="secret-subject"
FAILURE="Daily digest did not run."

fail() { echo "FAIL: $*" >&2; exit 1; }

cat >"$BIN/date-stub" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cat "${EMAILS_ASSISTANT_STUB_DIR:?}/now"
EOF

cat >"$BIN/sleep-stub" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
dir="${EMAILS_ASSISTANT_STUB_DIR:?}"
printf '%s\n' "$1" >>"$dir/sleeps"
if [[ -x "$dir/after_sleep" ]]; then
  "$dir/after_sleep"
fi
EOF

cat >"$BIN/osascript-stub" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
dir="${EMAILS_ASSISTANT_STUB_DIR:?}"
printf '%s\n' "$1" >>"$dir/banners"
printf '%s\n' "$*" >>"$dir/banner_args"
EOF

cat >"$BIN/oneshot-stub" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
dir="${EMAILS_ASSISTANT_STUB_DIR:?}"
echo shot >>"$dir/shots"
if [[ -f "$dir/shot_fail" ]]; then
  if [[ -f "$dir/shot_stderr" ]]; then
    cat "$dir/shot_stderr" >&2
  fi
  if [[ -f "$dir/shot_fail_stdout" ]]; then
    cat "$dir/shot_fail_stdout"
  fi
  exit 1
fi
cat "$dir/shot_stdout"
EOF

cat >"$BIN/docker-stub" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
dir="${EMAILS_ASSISTANT_STUB_DIR:?}"
printf '%s\n' "$1" >>"$dir/docker_cmds"
if [[ "$1" == "info" ]]; then
  if [[ -f "$dir/docker_down" ]]; then
    exit 1
  fi
  exit 0
fi
if [[ "$1" == "image" ]]; then
  if [[ -f "$dir/image_ready" ]]; then
    exit 0
  fi
  exit 1
fi
if [[ "$1" == "build" ]]; then
  exit 0
fi
if [[ "$1" == "exec" ]]; then
  exit 1
fi
printf '%s\n' "$*" >>"$dir/docker_args"
cat >"$dir/docker_stdin"
if [[ -f "$dir/docker_down" ]]; then
  exit 1
fi
if [[ -f "$dir/write_path" && -f "$dir/write_body" ]]; then
  cp "$dir/write_body" "$(cat "$dir/write_path")"
fi
if [[ -f "$dir/docker_stdout" ]]; then
  cat "$dir/docker_stdout"
fi
if [[ -f "$dir/docker_exit" ]]; then
  exit "$(cat "$dir/docker_exit")"
fi
EOF

chmod +x "$BIN/date-stub" "$BIN/sleep-stub" "$BIN/osascript-stub" "$BIN/oneshot-stub" "$BIN/docker-stub"

reset_io() {
  IO_DIR="$(mktemp -d)"
  DAY_DIR="$(mktemp -d)"
  : >"$IO_DIR/shots"
  : >"$IO_DIR/banners"
  : >"$IO_DIR/banner_args"
  : >"$IO_DIR/docker_cmds"
  : >"$IO_DIR/docker_args"
  : >"$IO_DIR/sleeps"
  printf '%s\n' "$1" >"$IO_DIR/now"
}

payloads() {
  printf '%s\n%s' \
    "{\"access_token\":\"${TOKEN_1}\",\"expiry\":\"2026-09-29T12:00:00Z\"}" \
    "{\"access_token\":\"${TOKEN_2}\",\"expiry\":\"2026-09-29T12:00:00Z\"}"
}

arm_success() {
  payloads >"$IO_DIR/shot_stdout"
  rm -f "$IO_DIR/shot_fail" "$IO_DIR/docker_down" "$IO_DIR/docker_exit"
  printf '%s\n' "from-container" >"$IO_DIR/write_body"
  printf '%s' "$DAY_DIR/2026-09-29.txt" >"$IO_DIR/write_path"
  printf '%s\n' "5" >"$IO_DIR/docker_stdout"
}

run_agent() {
  EMAILS_ASSISTANT_DATE="$BIN/date-stub" \
  EMAILS_ASSISTANT_SLEEP="$BIN/sleep-stub" \
  EMAILS_ASSISTANT_OSASCRIPT="$BIN/osascript-stub" \
  EMAILS_ASSISTANT_ONE_SHOT="$BIN/oneshot-stub" \
  EMAILS_ASSISTANT_DOCKER="$BIN/docker-stub" \
  EMAILS_ASSISTANT_STUB_DIR="$IO_DIR" \
  EMAILS_ASSISTANT_DAILY_DIR="$DAY_DIR" \
  EMAILS_ASSISTANT_IMAGE_STAMP="$IO_DIR/stamp" \
  EMAILS_ASSISTANT_ACCOUNTS=email1,email2 \
  "$SCRIPT"
}

[[ -f "$SCRIPT" ]] || fail "missing $SCRIPT"
[[ -f "$PLIST" ]] || fail "missing $PLIST"
grep -n 'docker exec' "$SCRIPT" >/dev/null && fail "script docker execs the dev container"
grep -n 'display notification' "$SCRIPT" >/dev/null || fail "missing display notification"
if grep -n -E 'osascript .*open |display notification.*open' "$SCRIPT" >/dev/null; then
  fail "notification opens a file"
fi

grep -n '<key>Hour</key>' -A1 "$PLIST" | grep -q '<integer>8</integer>' || fail "plist hour"
grep -n '<key>Minute</key>' -A1 "$PLIST" | grep -q '<integer>0</integer>' || fail "plist minute"
grep -n '<key>RunAtLoad</key>' -A1 "$PLIST" | grep -q '<true/>' || fail "plist RunAtLoad"
grep -n 'WakeSystem\|StartInterval' "$PLIST" >/dev/null && fail "plist wakes the Mac"

# 07:40, no file: no one-shot, no banner, no file.
reset_io "2026-09-29 07:40:00"
arm_success
run_agent
[[ ! -s "$IO_DIR/shots" ]] || fail "one-shot ran before 08:00"
[[ ! -s "$IO_DIR/banners" ]] || fail "banner before 08:00"
[[ ! -e "$DAY_DIR/2026-09-29.txt" ]] || fail "file written before 08:00"

# After 08:00, one run writes the file and shows only the count.
reset_io "2026-09-29 10:30:00"
arm_success
run_agent
[[ "$(grep -c shot "$IO_DIR/shots")" -eq 1 ]] || fail "expected one one-shot"
[[ "$(grep -c '^build$' "$IO_DIR/docker_cmds")" -eq 1 ]] || fail "missing image build"
[[ "$(cat "$IO_DIR/banners")" == "5" ]] || fail "count banner: $(cat "$IO_DIR/banners")"
[[ "$(cat "$DAY_DIR/2026-09-29.txt")" == "from-container" ]] || fail "host replaced the day file"
[[ "$(cat "$IO_DIR/docker_stdin")" == *"access_token"* ]] || fail "token was not piped to docker"
[[ "$(cat "$IO_DIR/docker_args")" != *"$TOKEN_1"* && "$(cat "$IO_DIR/docker_args")" != *"$TOKEN_2"* ]] || fail "token was a docker argument"
[[ "$(cat "$IO_DIR/banner_args")" != *"$TOKEN_1"* && "$(cat "$IO_DIR/banners")" != *"$SUBJECT"* ]] || fail "banner leaked"
grep -q 'exec' "$IO_DIR/docker_cmds" && fail "docker exec was used"
[[ "$(cat "$IO_DIR/docker_cmds")" != *'exec'* ]] || fail "docker exec was used"

# Same day again: file stays, no second banner.
printf '%s' "keep" >"$DAY_DIR/2026-09-29.txt"
: >"$IO_DIR/shots"
: >"$IO_DIR/banners"
: >"$IO_DIR/docker_cmds"
run_agent
[[ "$(cat "$DAY_DIR/2026-09-29.txt")" == "keep" ]] || fail "second run replaced the file"
[[ ! -s "$IO_DIR/banners" ]] || fail "second banner"
[[ ! -s "$IO_DIR/shots" ]] || fail "second one-shot"

# Image already matches pyproject.toml and uv.lock: do not build again.
reset_io "2026-09-29 10:30:00"
arm_success
: >"$IO_DIR/image_ready"
if command -v shasum >/dev/null 2>&1; then
  cat "$ROOT/pyproject.toml" "$ROOT/uv.lock" | shasum -a 256 | awk '{print $1}' >"$IO_DIR/stamp"
else
  cat "$ROOT/pyproject.toml" "$ROOT/uv.lock" | sha256sum | awk '{print $1}' >"$IO_DIR/stamp"
fi
run_agent
[[ "$(grep -c '^build$' "$IO_DIR/docker_cmds")" -eq 0 ]] || fail "rebuilt a current image"
[[ "$(cat "$IO_DIR/banners")" == "5" ]] || fail "current image did not run"

# Docker is down at 08:00, then up 15 minutes later.
reset_io "2026-09-29 08:00:00"
: >"$IO_DIR/docker_down"
printf '%s\n' "$SUBJECT from someone" >"$IO_DIR/shot_stderr"
cat >"$IO_DIR/after_sleep" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
dir="${EMAILS_ASSISTANT_STUB_DIR:?}"
rm -f "$dir/docker_down"
printf '%s\n' "2026-09-29 08:15:00" >"$dir/now"
printf '%s\n%s' \
  '{"access_token":"ya29-example-access","expiry":"2026-09-29T12:00:00Z"}' \
  '{"access_token":"ya29-email2","expiry":"2026-09-29T12:00:00Z"}' >"$dir/shot_stdout"
printf '%s\n' "from-container" >"$dir/write_body"
printf '%s\n' "4" >"$dir/docker_stdout"
EOF
# write_path is the day file; arm it without clearing docker_down.
printf '%s' "$DAY_DIR/2026-09-29.txt" >"$IO_DIR/write_path"
chmod +x "$IO_DIR/after_sleep"
run_agent
[[ "$(grep -c shot "$IO_DIR/shots")" -eq 1 ]] || fail "one-shot ran while docker was down"
[[ "$(sed -n '1p' "$IO_DIR/banners")" == "$FAILURE" ]] || fail "failure banner"
[[ "$(sed -n '2p' "$IO_DIR/banners")" == "4" ]] || fail "later count banner"
[[ "$(grep -c "$FAILURE" "$IO_DIR/banners")" -eq 1 ]] || fail "second failure banner"
[[ "$(cat "$IO_DIR/banners")" != *"$SUBJECT"* && "$(cat "$IO_DIR/banners")" != *"someone"* ]] || fail "failure banner has mail"
[[ "$(cat "$DAY_DIR/2026-09-29.txt")" == "from-container" ]] || fail "later try did not write the file"
[[ "$(cat "$IO_DIR/sleeps")" == "900" ]] || fail "did not wait 15 minutes"

# one-shot re-login: no container, no file, banner hides the token. A later try still writes.
reset_io "2026-09-29 10:30:00"
: >"$IO_DIR/shot_fail"
printf '%s\n' "Login is required for email2. The refresh token was rejected. ${SUBJECT}" >"$IO_DIR/shot_stderr"
printf '%s\n' "$TOKEN_1" >"$IO_DIR/shot_fail_stdout"
cat >"$IO_DIR/after_sleep" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
dir="${EMAILS_ASSISTANT_STUB_DIR:?}"
rm -f "$dir/shot_fail"
printf '%s\n' "2026-09-29 10:45:00" >"$dir/now"
printf '%s\n%s' \
  '{"access_token":"ya29-example-access","expiry":"2026-09-29T12:00:00Z"}' \
  '{"access_token":"ya29-email2","expiry":"2026-09-29T12:00:00Z"}' >"$dir/shot_stdout"
printf '%s\n' "from-container" >"$dir/write_body"
printf '%s\n' "2" >"$dir/docker_stdout"
EOF
printf '%s' "$DAY_DIR/2026-09-29.txt" >"$IO_DIR/write_path"
chmod +x "$IO_DIR/after_sleep"
run_agent
[[ "$(grep -c '^run$' "$IO_DIR/docker_cmds")" -eq 1 ]] || fail "container started on the failed one-shot"
[[ ! -e "$DAY_DIR/2026-09-29.txt" || "$(cat "$DAY_DIR/2026-09-29.txt")" == "from-container" ]] || fail "file written on the failed one-shot"
[[ "$(sed -n '1p' "$IO_DIR/banners")" == "$FAILURE" ]] || fail "re-login banner"
[[ "$(cat "$IO_DIR/banners")" != *"$TOKEN_1"* && "$(cat "$IO_DIR/banners")" != *"$SUBJECT"* ]] || fail "re-login banner leaked"
[[ "$(sed -n '2p' "$IO_DIR/banners")" == "2" ]] || fail "later try after re-login"
[[ "$(cat "$DAY_DIR/2026-09-29.txt")" == "from-container" ]] || fail "later try wrote nothing"
[[ "$(grep -c "$FAILURE" "$IO_DIR/banners")" -eq 1 ]] || fail "second failure banner after re-login"

# No override: the day file is digests/ on the repo mount, not Application Support.
reset_io "2026-09-29 10:30:00"
arm_success
rm -f "$ROOT/digests/2026-09-29.txt"
printf '%s' "$ROOT/digests/2026-09-29.txt" >"$IO_DIR/write_path"
EMAILS_ASSISTANT_DATE="$BIN/date-stub" \
EMAILS_ASSISTANT_SLEEP="$BIN/sleep-stub" \
EMAILS_ASSISTANT_OSASCRIPT="$BIN/osascript-stub" \
EMAILS_ASSISTANT_ONE_SHOT="$BIN/oneshot-stub" \
EMAILS_ASSISTANT_DOCKER="$BIN/docker-stub" \
EMAILS_ASSISTANT_STUB_DIR="$IO_DIR" \
EMAILS_ASSISTANT_DAILY_DIR= \
EMAILS_ASSISTANT_IMAGE_STAMP="$IO_DIR/stamp" \
EMAILS_ASSISTANT_ACCOUNTS=email1,email2 \
"$SCRIPT"
[[ "$(cat "$IO_DIR/docker_args")" == *"EMAILS_ASSISTANT_DAILY_DIR=/workspaces/emails-assistant/digests"* ]] || fail "container day dir: $(cat "$IO_DIR/docker_args")"
[[ "$(cat "$IO_DIR/docker_args")" == *"$ROOT/src/emails_assistant:/workspaces/emails-assistant/src/emails_assistant:ro"* ]] || fail "mail package was not mounted read-only"
[[ "$(cat "$IO_DIR/docker_args")" == *"$ROOT/src/shared.py:/workspaces/emails-assistant/src/shared.py:ro"* ]] || fail "shared.py was not mounted read-only"
[[ "$(cat "$IO_DIR/docker_args")" == *"$ROOT/digests:/workspaces/emails-assistant/digests"* ]] || fail "digests/ was not mounted"
[[ "$(cat "$IO_DIR/docker_args")" != *"$ROOT/digests:/workspaces/emails-assistant/digests:ro"* ]] || fail "digests/ was mounted read-only"
[[ "$(cat "$IO_DIR/docker_args")" != *"$ROOT:/workspaces/emails-assistant "* ]] || fail "the whole repo was mounted"
[[ "$(cat "$IO_DIR/docker_args")" != *"$ROOT/.env"* ]] || fail ".env was mounted"
[[ "$(cat "$IO_DIR/docker_args")" != *"$ROOT/src/login:"* ]] || fail "login package was mounted"
if [[ -d "$ROOT/keys" ]]; then
  [[ "$(cat "$IO_DIR/docker_args")" == *"$ROOT/keys:/workspaces/emails-assistant/keys:ro"* ]] || fail "keys/ was not mounted read-only"
else
  [[ "$(cat "$IO_DIR/docker_args")" != *"$ROOT/keys:"* ]] || fail "missing keys/ was mounted"
fi
[[ "$(cat "$IO_DIR/docker_args")" != *"Application Support"* ]] || fail "day file still uses Application Support"
[[ "$(cat "$IO_DIR/docker_args")" != *":/daily"* ]] || fail "default run still mounts /daily"
[[ "$(cat "$ROOT/digests/2026-09-29.txt")" == "from-container" ]] || fail "default run did not write digests/"
rm -f "$ROOT/digests/2026-09-29.txt"

# Summary miss: one banner, a non-txt marker, the prior day file stays.
reset_io "2026-09-29 10:30:00"
payloads >"$IO_DIR/shot_stdout"
printf '%s\n' "Summary did not run." >"$IO_DIR/docker_stdout"
printf '1\n' >"$IO_DIR/docker_exit"
printf '%s\n' "prior-day" >"$DAY_DIR/2026-09-28.txt"
run_agent
[[ ! -e "$DAY_DIR/2026-09-29.txt" ]] || fail "summary miss wrote a day file"
[[ -f "$DAY_DIR/2026-09-29.summary-miss" ]] || fail "missing summary miss marker"
[[ "$(find "$DAY_DIR" -name '*.txt' -print | wc -l | tr -d ' ')" -eq 1 ]] || fail "miss added a txt"
[[ "$(cat "$DAY_DIR/2026-09-28.txt")" == "prior-day" ]] || fail "miss changed the prior day file"
[[ "$(cat "$IO_DIR/banners")" == "Summary did not run." ]] || fail "summary banner: $(cat "$IO_DIR/banners")"
[[ "$(cat "$IO_DIR/banners")" != *"$SUBJECT"* ]] || fail "summary banner leaked"
[[ ! -s "$IO_DIR/sleeps" ]] || fail "summary miss retried"
[[ "$(grep -c shot "$IO_DIR/shots")" -eq 1 ]] || fail "summary miss one-shot count"

# Same local day: no second Gemini call and no second banner.
: >"$IO_DIR/shots"
: >"$IO_DIR/banners"
: >"$IO_DIR/docker_cmds"
: >"$IO_DIR/sleeps"
run_agent
[[ ! -s "$IO_DIR/shots" ]] || fail "second process called one-shot"
[[ ! -s "$IO_DIR/docker_cmds" ]] || fail "second process called docker"
[[ ! -s "$IO_DIR/banners" ]] || fail "second summary banner"
[[ "$(cat "$DAY_DIR/2026-09-28.txt")" == "prior-day" ]] || fail "second process changed the prior day file"

# The next local day ignores yesterday's marker.
printf '%s\n' "2026-09-30 10:30:00" >"$IO_DIR/now"
arm_success
printf '%s' "$DAY_DIR/2026-09-30.txt" >"$IO_DIR/write_path"
: >"$IO_DIR/shots"
: >"$IO_DIR/banners"
: >"$IO_DIR/docker_cmds"
run_agent
[[ "$(grep -c shot "$IO_DIR/shots")" -eq 1 ]] || fail "next day did not run"
[[ "$(cat "$IO_DIR/banners")" == "5" ]] || fail "next day banner: $(cat "$IO_DIR/banners")"
[[ -f "$DAY_DIR/2026-09-29.summary-miss" ]] || fail "next day removed yesterday's marker"
[[ "$(cat "$DAY_DIR/2026-09-30.txt")" == "from-container" ]] || fail "next day wrote nothing"

# A digest failure still retries and does not leave a summary marker.
reset_io "2026-09-29 10:30:00"
payloads >"$IO_DIR/shot_stdout"
printf '%s\n' "Daily digest did not run." >"$IO_DIR/docker_stdout"
printf '1\n' >"$IO_DIR/docker_exit"
cat >"$IO_DIR/after_sleep" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
dir="${EMAILS_ASSISTANT_STUB_DIR:?}"
rm -f "$dir/docker_exit"
printf '%s\n' "2026-09-29 10:45:00" >"$dir/now"
printf '%s\n%s' \
  '{"access_token":"ya29-example-access","expiry":"2026-09-29T12:00:00Z"}' \
  '{"access_token":"ya29-email2","expiry":"2026-09-29T12:00:00Z"}' >"$dir/shot_stdout"
printf '%s\n' "from-container" >"$dir/write_body"
printf '%s\n' "3" >"$dir/docker_stdout"
EOF
printf '%s' "$DAY_DIR/2026-09-29.txt" >"$IO_DIR/write_path"
chmod +x "$IO_DIR/after_sleep"
run_agent
[[ ! -e "$DAY_DIR/2026-09-29.summary-miss" ]] || fail "digest failure wrote a summary marker"
[[ "$(sed -n '1p' "$IO_DIR/banners")" == "$FAILURE" ]] || fail "digest failure banner"
[[ "$(grep -c "$FAILURE" "$IO_DIR/banners")" -eq 1 ]] || fail "second digest failure banner"
[[ "$(sed -n '2p' "$IO_DIR/banners")" == "3" ]] || fail "later count after digest failure"
[[ "$(cat "$IO_DIR/sleeps")" == "900" ]] || fail "digest failure did not wait 15 minutes"

echo "ok"
