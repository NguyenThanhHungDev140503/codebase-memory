#!/usr/bin/env python3
"""Kiểm docs context (CLAUDE.md, AGENTS.md, rules, ADR...) còn khớp code không. Tất định, chỉ dùng stdlib + git.

Kiểm trong mỗi `inline code` (bỏ qua code block ``` và dòng có <!-- ctx-ignore -->):
  - đường dẫn tương đối repo (`a/b.cs`, `a/b/`) phải tồn tại VÀ nằm trong git (không gitignored/untracked);
    `a/b.cs:42` thì file phải có >= 42 dòng
  - identifier PascalCase ghép (`ReportRequestMarkerTests`) phải xuất hiện trong code (git grep, bỏ *.md)
  - rule có frontmatter `paths:` thì mỗi glob phải khớp >= 1 file; có thêm `verified: <sha>` thì báo
    khi code trong các glob đó đã đổi kể từ sha
Chế độ: --full (mặc định, in hết, exit 1 nếu có lỗi) | --session-start (cache theo HEAD + docs, in <= 5 dòng, luôn exit 0)
        | --metrics (token luôn nạp + số commit kể từ verified của từng rule).
"""
import hashlib
import os
import re
import subprocess
import sys

DOC_GLOBS = ["CLAUDE.md", "AGENTS.md", "CONTEXT.md", ".claude/rules/**/*.md", "docs/adr/*.md",
             "docs/claude-reference/*.md"]
IGNORE_MARK = "<!-- ctx-ignore"  # cho phép kèm lý do: <!-- ctx-ignore: file sinh tự động -->"
CODE_SPAN = re.compile(r"`([^`\n]+)`")
PATH_TOKEN = re.compile(r"^[\w.\-]+(?:/[\w.\-]+)*(?:/|\.\w{1,8})(?::(\d+))?$")
IDENT_TOKEN = re.compile(r"^I?[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+$")  # I? để bắt cả interface IWriteUnitOfWork
MAX_SESSION_LINES = 5


def git(root, *args, check=True):
    r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r


def doc_files(root):
    out = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "--",
              *[f":(glob){g}" for g in DOC_GLOBS]).stdout.split()
    return sorted(f for f in set(out) if os.path.isfile(os.path.join(root, f)))


def split_frontmatter(text):
    """Trả (dict frontmatter, số dòng frontmatter). Chỉ hỗ trợ `key: value`, list inline [..] và list `- x`."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, 0
    meta, key = {}, None
    for i, line in enumerate(lines[1:], start=1):
        s = line.strip()
        if s == "---":
            return meta, i + 1
        if s.startswith("- ") and key:
            meta.setdefault(key, []).append(s[2:].strip().strip("\"'"))
        elif ":" in s:
            key, _, val = s.partition(":")
            key, val = key.strip(), val.split("#")[0].strip()
            if val.startswith("["):
                meta[key] = [v.strip().strip("\"'") for v in val.strip("[]").split(",") if v.strip()]
            elif val:
                meta[key] = val.strip("\"'")
    return {}, 0  # không đóng frontmatter → coi như không có


def scan_doc(root, rel):
    """Trả (findings, identifiers cần kiểm [(rel, line_no, ident)], đường dẫn tồn tại [(rel, line_no, path)])."""
    text = open(os.path.join(root, rel), encoding="utf-8", errors="replace").read()
    meta, skip = split_frontmatter(text)
    findings, idents, paths, in_fence = [], [], [], False
    for no, line in enumerate(text.splitlines(), start=1):
        if no <= skip:
            continue
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or IGNORE_MARK in line:
            continue
        for tok in CODE_SPAN.findall(line):
            tok = tok.strip()
            m = PATH_TOKEN.match(tok)
            if m and "/" in tok:
                path = tok.split(":")[0]
                full = os.path.join(root, path)
                if not os.path.exists(full):
                    findings.append(f"{rel}:{no}: đường dẫn không tồn tại `{path}`")
                    continue
                paths.append((rel, no, path))
                if m.group(1):
                    n = int(m.group(1))
                    with open(full, encoding="utf-8", errors="replace") as f:
                        total = sum(1 for _ in f)
                    if n > total:
                        findings.append(f"{rel}:{no}: `{tok}` vượt quá số dòng ({total})")
            elif IDENT_TOKEN.match(tok):
                idents.append((rel, no, tok))
    findings += check_rule_meta(root, rel, meta)
    return findings, idents, paths


def untracked_refs(root, paths):
    """Đường dẫn có trên máy này nhưng KHÔNG nằm trong git: người khác clone repo sẽ thấy đường dẫn chết."""
    files = set(git(root, "ls-files", "-z").stdout.split("\0"))  # gồm cả file đã stage
    dirs = {d + "/" for f in files for d in _parents(f)}
    loose = sorted({p for _, _, p in paths if p.rstrip("/") not in files and p.rstrip("/") + "/" not in dirs})
    if not loose:
        return []
    r = subprocess.run(["git", "-C", root, "check-ignore", "--stdin"], input="\n".join(loose) + "\n",
                       capture_output=True, text=True)
    ignored = set(r.stdout.split("\n"))
    out = []
    for rel, no, p in paths:
        if p not in loose:
            continue
        if p in ignored:
            out.append(f"{rel}:{no}: `{p}` bị gitignore, người khác không có (bỏ tham chiếu; "
                       f"chỉ nhắc tên file sinh ra thì thêm <!-- ctx-ignore -->)")
        else:
            out.append(f"{rel}:{no}: `{p}` chưa được track (commit cùng docs, hoặc bỏ tham chiếu nếu chỉ giữ local)")
    return out


def _parents(path):
    parts = path.split("/")[:-1]
    return ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]


def check_rule_meta(root, rel, meta):
    paths = meta.get("paths")
    if not paths:
        return []
    paths = [paths] if isinstance(paths, str) else paths
    out = []
    for g in paths:
        if not git(root, "ls-files", "--", f":(glob){g}").stdout.strip():
            out.append(f"{rel}:1: glob `{g}` không khớp file nào (rule sẽ không bao giờ được nạp)")
    sha = meta.get("verified")
    if sha:
        if git(root, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}", check=False).returncode != 0:
            out.append(f"{rel}:1: verified `{sha}` không phải commit hợp lệ")
        else:
            changed = git(root, "diff", "--name-only", f"{sha}..HEAD", "--",
                          *[f":(glob){g}" for g in paths]).stdout.split()
            if changed:
                out.append(f"{rel}:1: {len(changed)} file trong paths đã đổi từ verified {sha} "
                           f"(vd `{changed[0]}`), cần rà lại")
    return out


def code_words(root):
    """Tập mọi từ trong file tracked (bỏ *.md, binary, file > 5MB). Đọc 1 lần: nhanh hơn git grep -o -w nhiều mẫu
    (đo trên repo ~3.900 file: 0.7s so với 45s)."""
    words, tok = set(), re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    for rel in git(root, "ls-files", "-z", "--", ":!*.md").stdout.split("\0"):
        path = os.path.join(root, rel)
        if not rel or not os.path.isfile(path) or os.path.getsize(path) > 5_000_000:
            continue
        with open(path, "rb") as f:
            data = f.read()
        if b"\0" not in data[:8000]:
            words.update(tok.findall(data.decode("utf-8", "replace")))
    return words


def missing_idents(root, idents):
    if not idents:
        return []
    found = code_words(root)
    return [f"{rel}:{no}: không tìm thấy `{t}` trong code" for rel, no, t in idents if t not in found]


def run(root):
    findings, idents, paths = [], [], []
    for rel in doc_files(root):
        f, i, p = scan_doc(root, rel)
        findings += f
        idents += i
        paths += p
    return findings + untracked_refs(root, paths) + missing_idents(root, idents)


def cache_key(root):
    head = git(root, "rev-parse", "HEAD", check=False).stdout.strip()
    h = hashlib.sha1(head.encode())
    for rel in doc_files(root):
        st = os.stat(os.path.join(root, rel))
        h.update(f"{rel}:{st.st_mtime_ns}:{st.st_size}".encode())
    return h.hexdigest()


def session_start(root):
    git_dir = git(root, "rev-parse", "--absolute-git-dir").stdout.strip()
    cache = os.path.join(git_dir, "codebase-memory.cache")
    key = cache_key(root)
    try:
        cached_key, _, cached_out = open(cache, encoding="utf-8").read().partition("\n")
        if cached_key == key:
            sys.stdout.write(cached_out)
            return
    except OSError:
        pass
    findings = run(root)
    out = ""
    if findings:
        out = (f"codebase-memory: {len(findings)} mục context có thể đã lỗi thời so với code "
               f"(xem đủ: python3 \"{os.path.abspath(__file__)}\" --full):\n")
        out += "".join(f"- {f}\n" for f in findings[:MAX_SESSION_LINES - 1])
    with open(cache, "w", encoding="utf-8") as fh:
        fh.write(key + "\n" + out)
    sys.stdout.write(out)


def metrics(root):
    """Token luôn nạp mỗi phiên (CLAUDE.md, AGENTS.md + @import) và tuổi `verified` của từng rule."""
    always = [f for f in ("CLAUDE.md", "AGENTS.md") if os.path.isfile(os.path.join(root, f))]
    for f in list(always):
        for line in open(os.path.join(root, f), encoding="utf-8", errors="replace"):
            imp = line.strip()[1:] if line.startswith("@") else ""
            if imp and imp not in always and os.path.isfile(os.path.join(root, imp)):
                always.append(imp)
    total = 0
    out = ["| Luôn nạp | Ký tự | ~Token |", "|---|---|---|"]
    for f in always:
        n = len(open(os.path.join(root, f), encoding="utf-8", errors="replace").read())
        total += n
        out.append(f"| {f} | {n} | {n // 3} |")
    out.append(f"| **Tổng** | {total} | **{total // 3}** |")
    out += ["", "| Rule | Dòng | verified | Commit sau verified |", "|---|---|---|---|"]
    for rel in doc_files(root):
        if not rel.startswith(".claude/rules/"):
            continue
        text = open(os.path.join(root, rel), encoding="utf-8", errors="replace").read()
        sha = split_frontmatter(text)[0].get("verified", "")
        behind = git(root, "rev-list", "--count", f"{sha}..HEAD", check=False).stdout.strip() if sha else ""
        out.append(f"| {rel} | {text.count(chr(10))} | {sha or '-'} | {behind or '?'} |")
    out.append("\n~Token ước lượng = ký tự / 3 (tiếng Việt có dấu thường tốn hơn).")
    return "\n".join(out)


def main():
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if r.returncode != 0:
        return 0  # không phải git repo: im lặng
    root = r.stdout.strip()
    if "--metrics" in sys.argv:
        print(metrics(root))
        return 0
    if "--session-start" in sys.argv:
        try:
            session_start(root)
        except Exception as e:  # hook không được làm hỏng việc mở phiên
            sys.stdout.write(f"codebase-memory: lỗi khi kiểm context ({e})\n")
        return 0
    findings = run(root)
    print("\n".join(findings) if findings else "codebase-memory: context khớp code (0 lỗi).")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
