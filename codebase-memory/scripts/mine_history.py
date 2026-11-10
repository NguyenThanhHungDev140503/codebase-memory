#!/usr/bin/env python3
"""Trích những lần user sửa sai / dạy lại Claude từ transcript Claude Code của repo hiện tại.

Đọc  ${CLAUDE_CONFIG_DIR:-~/.claude}/projects/<cwd mã hóa>*/*.jsonl  (kể cả worktree cùng tiền tố, bỏ subagents).
Mặc định: in báo cáo markdown (tin nhắn user khớp mẫu sửa sai + đoạn trả lời Claude ngay trước), đã che secret.
--count: số lần sửa sai / tổng tin nhắn user theo tuần ISO (thước đo "Claude đã học").
Không ghi gì vào repo; dùng --out để ghi ra file (nên là scratchpad).
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys

# Tín hiệu sửa sai / dạy lại. Ưu tiên recall: người duyệt sẽ lọc. "KHÔNG" viết hoa = nhấn mạnh (không bắt chữ thường).
CORRECTION = re.compile(
    r"không phải|sai rồi|bị sai|làm sai|nhầm|đã nói|nói rồi|đã bảo|bảo rồi|lần sau|từ giờ|từ nay|đừng|"
    r"không được|chứ không|ý tôi là|ý là|tại sao lại|sao lại|nhớ là|phải là|luôn luôn|convention|"
    r"\bKHÔNG\b|\bwrong\b|\bdon'?t\b|\bnever\b|\bstop\b|not what i",
    re.IGNORECASE)
CASE_SENSITIVE = {"KHÔNG"}
SECRET = re.compile(
    r"(?i)((?:password|pwd|accountkey|secret|token|apikey|api_key)\s*[=:]\s*)[^\s;\"',]+"
    r"|\b(?:sk|ghp|gho|xox[bp])-?[A-Za-z0-9_\-]{16,}\b|eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")
SKIP_PREFIX = ("<local-command", "<task-notification", "<system-reminder", "[Request interrupted", "Caveat:")
ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)


def redact(text):
    return SECRET.sub(lambda m: (m.group(1) or "") + "***", text)


def project_dirs(cwd, exact):
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    enc = re.sub(r"[^A-Za-z0-9]", "-", cwd)
    pattern = os.path.join(base, "projects", enc if exact else enc + "*")
    return sorted(d for d in glob.glob(pattern) if os.path.isdir(d))


def user_text(rec):
    """Text user thật gõ; None nếu là tool_result/meta/hook/lệnh nội bộ."""
    if rec.get("type") != "user" or rec.get("isMeta") or rec.get("isCompactSummary"):
        return None
    if rec.get("entrypoint") == "sdk-cli":  # phiên headless `claude -p` (script/agent), không phải user gõ
        return None
    if (rec.get("origin") or {}).get("kind", "human") != "human":
        return None
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    if not isinstance(content, str):
        return None
    text = content.strip()
    if text.startswith("<command-"):
        m = ARGS.search(text)
        text = m.group(1).strip() if m else ""
    if not text or text.startswith(SKIP_PREFIX):
        return None
    return text


def assistant_text(rec):
    if rec.get("type") != "assistant":
        return None
    content = (rec.get("message") or {}).get("content")
    if not isinstance(content, list):
        return None
    text = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text").strip()
    return text or None


def is_correction(text):
    for m in CORRECTION.finditer(text):
        tok = m.group(0)
        if tok.upper() in CASE_SENSITIVE and not tok.isupper():
            continue  # "không" thường quá phổ biến, chỉ tính "KHÔNG" viết hoa
        return True
    return False


def iter_messages(dirs, since):
    """Yield (timestamp, session, user_text, prev_assistant_text) theo thứ tự trong từng file.
    Phiên resume/fork chép lại lịch sử cũ → bỏ trùng theo (timestamp, text)."""
    seen = set()
    for d in dirs:
        for path in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
            prev = ""
            session = os.path.basename(path)[:8]
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    a = assistant_text(rec)
                    if a:
                        prev = a
                        continue
                    u = user_text(rec)
                    if u is None:
                        continue
                    ts = rec.get("timestamp", "")[:19]
                    if (since and ts[:10] < since) or (ts, u) in seen:
                        prev = ""
                        continue
                    seen.add((ts, u))
                    yield ts, session, u, prev
                    prev = ""


def report(dirs, since, out):
    rows = [(ts, s, u, p) for ts, s, u, p in iter_messages(dirs, since) if is_correction(u)]
    lines = [f"# Ứng viên bài học từ lịch sử chat ({len(rows)} tin nhắn)",
             f"Nguồn: {', '.join(os.path.basename(d) for d in dirs)}", ""]
    for ts, s, u, p in sorted(rows):
        lines.append(f"## {ts.replace('T', ' ')} · {s}")
        if p:
            lines.append("> Claude trước đó: " + redact(p[-300:]).replace("\n", " "))
        lines.append("**User:** " + redact(u[:600]).replace("\n", " "))
        lines.append("")
    out.write("\n".join(lines) + "\n")


def count(dirs, since, out):
    weeks = {}
    for ts, _, u, _ in iter_messages(dirs, since):
        try:
            y, w, _ = dt.date.fromisoformat(ts[:10]).isocalendar()
        except ValueError:
            continue
        total, corr = weeks.get((y, w), (0, 0))
        weeks[(y, w)] = (total + 1, corr + is_correction(u))
    out.write("| Tuần | Tin nhắn user | Sửa sai | Tỉ lệ |\n|---|---|---|---|\n")
    for (y, w), (total, corr) in sorted(weeks.items()):
        out.write(f"| {y}-W{w:02d} | {total} | {corr} | {corr / total:.0%} |\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--count", action="store_true", help="chỉ in thống kê theo tuần")
    ap.add_argument("--since", help="YYYY-MM-DD")
    ap.add_argument("--exact", action="store_true", help="không gộp worktree cùng tiền tố")
    ap.add_argument("--out", help="ghi ra file thay vì stdout")
    ap.add_argument("--cwd", default=None, help="repo cần quét (mặc định: git root của thư mục hiện tại)")
    a = ap.parse_args()
    cwd = a.cwd or subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                                  text=True).stdout.strip() or os.getcwd()
    dirs = project_dirs(cwd, a.exact)
    if not dirs:
        sys.exit(f"mine_history: không có transcript cho {cwd}")
    out = open(a.out, "w", encoding="utf-8") if a.out else sys.stdout
    (count if a.count else report)(dirs, a.since, out)
    if a.out:
        out.close()
        print(f"mine_history: đã ghi {a.out}")


if __name__ == "__main__":
    main()
