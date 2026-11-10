---
name: guide
description: Hướng dẫn plugin codebase-memory (lệnh /codebase-memory:bootstrap, :analyze, :learn-new, :audit, :guide; agent architect, analyst, locator; hook SessionStart; script check_context, mine_history) — workflow, thành phần nào làm gì, và kiểm trạng thái repo để gợi ý bước tiếp theo. LUÔN gọi skill này trước khi trả lời bất kỳ câu hỏi nào về plugin codebase-memory (có skill/lệnh gì, dùng thế nào, khác nhau ra sao) hoặc "bước tiếp theo / giờ nên làm gì" với context, rule của repo. bootstrap, analyze, audit là lệnh chỉ user gõ nên không hiện trong danh sách skill.
argument-hint: "[câu hỏi, vd: bước tiếp theo là gì?]"
---

# guide

Trả lời câu hỏi của user về plugin trước. Hỏi "bước tiếp theo" (hoặc không hỏi gì cụ thể) → chạy phần **Chẩn đoán** rồi gợi ý ĐÚNG 1 việc nên làm ngay + lệnh cụ thể. Chỉ đọc, không sửa file.
Script (tính từ thư mục skill này): `<skill>/../../scripts/check_context.py`, `<skill>/../../scripts/mine_history.py`.

## Plugin giải quyết gì

Mỗi phiên Claude Code mới không nhớ gì về repo. Plugin giữ tri thức dài hạn trong file của repo (commit được, team dùng chung) và chỉ nạp phần cần lúc cần. Nguyên tắc: chỉ ghi điều KHÔNG suy ra được từ code (lý do, bẫy, quyết định, điều Claude từng làm sai), mỗi điều có bằng chứng `path:line`, và được máy kiểm còn khớp code hay không.

## Tri thức nằm ở đâu

| File | Nạp khi nào | Chứa gì |
|---|---|---|
| `AGENTS.md` | mọi phiên (qua `@AGENTS.md` trong `CLAUDE.md`; Codex đọc trực tiếp) | lệnh build/test, kiến trúc vài dòng, luật cứng toàn repo, bảng "sửa vùng nào → đọc rule nào" |
| `CLAUDE.md` | mọi phiên | `@AGENTS.md` + vài dòng riêng Claude |
| `.claude/rules/<vùng>.md` | tự động khi Claude đọc/sửa file khớp `paths:` | convention, bẫy của một vùng code; `verified: <sha>` = commit lúc đối chiếu gần nhất |
| `docs/claude-reference/*.md` | khi rule trỏ tới | chi tiết dài |
| `docs/adr/NNNN-*.md` | khi rule/AGENTS trỏ tới | quyết định + phương án đã loại (để Claude không đề xuất lại) |
| `CONTEXT.md` | khi cần | thuật ngữ nghiệp vụ |
| auto-memory / global `CLAUDE.md` | mọi phiên | sở thích cá nhân của user (KHÔNG ghi vào repo) |

## Thành phần

| Thành phần | Kích hoạt | Dùng để |
|---|---|---|
| Hook SessionStart | tự động khi mở phiên | chạy `check_context.py --session-start`: im lặng nếu context khớp code; lệch thì in ≤ 5 dòng cảnh báo (kể cả docs trỏ tới file gitignored/chưa track) |
| Hook Stop | tự động cuối mỗi lượt, chỉ ở repo đã có `.claude/rules` có `paths` | `stop_capture.py`: tin cuối của user khớp mẫu sửa sai (cùng regex `mine_history`) → chặn kết thúc lượt 1 lần/phiên, Claude đề xuất `learn-new` (không tự ghi). Tắt: env `CODEBASE_MEMORY_STOP_CAPTURE=0` |
| `/codebase-memory:bootstrap` | user gõ, 1 lần mỗi repo | dựng bộ file trên từ docs cũ + lịch sử chat + git log; trình đề xuất, duyệt rồi mới ghi |
| `/codebase-memory:learn-new` | Claude tự đề xuất khi user sửa sai / nói "nhớ", "lần sau"; hoặc user gõ | ghi 1 bài học vào đúng file (rule, AGENTS, ADR, CONTEXT); qua 3 cổng: đáng nhớ, có bằng chứng, không máy hóa được |
| `/codebase-memory:analyze` | user gõ sau bootstrap hoặc khi rule còn thiếu; `--deep` dùng opus | phân tích CODE: agent architect lập bản đồ thành phần → agent analyst (song song) phân tích từng thành phần → rule chi tiết có số liệu N/M (convention, anti-pattern như "không tự trim, pipeline đã trim"); kết quả trung gian ở `.git/codebase-memory/analysis/` |
| `/codebase-memory:audit` | user gõ khi hook cảnh báo, sau đợt đổi code lớn, hoặc hằng tháng | sửa mục lỗi thời (đường dẫn, tên type, glob, rule có code đã đổi), in thước đo |
| agent `codebase-memory:architect` | skill analyze/bootstrap gọi | bản đồ kiến trúc hiện có: thành phần, nhiệm vụ, glob, file then chốt, luồng request |
| agent `codebase-memory:analyst` | skill analyze/bootstrap gọi, 1 agent/thành phần | quét toàn bộ file của thành phần, ra ứng viên luật (N/M, ví dụ, phản ví dụ) + đánh giá tốt / cần cải thiện |
| agent `codebase-memory:locator` | skill analyze (kiểm lại từng luật), learn-new (tìm bằng chứng), audit (tìm đường dẫn/tên mới); hoặc bất kỳ lúc nào cần tìm | tìm định nghĩa/chỗ dùng, trả `path:line` (ưu tiên LSP, thiếu thì grep) |
| `/codebase-memory:guide` | user hỏi | skill này |
| `check_context.py` | hook/skill gọi; chạy tay được | `--full` liệt kê lỗi `file:line`; `--metrics` token luôn nạp + số commit kể từ `verified` của từng rule |
| `mine_history.py` | skill gọi; chạy tay được | trích những lần user sửa/dạy lại Claude từ transcript; `--count` tỉ lệ sửa sai theo tuần (giảm dần = Claude đang "học") |

## Workflow

1. **Lần đầu trong repo**: `/codebase-memory:bootstrap` (đã gồm phân tích code) → duyệt → tự commit các file context. Repo đã có rule nhưng rule mỏng (chủ yếu từ docs cũ) → `/codebase-memory:analyze`.
2. **Hằng ngày**: không cần làm gì — rule tự nạp theo vùng code; hook chỉ lên tiếng khi context lệch.
3. **Khi sửa Claude / giải thích convention**: hook Stop nhắc Claude đề xuất `learn-new` (hoặc gõ `/codebase-memory:learn-new <bài học>`), duyệt diff.
4. **Khi hook cảnh báo, sau refactor lớn, hoặc hằng tháng**: `/codebase-memory:audit`.

## Chẩn đoán (để gợi ý bước tiếp theo)

Chạy theo thứ tự, dừng ở điều kiện ĐẦU TIÊN khớp:

| # | Kiểm | Khớp thì gợi ý |
|---|---|---|
| 1 | `git rev-parse --show-toplevel` lỗi | plugin chỉ chạy trong git repo → mở Claude Code ở thư mục repo |
| 2 | không có file `.claude/rules/*.md` nào chứa dòng `paths:` | `/codebase-memory:bootstrap` (repo chưa có bộ context) |
| 3 | `python3 <check_context.py> --full` có lỗi | `/codebase-memory:audit` (nêu số lỗi + 2-3 lỗi đầu) |
| 3b | chưa có thư mục `$(git rev-parse --absolute-git-dir)/codebase-memory/analysis/` (rule chưa từng được dựng từ phân tích code) | `/codebase-memory:analyze` (nói rõ: tốn nhiều agent, chọn thành phần ở bước 1) |
| 4 | `--metrics`: rule nào có ≥ 20 commit sau `verified` | `/codebase-memory:audit` (rule đó lâu chưa được đối chiếu) |
| 5 | `--metrics`: tổng token luôn nạp > 3000 | rút gọn `AGENTS.md`: chuyển chi tiết theo vùng sang `.claude/rules/` |
| 6 | file context (`AGENTS.md`, `CLAUDE.md`, `.claude/rules/`, `docs/adr/`, `docs/claude-reference/`) có thay đổi chưa commit (`git status --short -- <các file đó>`) | rà diff rồi commit (Claude không tự commit); chỉ commit file được docs trỏ tới, không gom file user giữ local |
| 7 | `python3 <mine_history.py> --since <7 ngày trước>` có tin sửa sai mà nội dung chưa có trong `AGENTS.md`/`.claude/rules/` | `/codebase-memory:learn-new <bài học>` cho từng mục (liệt kê tối đa 3) |
| 8 | không gì khớp | không cần làm gì; nhắc: khi sửa Claude thì nói "nhớ ..." để kích `learn-new` |

Trả lời: kết luận 1 câu (trạng thái repo) → việc nên làm ngay + lệnh → lý do 1 dòng (kết quả kiểm). Không chạy skill khác thay user; `bootstrap` và `audit` user phải tự gõ.

## Sự cố thường gặp

- Rule không được nạp: rule chỉ nạp khi Claude Read/Edit file khớp `paths` (lúc lập kế hoạch thì đọc theo bảng trong `AGENTS.md`); glob sai thì `check_context --full` báo "glob không khớp file nào".
- Hook Stop nhắc nhầm (câu chỉ là làm rõ yêu cầu): Claude tự bỏ qua; mỗi phiên nhắc tối đa 1 lần; tắt hẳn bằng `CODEBASE_MEMORY_STOP_CAPTURE=0` trong `env` của settings.json.
- Hook im lặng: nghĩa là 0 lỗi (kết quả cache theo HEAD + docs ở `.git/codebase-memory.cache`).
- Báo nhầm tên type thuộc thư viện ngoài/hệ thống khác: thêm `<!-- ctx-ignore -->` cuối dòng.
- Sửa mã nguồn plugin mà không thấy tác dụng: Claude Code chạy bản copy trong plugin cache → `claude plugin marketplace update <marketplace>` rồi `claude plugin update codebase-memory@<marketplace>` và mở phiên mới.
- Docs chỉ được trỏ tới file sẽ được commit (không trỏ file gitignored/untracked/giữ local).
