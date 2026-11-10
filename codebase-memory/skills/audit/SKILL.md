---
name: audit
description: Rà và sửa context lỗi thời của repo (CLAUDE.md, AGENTS.md, .claude/rules, ADR, docs/claude-reference) so với code hiện tại, rồi in thước đo. Chạy khi hook SessionStart báo context lỗi thời, sau đợt đổi code lớn, hoặc định kỳ.
disable-model-invocation: true
argument-hint: "[--metrics-only]"
---

# audit

Đưa context của repo về khớp code, có bằng chứng, có người duyệt. Không commit.
Agent của plugin chưa có trong phiên (vừa cài) → dùng `general-purpose` với nguyên văn `<skill>/../../agents/locator.md` làm prompt, giữ model; chạy bằng tool Agent trong phiên, không `claude -p`.

Script (đường dẫn tính từ thư mục skill này):
- `python3 <skill>/../../scripts/check_context.py --full` — danh sách `file:line: lý do`
- `python3 <skill>/../../scripts/check_context.py --metrics` — token luôn nạp + tuổi `verified` từng rule
- `python3 <skill>/../../scripts/mine_history.py --count` — số lần user sửa sai theo tuần

## Bước 1: Đo

Chạy cả 3 lệnh. Có `--metrics-only` hoặc `--full` ra 0 lỗi → chỉ báo thước đo (bước 4) và dừng.

## Bước 2: Chẩn đoán từng finding (chỉ đọc, chưa sửa)

| Finding | Cách tìm sự thật | Đề xuất |
|---|---|---|
| đường dẫn không tồn tại `X` | `git log --format= --name-status -M --diff-filter=RD -- X` (bị đổi tên/xóa?), `git ls-files` lọc theo basename | Đúng 1 ứng viên → đổi đường dẫn. Bị xóa → xóa/viết lại câu chứa nó. Nhiều ứng viên → hỏi user |
| `X:N` vượt quá số dòng | mở file, tìm lại symbol/nội dung câu đó đang trỏ | Cập nhật số dòng mới |
| không tìm thấy `T` trong code | `git log -S T --oneline -- . ':!*.md'` (bị xóa/đổi tên lúc nào), grep tên gần giống (không phân biệt hoa thường, bỏ tiền/hậu tố) | Đổi tên → sửa tên. Đã xóa → xóa hoặc viết lại khẳng định. Tên ngoài repo (thư viện, framework, hệ thống khác) → thêm `<!-- ctx-ignore -->` cuối dòng. Test/class "được nói là có" nhưng chưa từng có → ghi rõ "chưa có (TODO)", không giả vờ có |
| glob `G` không khớp file nào | code vùng đó chuyển đi đâu (`git log --name-status -M`) | Sửa glob |
| N file trong paths đã đổi từ verified `S` | `git diff --stat S..HEAD -- <paths>` rồi đọc hunk liên quan tới từng gạch đầu dòng của rule | Mọi gạch đầu dòng còn đúng → chỉ nâng `verified`. Có dòng sai → sửa dòng đó (kèm `path:line` mới) |

Việc "tìm đường dẫn/tên mới, tìm chỗ symbol đang nằm" giao agent `codebase-memory:locator` (≤ 5 song song mỗi lượt, mỗi agent một nhóm finding cùng file docs; brief: finding + câu hỏi cụ thể, vd "`OrderService` đổi tên thành gì, ở đâu?"); main chỉ đọc kết quả `path:line` rồi quyết.

Quy tắc: mỗi khẳng định giữ lại phải còn bằng chứng trong code. Không thêm kiến thức mới trong lúc audit (việc đó của `learn-new`). Không đoán: không chắc thì đưa vào mục "cần user quyết".

## Bước 3: Trình, ghi, kiểm lại

1. Trình MỘT bản tổng hợp: mỗi file → dòng cũ → dòng mới → lý do/bằng chứng; cuối cùng là mục "cần user quyết".
2. Chờ user duyệt (có thể duyệt từng phần). Chưa duyệt thì không đụng file.
3. Ghi phần đã duyệt; với rule đã rà xong đặt `verified:` = `git rev-parse --short HEAD`.
4. Chạy lại `--full`. Còn lỗi do mình gây ra → sửa; còn lỗi chờ user quyết → liệt kê.

## Bước 4: Báo cáo

- Kết luận 1 dòng: còn bao nhiêu lỗi (mục tiêu 0).
- Đã sửa: số mục theo loại (đường dẫn, số dòng, tên, glob, verified).
- Thước đo: token luôn nạp (~); rule có nhiều commit sau `verified` nhất; bảng `mine_history --count` (xu hướng tỉ lệ sửa sai theo tuần — giảm dần nghĩa là Claude đang "học").
- Không commit; nhắc user tự commit kèm code liên quan.
