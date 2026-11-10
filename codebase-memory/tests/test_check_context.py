import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "check_context.py")


def sh(cwd, *args):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class CheckContextTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        sh(self.root, "git", "init", "-q")
        write(self.root, "src/Order.cs", "public class OrderService {}\n" + "// x\n" * 9)  # 10 dòng
        write(self.root, "src/Util.cs", "class Util {}\n")
        sh(self.root, "git", "add", "-A")
        sh(self.root, "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
        self.sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=self.root,
                                  capture_output=True, text=True).stdout.strip()

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self, *flags):
        return subprocess.run([sys.executable, SCRIPT, *flags], cwd=self.root, capture_output=True, text=True)

    def test_clean_repo_passes(self):
        write(self.root, "CLAUDE.md", "Xem `src/Order.cs:5`, thư mục `src/`, type `OrderService`.\n")
        r = self.run_check()
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_reports_each_kind_of_staleness(self):
        write(self.root, "CLAUDE.md", "\n".join([
            "Dead `docs/agents/domain.md`.",
            "Too far `src/Order.cs:99`.",
            "Missing `ReportRequestMarkerTests` and interface `IWriteUnitOfWork`.",
            "Ignored `gone/file.cs` <!-- ctx-ignore -->",
            "```",
            "`inside/fence.cs` OrderGhost",
            "```",
            "Not a path `appsettings.<Env>.json`, url `/api/x`, home `~/.claude/x.md`.",
        ]) + "\n")
        out = self.run_check().stdout
        self.assertIn("CLAUDE.md:1: đường dẫn không tồn tại `docs/agents/domain.md`", out)
        self.assertIn("CLAUDE.md:2: `src/Order.cs:99` vượt quá số dòng (10)", out)
        self.assertIn("CLAUDE.md:3: không tìm thấy `ReportRequestMarkerTests`", out)
        self.assertIn("CLAUDE.md:3: không tìm thấy `IWriteUnitOfWork`", out)
        for absent in ["gone/file.cs", "inside/fence.cs", "Env", "/api/x", ".claude/x.md"]:
            self.assertNotIn(absent, out)

    def test_rule_frontmatter_globs_and_verified(self):
        write(self.root, ".claude/rules/orders.md",
              f"---\npaths:\n  - \"src/**/*.cs\"\n  - \"nope/**\"\nverified: {self.sha}\n---\n- dùng `OrderService`\n")
        out = self.run_check().stdout
        self.assertIn("glob `nope/**` không khớp file nào", out)
        self.assertNotIn("đã đổi từ verified", out)

        write(self.root, "src/Util.cs", "class Util { int x; }\n")
        sh(self.root, "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "change")
        out = self.run_check().stdout
        self.assertIn("1 file trong paths đã đổi từ verified", out)

    def test_session_start_is_short_cached_and_silent_when_clean(self):
        write(self.root, "CLAUDE.md", "".join(f"`missing/f{i}.cs`\n" for i in range(10)))
        first = self.run_check("--session-start")
        self.assertEqual(first.returncode, 0)
        self.assertLessEqual(len(first.stdout.strip().splitlines()), 5)
        self.assertIn("10 mục", first.stdout)
        self.assertEqual(self.run_check("--session-start").stdout, first.stdout)  # từ cache

        write(self.root, "CLAUDE.md", "Không có gì để kiểm.\n")  # docs đổi → cache vô hiệu
        self.assertEqual(self.run_check("--session-start").stdout, "")

    def test_metrics_counts_imports_and_rule_age(self):
        write(self.root, "CLAUDE.md", "@AGENTS.md\n")
        write(self.root, "AGENTS.md", "x" * 300)
        write(self.root, ".claude/rules/orders.md", f"---\npaths: [\"src/**\"]\nverified: {self.sha}\n---\n- a\n")
        write(self.root, "src/Util.cs", "class Util { int y; }\n")
        sh(self.root, "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "c2")
        out = self.run_check("--metrics").stdout
        self.assertIn("| AGENTS.md | 300 | 100 |", out)
        self.assertIn("| **Tổng** | 311 | **103** |", out)
        self.assertIn(f"| .claude/rules/orders.md | 5 | {self.sha} | 1 |", out)

    def test_reports_refs_to_ignored_and_untracked_files(self):
        write(self.root, ".gitignore", "env.generated.ts\nlocal-tests/\n")
        write(self.root, "src/env.generated.ts", "x\n")
        write(self.root, "local-tests/ArchTests.cs", "class ArchTests {}\n")
        write(self.root, "docs/new.md", "mới\n")
        write(self.root, "src/staged.cs", "class Staged {}\n")
        sh(self.root, "git", "add", "src/staged.cs")  # đã stage = coi như đã track
        write(self.root, "CLAUDE.md", "\n".join([
            "Gen `src/env.generated.ts`.",
            "Test `local-tests/ArchTests.cs`.",
            "Doc `docs/new.md`.",
            "Staged `src/staged.cs`, thư mục `src/`.",
            "Gen có lý do `src/env.generated.ts` <!-- ctx-ignore: file sinh tự động -->",
        ]) + "\n")
        out = self.run_check().stdout
        self.assertIn("CLAUDE.md:1: `src/env.generated.ts` bị gitignore", out)
        self.assertIn("CLAUDE.md:2: `local-tests/ArchTests.cs` bị gitignore", out)
        self.assertIn("CLAUDE.md:3: `docs/new.md` chưa được track", out)
        for absent in ["CLAUDE.md:4", "CLAUDE.md:5"]:
            self.assertNotIn(absent, out)

    def test_outside_git_repo_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, SCRIPT, "--session-start"], cwd=d, capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
