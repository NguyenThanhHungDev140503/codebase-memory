---
name: learn-new
description: Ghi một bài học về codebase hiện tại (convention, kiến trúc, bẫy, quyết định, thuật ngữ) vào đúng file context của repo để các phiên sau tự biết. Dùng khi user sửa sai cách làm của Claude, giải thích lý do/convention dự án, hoặc nói "nhớ", "lần sau", "từ giờ", "luôn/đừng ... trong dự án này", hoặc gọi /learn-new. Không dùng cho sở thích cá nhân của user (văn phong trả lời) — cái đó thuộc auto-memory.
argument-hint: "<bài học, vd: QueryHandler không được dùng IWriteUnitOfWork>"
---

# learn-new

Biến một bài học thành tri thức bền vững trong repo, nạp tự động đúng lúc. Chỉ ĐỀ XUẤT; ghi file sau khi user đồng ý. Không commit.
Agent của plugin chưa có trong phiên (vừa cài) → dùng `general-purpose` với nguyên văn `<skill>/../../agents/locator.md` làm prompt, giữ model; chạy bằng tool Agent trong phiên, không `claude -p`.

## Cổng nạp (bài học phải qua cả 3, không qua thì nói lý do và dừng)

1. **Đáng nhớ**: Claude đã làm sai điều này, HOẶC không suy ra được từ code lân cận (lý do, ràng buộc ngoài, bẫy runtime, quyết định), HOẶC là convention trên nhiều file mà AI chỉ đọc vài file sẽ phá (kèm số liệu N/M file tuân thủ). Cấm ghi: cây thư mục, kiến thức framework phổ thông, mô tả không phải mệnh lệnh.
2. **Có bằng chứng**: tìm `path:line` trong file đã track (`git ls-files`) chứng minh hoặc minh họa — giao agent `codebase-memory:locator` (trả `path:line`, ưu tiên LSP; bài học về convention nhiều file thì yêu cầu thêm số file tuân thủ / vi phạm). Không tìm được → hỏi user nguồn (ticket, ADR, người quyết định) trước khi ghi.
3. **Máy hóa được thì nói**: nếu kiểm được bằng test (reflection, architecture test) hoặc analyzer → gợi ý viết test; vẫn ghi rule bằng chữ (test có thể chỉ ở local, rule không được trỏ tới test chưa commit).

## Các bước

1. **Phân loại** → chọn đích:

   | Loại | Đích |
   |---|---|
   | convention / pitfall / kiến trúc của MỘT vùng code | `.claude/rules/<vùng>.md` (có `paths`) |
   | luật áp dụng toàn repo | 1 dòng trong mục luật cứng của `AGENTS.md` (không có thì `CLAUDE.md`) |
   | quyết định có lý do, có phương án bị loại | `docs/adr/NNNN-<slug>.md` (NNNN = số lớn nhất + 1) |
   | thuật ngữ nghiệp vụ / viết tắt | `CONTEXT.md` (mục Glossary) |
   | sở thích cá nhân user | KHÔNG ghi vào repo → auto-memory |

2. **Tìm chỗ đã có**: grep bài học trong `AGENTS.md`, `CLAUDE.md`, `.claude/rules/`, `docs/adr/`, `CONTEXT.md`.
   - Đã có và đúng → báo "đã có ở `file:line`", dừng.
   - Đã có nhưng mâu thuẫn → trình cả hai, hỏi user cái nào đúng; không tự chọn.
3. **Chọn file rule**: rule có `paths` khớp file chứa bằng chứng. Không có → tạo rule mới theo mẫu dưới, glob hẹp nhất phủ vùng đó, và thêm 1 dòng vào bảng chỉ mục rule trong `AGENTS.md` (hoặc `CLAUDE.md`).
4. **Viết 1 dòng** (tối đa 2): mệnh lệnh rõ + lý do ngắn + bằng chứng `path:line`. Không dán code. Rule vượt 40 dòng → chuyển chi tiết sang `docs/claude-reference/<chủ đề>.md` và để lại 1 dòng trỏ.
5. **Trình diff** (file đích + nội dung thêm/sửa) và hỏi user: ghi / sửa lại / bỏ. Chưa có "ghi" thì không đụng file.
6. **Ghi**, rồi:
   - đặt `verified:` của rule vừa sửa = `git rev-parse --short HEAD`;
   - chạy `python3 <thư mục skill này>/../../scripts/check_context.py --full`; có lỗi do mình gây ra thì sửa ngay.
7. Báo: file đã đổi, dòng đã thêm, kết quả check. KHÔNG commit.

## Mẫu

Rule mới (`.claude/rules/<vùng>.md`):
```markdown
---
paths: ["<glob hẹp nhất>"]
verified: <sha ngắn>
---
# <Tên vùng>

- <Mệnh lệnh> — <lý do>. Ví dụ: `<path>:<line>`
```

ADR (`docs/adr/NNNN-<slug>.md`):
```markdown
# NNNN. <Quyết định>
Trạng thái: Accepted (<YYYY-MM-DD>) | Thay thế: <ADR cũ nếu có>
## Bối cảnh
## Quyết định
## Phương án đã loại và lý do
## Hệ quả
```
ADR không sửa nội dung cũ: quyết định đổi thì tạo ADR mới và ghi "Superseded by NNNN" vào ADR cũ.
