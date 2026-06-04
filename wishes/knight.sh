#!/usr/bin/env bash
# knight.sh — polls for pending spells and executes them via Claude Code
# usage:  bash wishes/knight.sh
# env:    POLL_INTERVAL=seconds (default 600)

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SPELL_DIR="$REPO_DIR/wishes/spell"
PHANTASM_DIR="$REPO_DIR/wishes/phantasm"
POLL_INTERVAL="${POLL_INTERVAL:-600}"
LOG_FILE="$REPO_DIR/wishes/knight.log"
LOG_RETAIN_DAYS="${LOG_RETAIN_DAYS:-7}"

LOCK_FILE="/tmp/knight-math.lock"

cd "$REPO_DIR"

log() { echo "[$(date '+%Y/%m/%d %H:%M:%S')] $*" | tee -a "$LOG_FILE" >&2; }

trim_log() {
    local log_file="$1"
    [[ -f "$log_file" ]] || return
    local cutoff
    cutoff=$(date -d "${LOG_RETAIN_DAYS} days ago" '+%Y-%m-%d')
    local start
    start=$(awk -v c="$cutoff" '
        match($0, /\[([0-9]{4})[\/\-]([0-9]{2})[\/\-]([0-9]{2})/, a) {
            if (a[1] "-" a[2] "-" a[3] >= c) { print NR; exit }
        }
    ' "$log_file")
    if [[ -n "$start" && "$start" -gt 1 ]]; then
        local tmp; tmp=$(mktemp)
        tail -n +"$start" "$log_file" > "$tmp" && mv "$tmp" "$log_file"
    fi
}

# 防止重复启动
if [ -f "$LOCK_FILE" ] && kill -0 "$(cat "$LOCK_FILE")" 2>/dev/null; then
    log "knight already running (PID $(cat "$LOCK_FILE")), exiting"
    exit 0
fi
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"; kill -- -$$ 2>/dev/null' EXIT

# ── spell file helpers ────────────────────────────────────────────────────────

get_first_pending() {
    python3 - "$1" <<'EOF'
import sys, re

with open(sys.argv[1], encoding='utf-8') as f:
    content = f.read()

pattern = r'^--- (wish-\S+) \[pending\]\n(.*?)(?=^--- wish-|\Z)'
m = re.search(pattern, content, re.MULTILINE | re.DOTALL)
if not m:
    sys.exit(1)

print(m.group(1))
print(m.group(2).strip())
EOF
}

set_status() {
    python3 - "$1" "$2" "$3" "$4" <<'EOF'
import sys
file, wish_id, from_s, to_s = sys.argv[1:]
with open(file, encoding='utf-8') as f:
    text = f.read()
with open(file, 'w', encoding='utf-8') as f:
    f.write(text.replace(f'--- {wish_id} [{from_s}]', f'--- {wish_id} [{to_s}]', 1))
EOF
}

get_dynamic_sleep() {
    python3 - "$1" <<'EOF'
import sys, re, datetime

text = sys.argv[1]
m = re.search(r'resets\s+(\d{1,2})(?::(\d{2}))?(am|pm)', text, re.IGNORECASE)
if not m:
    sys.exit(1)

hr = int(m.group(1))
mn = int(m.group(2)) if m.group(2) else 0
meridian = m.group(3).lower()

if meridian == 'pm' and hr != 12:
    hr += 12
elif meridian == 'am' and hr == 12:
    hr = 0

now = datetime.datetime.now()
target = now.replace(hour=hr, minute=mn + 1, second=0, microsecond=0)

if target <= now:
    target += datetime.timedelta(days=1)

print(int((target - now).total_seconds()))
EOF
}

recover_failed_wishes() {
    local any_recovered=false

    for spell_file in "$SPELL_DIR"/*.md; do
        [ -f "$spell_file" ] || continue
        local date_str
        date_str=$(basename "$spell_file" .md)
        local phantasm_file="$PHANTASM_DIR/${date_str}.md"
        [ -f "$phantasm_file" ] || continue

        local recovered
        recovered=$(python3 - "$spell_file" "$phantasm_file" <<'EOF'
import sys, re, datetime

spell_file, phantasm_file = sys.argv[1:]

with open(spell_file, encoding='utf-8') as f:
    spell_content = f.read()
with open(phantasm_file, encoding='utf-8') as f:
    phantasm_content = f.read()

now = datetime.datetime.now()
threshold = datetime.timedelta(hours=26)

failed_wishes = re.findall(r'^--- (wish-\S+) \[failed\]', spell_content, re.MULTILINE)

recovered = []
for wish_id in failed_wishes:
    entries = list(re.finditer(
        rf'^--- {re.escape(wish_id)} \[(\S+)\]\n(.*?)(?=^--- wish-|\Z)',
        phantasm_content, re.MULTILINE | re.DOTALL
    ))
    if not entries:
        continue
    last = entries[-1]
    if last.group(1) != 'failed':
        continue
    block = last.group(2)

    end_m = re.search(r'end\s+(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})', block)
    if not end_m:
        continue
    end_time = datetime.datetime.strptime(end_m.group(1), '%Y/%m/%d %H:%M:%S')
    if now - end_time > threshold:
        continue

    reset_m = re.search(r'resets\s+(\d{1,2})(?::(\d{2}))?(am|pm)', block, re.IGNORECASE)
    if not reset_m:
        continue
    hr = int(reset_m.group(1))
    mn = int(reset_m.group(2)) if reset_m.group(2) else 0
    meridian = reset_m.group(3).lower()
    if meridian == 'pm' and hr != 12:
        hr += 12
    elif meridian == 'am' and hr == 12:
        hr = 0
    reset_time = end_time.replace(hour=hr, minute=mn + 1, second=0, microsecond=0)
    if reset_time <= end_time:
        reset_time += datetime.timedelta(days=1)
    if reset_time > now:
        continue

    recovered.append(wish_id)

if recovered:
    content = spell_content
    for wish_id in recovered:
        content = content.replace(f'--- {wish_id} [failed]', f'--- {wish_id} [pending]', 1)
    with open(spell_file, 'w', encoding='utf-8') as f:
        f.write(content)
    for wish_id in recovered:
        print(wish_id)
EOF
        ) || continue

        if [ -n "$recovered" ]; then
            while IFS= read -r wish_id; do
                log "recover: ${date_str}/${wish_id} → [pending]"
            done <<< "$recovered"
            git add "wishes/spell/${date_str}.md"
            any_recovered=true
        fi
    done

    if [ "$any_recovered" = true ]; then
        git commit -m "recover: reset token-limited wishes to [pending]"
        git push
    fi
}

# ── execution ─────────────────────────────────────────────────────────────────

process_wish() {
    local spell_file="$1"
    local date_str
    date_str=$(basename "$spell_file" .md)

    local raw
    raw=$(get_first_pending "$spell_file") || return 1

    local wish_id prompt
    wish_id=$(printf '%s' "$raw" | head -1)
    prompt=$(printf '%s' "$raw" | tail -n +2)

    log "$date_str / $wish_id → running"

    set_status "$spell_file" "$wish_id" "pending" "running"
    git add "wishes/spell/${date_str}.md"
    git commit -m "wish: ${date_str}/${wish_id} [running]"
    git push

    local start_time exit_code cc_output diff_stat status
    start_time=$(date '+%Y/%m/%d %H:%M:%S')
    exit_code=0

    cc_output=$(claude -p "$prompt" \
        --allowedTools "Bash Edit Read Write" \
        --allow-dangerously-skip-permissions \
        2>&1) || exit_code=$?

    local end_time
    end_time=$(date '+%Y/%m/%d %H:%M:%S')

    diff_stat=$(git diff --stat HEAD 2>/dev/null || echo "(no file changes)")

    if [ "$exit_code" -eq 0 ]; then
        status="done"
    elif printf '%s' "$cc_output" | grep -qiE "token|context.?window|rate.?limit|session.?limit"; then
        local sleep_secs
        if sleep_secs=$(get_dynamic_sleep "$cc_output"); then
            log "$date_str / $wish_id → 触发 API 限额！识别到具体解限时间，休眠 ${sleep_secs} 秒..."

            set_status "$spell_file" "$wish_id" "running" "pending"
            git add "wishes/spell/${date_str}.md"
            git commit -m "wish: ${date_str}/${wish_id} [reverted: sleeping ${sleep_secs}s for reset]"
            git push

            sleep "$sleep_secs"
            return 0
        else
            log "$date_str / $wish_id → 触发限额，但未能解析到 resets 时间，标记为 failed。"
            status="failed"
        fi
    else
        status="failed"
    fi

    set_status "$spell_file" "$wish_id" "running" "$status"

    local phantasm_file="$PHANTASM_DIR/${date_str}.md"
    {
        printf '\n--- %s [%s]\n' "$wish_id" "$status"
        printf '    start    %s\n' "$start_time"
        printf '    end      %s\n' "$end_time"
        printf '    exit     %s\n' "$exit_code"
        printf '\n    prompt\n'
        printf '%s\n' "$prompt" | sed 's/^/        /'
        printf '\n    diff\n'
        printf '%s\n' "$diff_stat" | sed 's/^/        /'
        printf '\n    output\n'
        printf '%s\n' "$cc_output" | sed 's/^/        /'
        printf '\n'
    } >> "$phantasm_file"

    git add -A
    git commit -m "phantasm: ${date_str}/${wish_id} [$status]"
    git push

    log "$date_str / $wish_id → [$status]"
}

# ── main loop ─────────────────────────────────────────────────────────────────

reset_stale_running() {
    local any=false
    for spell_file in "$SPELL_DIR"/*.md; do
        [ -f "$spell_file" ] || continue
        local date_str
        date_str=$(basename "$spell_file" .md)
        local reset
        reset=$(python3 - "$spell_file" <<'EOF'
import sys, re
from pathlib import Path

spell_file = Path(sys.argv[1])
content = spell_file.read_text(encoding='utf-8')
running = re.findall(r'^--- (wish-\S+) \[running\]', content, re.MULTILINE)
if not running:
    sys.exit(0)
new_content = re.sub(r'^(--- wish-\S+) \[running\]', r'\1 [pending]', content, flags=re.MULTILINE)
spell_file.write_text(new_content, encoding='utf-8')
for w in running:
    print(w)
EOF
        ) || continue
        if [ -n "$reset" ]; then
            while IFS= read -r wish_id; do
                log "startup: ${date_str}/${wish_id} [running→pending] (stale from previous session)"
            done <<< "$reset"
            git add "wishes/spell/${date_str}.md"
            any=true
        fi
    done
    if [ "$any" = true ]; then
        git commit -m "recover: reset stale [running] wishes to [pending] on startup"
        git push
    fi
}

main() {
    trim_log "$LOG_FILE"
    log "knight online  (poll interval ${POLL_INTERVAL}s)"
    mkdir -p "$SPELL_DIR" "$PHANTASM_DIR"

    git pull --rebase 2>/dev/null || log "git pull failed on startup"
    reset_stale_running

    local _idle=false
    local _last_heartbeat=0
    local _heartbeat_interval=21600  # 6 hours

    while true; do
        git pull --rebase 2>/dev/null || log "git pull failed, will retry"

        recover_failed_wishes

        local any=false
        for spell_file in "$SPELL_DIR"/*.md; do
            [ -f "$spell_file" ] || continue
            while process_wish "$spell_file"; do
                any=true
            done
        done

        if [ "$any" = false ]; then
            local _now; _now=$(date +%s)
            if ! $_idle; then
                log "no pending spells — polling every ${POLL_INTERVAL}s"
                _idle=true
                _last_heartbeat=$_now
            elif (( _now - _last_heartbeat >= _heartbeat_interval )); then
                log "online — idle $(( (_now - _last_heartbeat) / 3600 ))h, still polling"
                _last_heartbeat=$_now
                git add "$LOG_FILE" 2>/dev/null
                git diff --cached --quiet 2>/dev/null || {
                    git commit -m "log: heartbeat" && git push 2>/dev/null || true
                }
            fi
            sleep "$POLL_INTERVAL"
        else
            _idle=false
        fi
    done
}

main
