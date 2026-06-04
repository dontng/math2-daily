#!/usr/bin/env python3
"""
OCR + solve math problems from photos via Claude Vision.

Usage:
    python3 scripts/solve.py IMG [IMG ...]

Env:
    ANTHROPIC_API_KEY   required
    CLAUDE_MODEL        default: claude-sonnet-4-6
"""

import os, sys, re, mimetypes, base64
from pathlib import Path
from datetime import datetime

REPO_DIR = Path(__file__).parent.parent
PROBLEMS_DIR = REPO_DIR / 'problems'

# load .env if present
_env = REPO_DIR / '.env'
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _v = _line.split('=', 1)
            os.environ.setdefault(_k.strip(), _v.strip())

MONTHS = {
    1: 'jan', 2: 'feb', 3: 'mar', 4: 'apr',
    5: 'may', 6: 'june', 7: 'july', 8: 'aug',
    9: 'sep', 10: 'oct', 11: 'nov', 12: 'dec',
}

PROMPT = """\
请完成：

1. **识别题目**：将图片中所有题目（保留题号）精确转写为 LaTeX，题目单行内联。

2. **极度压缩解题**，严格遵守以下排版规则：
   - 中间推导用行内 $...$ + 箭头/分号串联，**不开独立 $$ 块**
   - 只有关键结果（分段函数、最终答案）才用 $$ 块
   - 两个分段函数可放同一 $$ 块，用 \\qquad 隔开
   - 不写任何文字解释，只写数学符号（∴ ∵ ⟹ 令 设 等）
   - 不加编号标题（不写"第一步"之类）

**严格**按以下格式输出（禁止添加额外说明）：

## 题目

[题号]

$$[题目 LaTeX，\lim \int \sum 等符号在展示模式下下标居中]$$

## 解

[若需说明关键公式，一行行内 $...$]

$$[关键中间结果，多个分段函数用 \\qquad 并排]$$

$[复合/推导链，用 \\xrightarrow{} 或 \\Rightarrow 串联，分号隔开各段情况]$

$$\\therefore [最终答案]$$\
"""


def count_existing_days() -> int:
    if not PROBLEMS_DIR.exists():
        return 0
    return sum(
        1 for p in PROBLEMS_DIR.rglob('*.md')
        if re.match(r'\d{4}-day\d+', p.stem)
    )


def get_today_file() -> Path:
    now = datetime.now()
    month_dir = PROBLEMS_DIR / MONTHS[now.month]
    month_dir.mkdir(parents=True, exist_ok=True)
    mmdd = now.strftime('%m%d')

    existing = sorted(month_dir.glob(f'{mmdd}-day*.md'))
    if existing:
        return existing[0]

    day_n = count_existing_days() + 1
    path = month_dir / f'{mmdd}-day{day_n:02d}.md'
    path.write_text(f'# {mmdd}\n\n', encoding='utf-8')
    return path


def solve_image(client, model_name: str, img_path: Path) -> str:
    mime = mimetypes.guess_type(str(img_path))[0] or 'image/jpeg'
    img_b64 = base64.standard_b64encode(img_path.read_bytes()).decode()

    response = client.messages.create(
        model=model_name,
        max_tokens=4096,
        messages=[{
            'role': 'user',
            'content': [
                {
                    'type': 'image',
                    'source': {
                        'type': 'base64',
                        'media_type': mime,
                        'data': img_b64,
                    },
                },
                {
                    'type': 'text',
                    'text': PROMPT,
                },
            ],
        }],
    )
    return response.content[0].text.strip()


def main():
    if len(sys.argv) < 2:
        print('Usage: python3 scripts/solve.py IMG [IMG ...]', file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print('Error: ANTHROPIC_API_KEY not set\n'
              '  echo "ANTHROPIC_API_KEY=your_key" >> .env', file=sys.stderr)
        sys.exit(1)

    try:
        import anthropic
    except ImportError:
        print('Error: anthropic not installed\n'
              '  pip install anthropic', file=sys.stderr)
        sys.exit(1)

    model_name = os.environ.get('CLAUDE_MODEL', 'claude-sonnet-4-6')
    client = anthropic.Anthropic(api_key=api_key)

    today_file = get_today_file()
    print(f'→ {today_file.relative_to(REPO_DIR)}')

    for arg in sys.argv[1:]:
        img_path = Path(arg)
        if not img_path.exists():
            print(f'  skip: {arg} not found', file=sys.stderr)
            continue

        print(f'  {img_path.name} ... ', end='', flush=True)
        result = solve_image(client, model_name, img_path)
        print('done')

        with open(today_file, 'a', encoding='utf-8') as f:
            f.write(f'\n---\n\n{result}\n')

        print()
        print(result)
        print()


if __name__ == '__main__':
    main()
