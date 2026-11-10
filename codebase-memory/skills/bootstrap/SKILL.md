---
name: bootstrap
description: Dựng bộ context dài hạn cho một repo (AGENTS.md nguồn chính, CLAUDE.md import, .claude/rules theo đường dẫn, ADR, CONTEXT.md) từ docs cũ, lịch sử chat và git log — chỉ giữ điều không suy ra được từ code, có bằng chứng. Chạy một lần cho mỗi repo.
disable-model-invocation: true
argument-hint: "[đường dẫn repo, mặc định repo hiện tại]"
---

# bootstrap

Mục tiêu: phiên Claude mới trong repo này không phải được dạy lại. Đầu ra là ĐỀ XUẤT; ghi sau khi user duyệt. Không commit.
Script (tính từ thư mục skill này): `<skill>/../../scripts/check_context.py`, `<skill>/../../scripts/mine_history.py`.

## Cổng nạp (ghi nguyên văn, áp cho MỌI mục)

1. **Đáng nhớ**: Claude đã từng sai điều này, HOẶC không suy ra được từ code lân cận (lý do, ràng buộc ngoài, bẫy runtime, quyết định), HOẶC là convention áp dụng trên nhiều file mà AI chỉ đọc vài file sẽ phá (có số liệu N/M, vd "controller chỉ gọi mediator", "không tự trim vì pipeline đã trim"). Phải là MỆNH LỆNH. Cấm: cây thư mục, danh sách base class/module dạng mô tả, kiến thức framework phổ thông.
2. **Có bằng chứng**: `path:line` trong file ĐÃ ĐƯỢC TRACK (`git ls-files <path>` có kết quả). Không trỏ tới file gitignored, untracked hay file user giữ local (test không push...). Không tìm được bằng chứng → đưa vào "cần user quyết", không ghi.
3. **Không máy hóa được**: kiểm được bằng test/analyzer thì ghi "nên có test" vào mục đề xuất cho user, không viết rule dài thay test.

## Bước 1: Khảo sát (chỉ đọc)

- Context sẵn có: `CLAUDE.md`, `AGENTS.md`, `.claude/rules/`, `docs/adr/`, `CONTEXT.md`, `README*`, `.cursor/rules`, `.github/copilot-instructions.md`. Repo đã có `.claude/rules/` có `paths` → dừng, đề xuất `/codebase-memory:analyze` (rule còn thiếu), `/codebase-memory:audit` (rule lệch code), `/codebase-memory:learn-new` thay vì bootstrap lại.
- Stack và vùng code: `git ls-files | sed 's/.*\.//' | sort | uniq -c | sort -rn | head`; thư mục cấp 1-2 nhiều file nhất. Gợi ý glob theo stack:

  | Stack | Glob gợi ý |
  |---|---|
  | .NET (Clean Arch) | `Domain/**`, `Application/Features/**`, `Infrastructure/**`, `WebApi/**` |
  | ASP.NET WebForms | `**/*.aspx`, `**/*.ascx`, `**/*.aspx.cs`, `**/*.asmx`, `App_Code/**` |
  | Angular | `src/app/**/*.ts`, `src/app/**/*.html`, `**/*.scss` |

- Lệnh build/test/run thật: đọc file solution/csproj, `package.json` scripts, pipeline CI.

## Bước 2: Gom ứng viên

0. **Phân tích code (nguồn CHÍNH)**: chạy đúng quy trình Bước 0–3 của skill `analyze` (đọc `<skill>/../analyze/SKILL.md`): agent `codebase-memory:architect` lập bản đồ thành phần, `codebase-memory:analyst` phân tích từng thành phần, ra ứng viên luật có số liệu N/M. Các nguồn dưới chỉ bổ sung điều code không nói được (lý do, quyết định, bẫy đã gặp).
1. **Docs cũ**: tách `CLAUDE.md`/`AGENTS.md` thành từng mục; với mỗi mục kiểm đường dẫn/type còn tồn tại (`python3 <check_context.py> --full` chạy trên repo cho danh sách nhanh).
2. **Lịch sử chat**: `python3 <mine_history.py> --out <scratchpad>/lessons.md` (KHÔNG ghi vào repo: có thể chứa secret). Gom theo chủ đề; tách bài học về codebase (→ repo) với sở thích cá nhân của user (→ đề xuất ghi global CLAUDE.md/memory, không vào repo).
3. **Git log**: `git log --since=6.months -i --grep='fix\|hotfix\|revert\|review' --format='%h %s' | head -100` → chủ đề lỗi lặp lại (cùng vùng, cùng loại lỗi ≥2 lần) là ứng viên `pitfall`.
4. **Bằng chứng**: grep/LSP để tìm `path:line` cho từng ứng viên. Giao agent `codebase-memory:locator` (song song ≤ 5, mỗi agent một câu hỏi), không tự đọc hàng loạt file.

## Bước 3: Dựng đề xuất

| File | Nội dung | Giới hạn |
|---|---|---|
| `AGENTS.md` (nguồn chính, Codex đọc) | lệnh build/test/run; kiến trúc 3-5 dòng; luật cứng toàn repo; bảng "sửa vùng nào → đọc rule nào"; trỏ `docs/adr/` nếu có | ≤ 120 dòng, luật cứng ≤ 12 |
| `CLAUDE.md` | `@AGENTS.md` + 3 dòng riêng Claude (rule tự nạp theo `paths`; user sửa sai → đề xuất ghi rule, chờ duyệt; sửa rule → cập nhật `verified`) | ≤ 20 dòng |
| `.claude/rules/<thành phần>.md` | frontmatter `paths` = glob của thành phần (phải khớp ≥ 1 file: kiểm bằng `git ls-files -- ':(glob)<g>'`) + `verified: <sha>`; mỗi dòng: mệnh lệnh + lý do + (N/M) + `path:line` | mỗi file ≤ 80 dòng (dài hơn thì tách thành phần con); số file theo số thành phần |
| `docs/claude-reference/<chủ đề>.md` | chi tiết dài mà rule chỉ cần 1 dòng trỏ tới | chỉ khi cần |
| `docs/adr/NNNN-<slug>.md` | quyết định có lý do + phương án đã loại (mẫu ở skill `learn-new`) | chỉ khi docs/chat cho thấy rõ quyết định |
| `CONTEXT.md` | glossary thuật ngữ nghiệp vụ / viết tắt lặp lại | chỉ khi có ≥ 3 thuật ngữ |

Mỗi mục của `CLAUDE.md`/`AGENTS.md` cũ phải có đích: chuyển tới file nào, HOẶC "bỏ vì <lý do>" (suy ra được từ code / lỗi thời / trùng). Không âm thầm làm mất nội dung.

## Bước 4: Trình, ghi, kiểm

1. Trình: cây file sẽ tạo/sửa; nội dung từng file (file sửa thì trình diff); bảng "mục cũ → đích"; "mục bị loại + lý do"; "cần user quyết"; "nên có test" (nếu có).
2. Chờ user duyệt (có thể từng phần). Chưa duyệt thì không đụng file.
3. Ghi; đặt `verified:` = `git rev-parse --short HEAD`.
4. `python3 <check_context.py> --full` phải ra 0 lỗi (sửa lỗi do mình gây ra); `--metrics` để báo token luôn nạp trước/sau.
5. Báo: file đã tạo/sửa, số rule, token luôn nạp trước → sau, mục chờ user. Nhắc user tự commit (và chỉ commit file đã được trỏ tới).
