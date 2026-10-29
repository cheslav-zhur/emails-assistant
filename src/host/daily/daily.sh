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

# One reason line. Same set as record_summary_miss.
miss_reason_ok() {
  local marker="$1" line extra bytes
  [[ -f "$marker" ]] || return 1
  bytes="$(wc -c <"$marker" | tr -d '[:space:]')"
  [[ "$bytes" -le 81 ]] || return 1
  IFS= read -r line <"$marker" || return 1
  [[ "$line" =~ ^(no-key|credentials|empty|request:[A-Za-z_][A-Za-z0-9_]*|finish:[A-Z0-9_]+)$ ]] || return 1
  extra="$(tail -n +2 "$marker" || true)"
  [[ -z "$extra" ]]
}

# Transport blips only. Same names as _TRANSIENT_EXC_NAMES in summary.
miss_is_transient() {
  local marker="$1" line
  [[ -f "$marker" ]] || return 1
  IFS= read -r line <"$marker" || return 1
  [[ "$line" =~ ^request:(RemoteProtocolError|ConnectError|ReadTimeout|WriteTimeout|ConnectTimeout|PoolTimeout|NetworkError)$ ]]
}

image_stamp() {
  if [[ -n "${EMAILS_ASSISTANT_IMAGE_STAMP:-}" ]]; then
    printf '%s' "$EMAILS_ASSISTANT_IMAGE_STAMP"
    return
  fi
  printf '%s' "$HOME/Library/Application Support/emails-assistant/${TARGET}-image.sha256"
}

deps_hash() {
  if command -v shasum >/dev/null 2>&1; then
    cat "$ROOT/pyproject.toml" "$ROOT/uv.lock" | shasum -a 256 | awk '{print $1}'
    return
  fi
  cat "$ROOT/pyproject.toml" "$ROOT/uv.lock" | sha256sum | awk '{print $1}'
}

ensure_image() {
  local stamp hash
  stamp="$(image_stamp)"
  hash="$(deps_hash)"
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

folder_url() {
  local dir="$1"
  local encoded="" byte hex
  local LC_ALL=C
  [[ "$dir" == /* ]] || dir="${PWD}/${dir}"
  while IFS= read -r -n 1 byte || [[ -n "$byte" ]]; do
    case "$byte" in
      [A-Za-z0-9._~/-]) encoded="${encoded}${byte}" ;;
      *)
        hex="$(printf '%s' "$byte" | od -An -tu1 | awk '{printf "%02X", $1}')"
        encoded="${encoded}%${hex}"
        ;;
    esac
  done < <(printf '%s' "$dir")
  printf 'file://%s' "$encoded"
}

# Two-line success notice from the container. No free text from mail.
count_notice_ok() {
  local subtitle="$1" message="$2"
  [[ "$subtitle" =~ ^[1-9][0-9]?\ [A-Z][a-z]{2}$ ]] || return 1
  [[ "$message" =~ ^[0-9]+\ messages?\ summary$ ]]
}

notify() {
  local message="$1"
  local subtitle="${2:-}"
  local dir url
  local args=(-title "emails-assistant" -message "$message")
  if [[ -n "$subtitle" ]]; then
    count_notice_ok "$subtitle" "$message" || return 1
    args+=(-subtitle "$subtitle")
  else
    [[ "$message" == "$FAILURE" || "$message" == "$SUMMARY_MISS" ]] || return 1
  fi
  dir="$(daily_dir)"
  mkdir -p "$dir"
  url="$(folder_url "$dir")"
  args+=(-open "$url")
  if [[ -n "${EMAILS_ASSISTANT_NOTIFIER:-}" ]]; then
    "$EMAILS_ASSISTANT_NOTIFIER" "${args[@]}"
    return
  fi
  if ! command -v terminal-notifier >/dev/null 2>&1; then
    echo "terminal-notifier is not installed." >&2
    return 1
  fi
  terminal-notifier "${args[@]}"
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
  local payload result file marker
  if ! docker_cmd info >/dev/null 2>&1; then
    return 1
  fi
  ensure_image || return 1
  payload="$(one_shot)" || return 1
  if [[ -z "$payload" ]]; then
    return 1
  fi
  file="$(today_file)"
  local status=0 subtitle message
  result="$(run_container "$payload")" || status=$?
  if [[ "$status" -eq 0 && -f "$file" && "$result" == *$'\n'* && "$result" != *$'\n'*$'\n'* ]]; then
    subtitle="${result%%$'\n'*}"
    message="${result#*$'\n'}"
    if count_notice_ok "$subtitle" "$message"; then
      rm -f "$(miss_marker)"
      notify "$message" "$subtitle" || true
      return 0
    fi
  fi
  result="${result//$'\n'/}"
  if [[ "$result" == "$SUMMARY_MISS" && ! -f "$file" ]]; then
    marker="$(miss_marker)"
    if ! miss_reason_ok "$marker"; then
      : >"$marker"
    fi
    if miss_is_transient "$marker"; then
      return 3
    fi
    notify "$SUMMARY_MISS" || true
    return 2
  fi
  return 1
}

main() {
  local start_day notified=0 summary_notified=0
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
    if [[ -f "$(miss_marker)" ]] && ! miss_is_transient "$(miss_marker)"; then
      return 0
    fi
    local status=0
    try_once || status=$?
    if [[ "$status" -eq 0 || "$status" -eq 2 ]]; then
      return 0
    fi
    if [[ "$status" -eq 3 ]]; then
      if ((summary_notified == 0)); then
        notify "$SUMMARY_MISS" || true
        summary_notified=1
      fi
      sleep_15
      continue
    fi
    if ((notified == 0)) && notify "$FAILURE"; then
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
