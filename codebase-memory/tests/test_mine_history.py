import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "mine_history.py")
REPO = "/work/My_Repo"


def rec(kind, text, ts, **extra):
    if kind == "assistant":
        msg = {"role": "assistant", "content": [{"type": "text", "text": text}]}
    else:
        msg = {"role": "user", "content": text}
    return {"type": kind, "timestamp": ts, "message": msg, **extra}


class MineHistoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        proj = os.path.join(self.tmp.name, "projects", re.sub(r"[^A-Za-z0-9]", "-", REPO))
        os.makedirs(os.path.join(proj, "subagents"))
        human = {"origin": {"kind": "human"}}
        rows = [
            rec("user", "thêm API lấy danh sách", "2026-11-02T09:00:00", **human),
            rec("assistant", "Tôi đã tạo file OrderConfiguration.cs", "2026-11-02T09:01:00"),
            rec("user", "không phải, dùng Data Annotations, đừng tạo Configuration.cs", "2026-11-02T09:02:00", **human),
            rec("user", "Base directory for this skill: không phải tin user", "2026-11-02T09:03:00", isMeta=True),
            {"type": "user", "timestamp": "2026-11-02T09:04:00",
             "message": {"content": [{"type": "tool_result", "content": "đừng"}]}},
            rec("user", "<command-name>/x</command-name><command-args>lần sau nhớ chạy test</command-args>",
                "2026-11-10T08:00:00", **human),
            rec("user", "không có gì sai cả", "2026-11-10T08:05:00", **human),  # "không" thường: không tính
            rec("user", "KHÔNG commit, password=Sup3rS3cret!", "2026-11-10T08:06:00", **human),
        ]
        with open(os.path.join(proj, "s1.jsonl"), "w") as f:
            f.write("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\nnot json\n")
        # phiên fork chép lại đúng tin cũ + 1 phiên headless (claude -p): đều không được tính thêm
        with open(os.path.join(proj, "s2-fork.jsonl"), "w") as f:
            f.write(json.dumps(rows[2], ensure_ascii=False) + "\n")
        with open(os.path.join(proj, "s3-headless.jsonl"), "w") as f:
            f.write(json.dumps(rec("user", "đừng ghi file", "2026-11-10T09:00:00", entrypoint="sdk-cli")) + "\n")
        with open(os.path.join(proj, "subagents", "a.jsonl"), "w") as f:
            f.write(json.dumps(rec("user", "đừng làm vậy", "2026-11-02T10:00:00", **human)) + "\n")
        self.env = {**os.environ, "CLAUDE_CONFIG_DIR": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, *args):
        return subprocess.run([sys.executable, SCRIPT, "--cwd", REPO, *args], env=self.env,
                              capture_output=True, text=True, check=True).stdout

    def test_report_keeps_only_human_corrections_with_context(self):
        out = self.run_script()
        self.assertIn("(3 tin nhắn)", out)
        self.assertIn("Claude trước đó: Tôi đã tạo file OrderConfiguration.cs", out)
        self.assertIn("dùng Data Annotations", out)
        self.assertIn("lần sau nhớ chạy test", out)  # args của slash command
        for absent in ["Base directory", "thêm API", "không có gì sai", "subagents", "đừng làm vậy"]:
            self.assertNotIn(absent, out)

    def test_secrets_are_redacted(self):
        out = self.run_script()
        self.assertIn("password=***", out)
        self.assertNotIn("Sup3rS3cret", out)

    def test_count_per_week(self):
        out = self.run_script("--count")
        self.assertIn("| 2026-W45 | 2 | 1 | 50% |", out)
        self.assertIn("| 2026-W46 | 3 | 2 | 67% |", out)


if __name__ == "__main__":
    unittest.main()
