#!/usr/bin/env python3
"""Hook Stop: tin nhắn vừa rồi của user có dạng sửa sai / dạy lại → chặn kết thúc lượt MỘT lần mỗi phiên,
yêu cầu Claude đề xuất ghi bài học bằng /codebase-memory:learn-new (chỉ đề xuất, không tự ghi).

Im lặng (exit 0, không in gì) khi: CODEBASE_MEMORY_STOP_CAPTURE=0; stop_hook_active; không phải git repo;
repo chưa có .claude/rules/*.md có `paths:` (chưa dùng codebase-memory); đã nhắc trong phiên này;
tin nhắn cuối không khớp mẫu sửa sai; phiên headless (`claude -p`, entrypoint sdk-cli); mọi lỗi.
"""
import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mine_history import is_correction, user_text  # noqa: E402  (cùng regex với thước đo --count)

REASON = (
    "codebase-memory: tin nhắn vừa rồi của user có dạng sửa sai / dạy lại: \"{quote}\". "
    "Nếu đó là bài học về CODEBASE (convention, lý do, bẫy, quyết định) chưa có trong AGENTS.md/.claude/rules: "
    "thêm 1 đoạn ngắn cuối câu trả lời đề xuất ghi bằng /codebase-memory:learn-new (nêu bài học 1 dòng, chờ user duyệt, "
    "KHÔNG tự ghi file). Nếu chỉ là làm rõ yêu cầu, sở thích cá nhân, hoặc đã có trong rule: bỏ qua và kết thúc bình thường."
)


def last_user_message(transcript):
    last = None
    with open(transcript, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            text = user_text(rec)
            if text is not None:
                last = text
    return last


def uses_codebase_memory(root):
    for path in glob.glob(os.path.join(root, ".claude", "rules", "**", "*.md"), recursive=True):
        with open(path, encoding="utf-8", errors="replace") as f:
            if any(line.startswith("paths:") for line in f):
                return True
    return False


def main():
    if os.environ.get("CODEBASE_MEMORY_STOP_CAPTURE", "1") == "0":
        return
    data = json.load(sys.stdin)
    if data.get("stop_hook_active"):
        return
    r = subprocess.run(["git", "-C", data.get("cwd") or os.getcwd(), "rev-parse", "--show-toplevel",
                        "--absolute-git-dir"], capture_output=True, text=True)
    if r.returncode != 0:
        return
    root, git_dir = r.stdout.splitlines()[:2]
    if not uses_codebase_memory(root):
        return
    # shortcut: flag file mỗi phiên không bao giờ được dọn (vài byte/phiên), dọn khi .git/codebase-memory/ phình to
    flag = os.path.join(git_dir, "codebase-memory", f"stop-{data.get('session_id', 'unknown')}")
    if os.path.exists(flag):
        return
    msg = last_user_message(data["transcript_path"])
    if not msg or not is_correction(msg):
        return
    os.makedirs(os.path.dirname(flag), exist_ok=True)
    open(flag, "w").close()
    quote = " ".join(msg.split())[:160]
    print(json.dumps({"decision": "block", "reason": REASON.format(quote=quote)}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # hook không bao giờ được làm kẹt phiên
        pass
    sys.exit(0)
