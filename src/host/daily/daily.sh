#!/usr/bin/env bash
# Mac host: one daily digest after 08:00 local time. Tokens stay in memory.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
FAILURE="Daily digest did not run."
SUMMARY_MISS="Summary did not run."
IMAGE="${EMAILS_ASSISTANT_IMAGE:-emails-assistant:app}"
TARGET="${EMAILS_ASSISTANT_IMAGE_TARGET:-app}"
CONTAINER_ROOT="/workspaces/emails-assistant"
CONTAINER_DAILY="/daily"

export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"

daily_dir() {
  if [[ -n "${EMAILS_ASSISTANT_DAILY_DIR:-}" ]]; then
    printf '%s' "$EMAILS_ASSISTANT_DAILY_DIR"
    return
  fi
  printf '%s' "$ROOT/digests"
}

date_local() {
  if [[ -n "${EMAILS_ASSISTANT_DATE:-}" ]]; then
    "$EMAILS_ASSISTANT_DATE"
    return
  fi
  date '+%Y-%m-%d %H:%M:%S'
}

day_stamp() {
  local clock
  clock="$(date_local)"
  printf '%s' "${clock:0:10}"
}

before_eight() {
  local clock hm
  clock="$(date_local)"
  hm="${clock:11:2}${clock:14:2}"
  ((10#$hm < 800))
}

today_file() {
  printf '%s/%s.txt' "$(daily_dir)" "$(day_stamp)"
}

miss_marker() {
  printf '%s/%s.summary-miss' "$(daily_dir)" "$(day_stamp)"
}

image_stamp() {
  if [[ -n "${EMAILS_ASSISTANT_IMAGE_STAMP:-}" ]]; then
    printf '%s' "$EMAILS_ASSISTANT_IMAGE_STAMP"
    return
  fi
  printf '%s' "$HOME/Library/Application Support/emails-assistant/${TARGET}-image.sha256"
}

pyproject_hash() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$ROOT/pyproject.toml" | awk '{print $1}'
    return
  fi
  sha256sum "$ROOT/pyproject.toml" | awk '{print $1}'
}

ensure_image() {
  local stamp hash
  stamp="$(image_stamp)"
  hash="$(pyproject_hash)"
  if docker_cmd image inspect "$IMAGE" >/dev/null 2>&1 \
    && [[ -f "$stamp" ]] \
    && [[ "$(cat "$stamp")" == "$hash" ]]; then
    return 0
  fi
  docker_cmd build --target "$TARGET" -t "$IMAGE" -f "$ROOT/Dockerfile" "$ROOT"
  mkdir -p "$(dirname "$stamp")"
  printf '%s\n' "$hash" >"$stamp"
}

docker_cmd() {
  if [[ -n "${EMAILS_ASSISTANT_DOCKER:-}" ]]; then
    "$EMAILS_ASSISTANT_DOCKER" "$@"
    return
  fi
  command docker "$@"
}

one_shot() {
  if [[ -n "${EMAILS_ASSISTANT_ONE_SHOT:-}" ]]; then
    "$EMAILS_ASSISTANT_ONE_SHOT"
    return
  fi
  "$ROOT/src/host/access-token/access-token.sh" one-shot
}

host_tz() {
  local target
  if [[ -n "${EMAILS_ASSISTANT_TZ:-}" ]]; then
    printf '%s' "$EMAILS_ASSISTANT_TZ"
    return
  fi
  if [[ -L /etc/localtime ]]; then
    target="$(readlink /etc/localtime)"
    printf '%s' "${target##*zoneinfo/}"
    return
  fi
  printf '%s' "UTC"
}

sleep_15() {
  if [[ -n "${EMAILS_ASSISTANT_SLEEP:-}" ]]; then
    "$EMAILS_ASSISTANT_SLEEP" 900
    return
  fi
  sleep 900
}

notify() {
  local message="$1"
  case "$message" in
    *[!0-9A-Za-z.\ ]*) return 1 ;;
  esac
  if [[ -n "${EMAILS_ASSISTANT_OSASCRIPT:-}" ]]; then
    "$EMAILS_ASSISTANT_OSASCRIPT" "$message"
    return
  fi
  osascript -e "display notification \"$message\" with title \"emails-assistant\""
}

run_container() {
  local host_daily tz container_daily
  local args
  host_daily="$(daily_dir)"
  tz="$(host_tz)"
  mkdir -p "$host_daily"
  if [[ "$host_daily" == "$ROOT/"* ]]; then
    container_daily="$CONTAINER_ROOT${host_daily#"$ROOT"}"
  else
    container_daily="$CONTAINER_DAILY"
  fi
  args=(
    run --rm -i -u vscode
    -e "TZ=$tz"
    -e "PYTHONPATH=$CONTAINER_ROOT/src"
    -e "EMAILS_ASSISTANT_DAILY_DIR=$container_daily"
    -e "EMAILS_ASSISTANT_ACCOUNTS=${EMAILS_ASSISTANT_ACCOUNTS:-email1,email2}"
  )
  args+=(
    -v "$ROOT/src/emails_assistant:$CONTAINER_ROOT/src/emails_assistant:ro"
    -v "$ROOT/src/shared.py:$CONTAINER_ROOT/src/shared.py:ro"
    -v "$host_daily:$container_daily"
  )
  if [[ -d "$ROOT/keys" ]]; then
    args+=(-v "$ROOT/keys:$CONTAINER_ROOT/keys:ro")
  fi
  args+=(
    -v /etc/localtime:/etc/localtime:ro
    -w "$CONTAINER_ROOT"
    "$IMAGE"
    python3 -m emails_assistant.cli daily
  )
  printf '%s' "$1" | docker_cmd "${args[@]}"
}

try_once() {
  local payload result file
  if ! docker_cmd info >/dev/null 2>&1; then
    return 1
  fi
  ensure_image || return 1
  payload="$(one_shot)" || return 1
  if [[ -z "$payload" ]]; then
    return 1
  fi
  file="$(today_file)"
  local status=0
  result="$(run_container "$payload")" || status=$?
  result="${result//$'\n'/}"
  if [[ "$status" -eq 0 && -f "$file" && "$result" =~ ^[0-9]+$ ]]; then
    notify "$result"
    return 0
  fi
  if [[ "$result" == "$SUMMARY_MISS" && ! -f "$file" ]]; then
    : >"$(miss_marker)"
    notify "$SUMMARY_MISS"
    return 2
  fi
  return 1
}

main() {
  local start_day notified=0
  if before_eight; then
    return 0
  fi
  start_day="$(day_stamp)"
  while true; do
    if [[ "$(day_stamp)" != "$start_day" ]] || before_eight; then
      return 0
    fi
    if [[ -f "$(today_file)" || -f "$(miss_marker)" ]]; then
      return 0
    fi
    local status=0
    try_once || status=$?
    if [[ "$status" -eq 0 || "$status" -eq 2 ]]; then
      return 0
    fi
    if ((notified == 0)); then
      notify "$FAILURE"
      notified=1
    fi
    sleep_15
  done
}

if [[ "${1:-}" == "build-image" ]]; then
  ensure_image
else
  main "$@"
fi
