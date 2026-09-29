#!/usr/bin/env bash
# Mac host: one daily digest after 08:00 local time. Tokens stay in memory.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAILURE="Daily digest did not run."
IMAGE="${EMAILS_ASSISTANT_IMAGE:-emails-assistant:daily}"
CONTAINER_ROOT="/workspaces/emails-assistant"
CONTAINER_DAILY="/daily"

export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"

daily_dir() {
  if [[ -n "${EMAILS_ASSISTANT_DAILY_DIR:-}" ]]; then
    printf '%s' "$EMAILS_ASSISTANT_DAILY_DIR"
    return
  fi
  printf '%s' "$HOME/Library/Application Support/emails-assistant/digests"
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
  "$ROOT/scripts/macos-access-token.sh" one-shot
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
  local host_daily tz
  host_daily="$(daily_dir)"
  tz="$(host_tz)"
  mkdir -p "$host_daily"
  printf '%s' "$1" | docker_cmd run --rm -i -u vscode \
    -e "TZ=$tz" \
    -e "PYTHONPATH=$CONTAINER_ROOT/src" \
    -e "EMAILS_ASSISTANT_DAILY_DIR=$CONTAINER_DAILY" \
    -e "EMAILS_ASSISTANT_ACCOUNTS=${EMAILS_ASSISTANT_ACCOUNTS:-email1,email2}" \
    -v "$ROOT:$CONTAINER_ROOT" \
    -v "$host_daily:$CONTAINER_DAILY" \
    -v /etc/localtime:/etc/localtime:ro \
    -w "$CONTAINER_ROOT" \
    "$IMAGE" \
    python3 -m emails_assistant.cli daily
}

try_once() {
  local payload result file
  if ! docker_cmd info >/dev/null 2>&1; then
    return 1
  fi
  payload="$(one_shot)" || return 1
  if [[ -z "$payload" ]]; then
    return 1
  fi
  file="$(today_file)"
  result="$(run_container "$payload")" || return 1
  result="${result//$'\n'/}"
  if [[ ! -f "$file" || ! "$result" =~ ^[0-9]+$ ]]; then
    return 1
  fi
  notify "$result"
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
    if [[ -f "$(today_file)" ]]; then
      return 0
    fi
    if try_once; then
      return 0
    fi
    if ((notified == 0)); then
      notify "$FAILURE"
      notified=1
    fi
    sleep_15
  done
}

main "$@"
