import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "stop_capture.py")


def human(text):
    return {"type": "user", "entrypoint": "cli", "origin": {"kind": "human"},
            "timestamp": "2026-11-09T10:00:00", "message": {"role": "user", "content": text}}


class StopCaptureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "repo")
        os.makedirs(os.path.join(self.root, ".claude", "rules"))
        subprocess.run(["git", "init", "-q", self.root], check=True)
        with open(os.path.join(self.root, ".claude", "rules", "x.md"), "w") as f:
            f.write('---\npaths: ["src/**"]\n---\n- a\n')
        self.transcript = os.path.join(self.tmp.name, "t.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, records, session="s1", env=None, **extra):
        with open(self.transcript, "w") as f:
            f.write("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n")
        payload = {"session_id": session, "transcript_path": self.transcript, "cwd": self.root, **extra}
        r = subprocess.run([sys.executable, SCRIPT], input=json.dumps(payload), capture_output=True, text=True,
                           env={**os.environ, **(env or {})})
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_correction_blocks_once_per_session(self):
        recs = [human("thêm API"), {"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}},
                human("không phải, đừng tạo Configuration.cs")]
        out = json.loads(self.run_hook(recs))
        self.assertEqual(out["decision"], "block")
        self.assertIn("learn-new", out["reason"])
        self.assertIn("đừng tạo Configuration.cs", out["reason"])
        self.assertEqual(self.run_hook(recs), "")  # lần 2 trong cùng phiên: im lặng
        self.assertNotEqual(self.run_hook(recs, session="s2"), "")  # phiên khác: nhắc lại

    def test_silent_cases(self):
        corr = [human("sai rồi, lần sau nhớ chạy test")]
        self.assertEqual(self.run_hook([human("thêm API lấy danh sách")]), "")
        self.assertEqual(self.run_hook(corr, stop_hook_active=True), "")
        self.assertEqual(self.run_hook(corr, env={"CODEBASE_MEMORY_STOP_CAPTURE": "0"}), "")
        headless = dict(corr[0], entrypoint="sdk-cli")
        self.assertEqual(self.run_hook([headless]), "")
        tool_result_last = corr + [{"type": "user", "message": {"content": [{"type": "tool_result", "content": "đừng"}]}}]
        self.assertNotEqual(self.run_hook(tool_result_last, session="s3"), "")  # tool_result không phải tin user

    def test_repo_without_rules_is_silent(self):
        os.remove(os.path.join(self.root, ".claude", "rules", "x.md"))
        self.assertEqual(self.run_hook([human("không phải, đừng làm vậy")]), "")

    def test_bad_input_never_fails(self):
        r = subprocess.run([sys.executable, SCRIPT], input="not json", capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
