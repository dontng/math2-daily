#!/usr/bin/env python3
"""
Stop hook: session 中断时自动创建 wish 接力执行。
触发条件：
  1. token 耗尽（session limit 消息）
  2. 有文件操作但最后一条消息没有完成标记（被强制中断）
"""
import sys, json, re, subprocess
from pathlib import Path
from datetime import datetime

REPO_DIR     = Path(__file__).parent.parent
SPELL_DIR    = REPO_DIR / 'wishes' / 'spell'
PROJECTS_DIR = Path.home() / '.claude' / 'projects' / '-home-djology-math2-daily'

COMPLETION_MARKERS = [
    '已完成', '已推送', '已提交', '推送完', '全部完成', '任务完成',
    'done', 'Done', 'pushed', 'committed', 'push完', '完成了',
]
FILE_TOOLS = {'Bash', 'Edit', 'Write'}

def find_session_jsonl(stdin_data):
    if 'transcript_path' in stdin_data:
        p = Path(stdin_data['transcript_path'])
        if p.exists():
            return p
    if 'session_id' in stdin_data:
        p = PROJECTS_DIR / f"{stdin_data['session_id']}.jsonl"
        if p.exists():
            return p
    files = list(PROJECTS_DIR.glob('*.jsonl'))
    return max(files, key=lambda f: f.stat().st_mtime) if files else None

def parse_session(jsonl_path):
    first_prompt    = None
    token_limited   = False
    had_file_ops    = False
    last_text       = ''

    with open(jsonl_path, encoding='utf-8') as f:
        for line in f:
            try:
                d = json.loads(line.strip())
            except Exception:
                continue

            if d.get('type') == 'user' and first_prompt is None:
                content = d.get('message', {}).get('content', '')
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get('type') == 'text':
                            text = block.get('text', '').strip()
                            if text:
                                first_prompt = text
                                break
                elif isinstance(content, str) and content.strip():
                    first_prompt = content.strip()

            if d.get('type') == 'assistant':
                content = d.get('message', {}).get('content', '')
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get('type') == 'tool_use' and block.get('name') in FILE_TOOLS:
                            had_file_ops = True
                        if block.get('type') == 'text' and block.get('text', '').strip():
                            last_text = block['text']
                elif isinstance(content, str):
                    last_text = content

                if re.search(r'session.?limit|resets\s+\d', last_text, re.IGNORECASE):
                    token_limited = True

    interrupted = (
        not token_limited
        and had_file_ops
        and not any(m.lower() in last_text.lower() for m in COMPLETION_MARKERS)
    )

    return first_prompt, token_limited, interrupted

def get_next_wish_id(spell_file):
    if not spell_file.exists():
        return 'wish-01'
    ids = re.findall(r'^--- (wish-\d+)', spell_file.read_text(encoding='utf-8'), re.MULTILINE)
    if not ids:
        return 'wish-01'
    return f"wish-{max(int(re.search(r'\d+', w).group()) for w in ids) + 1:02d}"

def create_wish(prompt, reason):
    today = datetime.now().strftime('%m%d')
    spell_file = SPELL_DIR / f'{today}.md'
    SPELL_DIR.mkdir(parents=True, exist_ok=True)
    wish_id = get_next_wish_id(spell_file)
    if not spell_file.exists():
        spell_file.write_text(f'# {today}\n\n', encoding='utf-8')
    content = spell_file.read_text(encoding='utf-8')
    body = f'{prompt}\n\n（接续上次未完成的工作，从当前文件状态继续。）'
    spell_file.write_text(content + f'\n--- {wish_id} [pending]\n{body}\n', encoding='utf-8')
    return wish_id, spell_file, today

def main():
    try:
        raw = sys.stdin.read() or '{}'
        stdin_data = json.loads(raw)
    except Exception:
        stdin_data = {}
        raw = ''

    log = REPO_DIR / '.auto_wish_debug.log'
    with open(log, 'a') as f:
        f.write(f"{datetime.now()} stdin_keys={list(stdin_data.keys())} raw_prefix={raw[:200]}\n")

    jsonl = find_session_jsonl(stdin_data)
    if not jsonl:
        return

    first_prompt, token_limited, interrupted = parse_session(jsonl)

    if not (token_limited or interrupted):
        return
    if not first_prompt:
        return

    reason = 'token limit' if token_limited else 'interrupted'
    wish_id, spell_file, today = create_wish(first_prompt, reason)

    cwd = str(REPO_DIR)
    subprocess.run(['git', 'add', str(spell_file)], cwd=cwd)
    subprocess.run(['git', 'commit', '-m', f'wish: {today}/{wish_id} [auto: {reason}]'], cwd=cwd)
    subprocess.run(['git', 'push'], cwd=cwd)

    print(f'[auto_wish] {reason} → {today}/{wish_id} created', file=sys.stderr)

if __name__ == '__main__':
    main()
