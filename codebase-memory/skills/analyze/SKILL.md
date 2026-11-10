---
name: analyze
description: Phân tích code của repo bằng agent architect + analyst để rút ra rule chi tiết (convention, kiến trúc, anti-pattern có số liệu N/M) giúp AI sinh code không phá convention; trình đề xuất bổ sung .claude/rules, duyệt rồi ghi. Dùng sau bootstrap hoặc khi rule còn thiếu.
disable-model-invocation: true
argument-hint: "[thành phần hoặc glob, bỏ trống = cả repo] [--deep]"
---

# analyze

Nguồn rule chính là CODE, không phải docs cũ. Main thread điều phối (subagent không gọi được subagent). Không commit.
Chạy NGAY TRONG phiên của user bằng tool Agent (subagent, `run_in_background: true` để chạy song song) cho user theo dõi từng agent. KHÔNG chạy qua `claude -p`/phiên headless hay lệnh Bash nền. Agent của plugin chưa có trong phiên (vừa cài, chưa mở phiên mới) → dùng `general-purpose` với nguyên văn hướng dẫn trong `<skill>/../../agents/<tên>.md` làm prompt, giữ đúng model của agent đó.
Agent của plugin: `codebase-memory:architect` (bản đồ kiến trúc), `codebase-memory:analyst` (phân tích 1 thành phần), `codebase-memory:locator` (tìm file/symbol).
Script: `<skill>/../../scripts/check_context.py`.

## Bước 0: Chỗ làm việc

`D=$(git rev-parse --absolute-git-dir)/codebase-memory/analysis/$(date +%F)-$(git rev-parse --short HEAD)`; `mkdir -p $D`. Mọi kết quả trung gian ghi vào `$D` (nằm trong `.git` → không bao giờ bị commit, vẫn còn cho phiên sau). Không ghi kết quả trung gian vào repo.

## Bước 1: Bản đồ kiến trúc

- Đã có `$D/architecture.md` (cùng HEAD) → dùng lại. Không thì gọi `codebase-memory:architect` (brief: đường dẫn repo; phạm vi nếu user truyền thành phần/glob) và ghi output nguyên văn vào `$D/architecture.md`.
- Trình user: danh sách thành phần (tên, glob, số file) + số analyst sẽ chạy + model (`sonnet`; `--deep` → `opus`, đắt hơn nhiều). User chọn thành phần nào phân tích (mặc định: tất cả, thành phần xuyên suốt trước). Chưa chọn thì không chạy bước 2.

## Bước 2: Phân tích từng thành phần

- Mỗi thành phần một `codebase-memory:analyst`. Gọi song song tối đa 5 agent trong CÙNG một lượt; xong đợt này mới tới đợt sau.
- Brief = nguyên văn mục thành phần trong `$D/architecture.md` + đường dẫn repo + "luồng request điển hình" + đường dẫn file `$D/architecture.md`. Truyền `model: "opus"` nếu `--deep`.
- Ghi output nguyên văn của từng agent vào `$D/C<n>-<slug>.md`. Agent lỗi/thiếu số liệu → chạy lại 1 lần với brief nói rõ phần thiếu; vẫn thiếu thì ghi nhận, không bịa.

## Bước 3: Tổng hợp thành rule (main làm)

1. Đọc `AGENTS.md`, `CLAUDE.md`, `.claude/rules/*.md` hiện có.
2. Lấy ứng viên độ tin cậy **cao** và **trung bình**. Bỏ: mô tả không phải mệnh lệnh; điều trùng rule đã có (giữ bản có số liệu tốt hơn); "cần cải thiện" (không phải luật).
3. Kiểm lại mỗi luật bằng `codebase-memory:locator` (analyst có thể sai): mỗi locator một nhóm luật cùng thành phần, ≤ 5 locator song song mỗi lượt. Brief: luật + `path:line` ví dụ đúng và phản ví dụ analyst đưa; yêu cầu xác nhận từng `path:line` còn đúng và tìm thêm phản ví dụ. Sai → bỏ; lệch số liệu → sửa N/M.
4. Xếp vào file:
   - Luật áp dụng toàn repo, ngắn → mục luật cứng trong `AGENTS.md` (giữ ≤ 15 luật).
   - Luật theo thành phần → `.claude/rules/<thành phần>.md`, `paths:` = glob của thành phần (kiểm khớp ≥ 1 file). Rule đã có cho vùng đó → bổ sung vào đó.
   - Mỗi dòng: `- <mệnh lệnh> — <lý do/cơ chế> (N/M). Đúng: \`path:line\``. Anti-pattern viết dạng "KHÔNG ... vì <cơ chế xuyên suốt> đã làm (\`path:line\`)".
   - Rule ≤ 80 dòng; dài hơn → tách theo thành phần con. Chi tiết dài → `docs/claude-reference/`.
5. Mâu thuẫn với rule cũ → không tự chọn, đưa vào "cần user quyết".
6. Ghi `$D/proposal.md` (đề xuất) và `$D/improvements.md` (gom mục "cần cải thiện" của mọi analyst).

## Bước 4: Trình, ghi, kiểm

1. Trình: theo từng file rule — dòng thêm/sửa (diff) kèm N/M; "không nhất quán — cần user chọn chuẩn"; "cần user quyết"; tóm tắt `improvements.md` (top 10, có `path:line`); "máy hóa được" (gợi ý test/analyzer).
2. Chờ user duyệt (có thể từng file). Chưa duyệt thì không đụng file repo.
3. Ghi phần đã duyệt; `verified:` = `git rev-parse --short HEAD` cho rule đã sửa; cập nhật bảng "sửa vùng nào → đọc rule nào" trong `AGENTS.md` nếu thêm rule mới.
4. `python3 <check_context.py> --full` phải 0 lỗi; `--metrics` báo token luôn nạp.
5. Báo: số thành phần đã phân tích / số luật thêm theo file / số mục chờ user / đường dẫn `$D` để xem báo cáo đầy đủ. Không commit; chỉ đề xuất commit file được docs trỏ tới.
