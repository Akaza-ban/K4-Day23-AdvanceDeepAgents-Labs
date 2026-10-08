# Mẫu báo cáo (REPORT_TEMPLATE)

Báo cáo do **lead agent** viết vào `/tmp/work/report/report.md` trong sandbox. Mẫu này là cấu trúc bắt buộc; hãy đưa nó vào prompt của lead (xem `GUIDE.md` Phần 2). Báo cáo được viết bằng tiếng Anh (nguồn là bài báo tiếng Anh); tiêu đề các phần giữ đúng như dưới đây để `check_citations.py` và người chấm tìm được.

## Cấu trúc

```markdown
# <Title of the survey>

## TL;DR
- 3-5 bullets: the main findings, each with a citation [n].

## Background
Short definition of the topic and why it matters now. Cite foundational work [n].

## <Theme 1: e.g. "Latent dynamics models">
Synthesise across papers: what approaches exist, how they differ, what the evidence says.
Compare, do not list one paper per paragraph. Every non-obvious claim carries a citation [n].

## <Theme 2> ... <Theme k>
(3 to 6 themes in total)

## Trends and open problems
What is changing in the last two years, what is unsolved, which results are still disputed. [n]

## References
[1] Title. arxiv. https://arxiv.org/abs/XXXX.XXXXX (2025-01-02)
[2] Title. hf-search. https://huggingface.co/papers/XXXX.XXXXX (2025-03-04)
[3] Title. web. https://example.org/page (2025-02-10)
```

## Quy tắc trích dẫn

> Phần `## References` **không do LLM viết tay**: lead viết thân báo cáo rồi chạy `finalize_citations.py` (có sẵn) để sinh nó đúng quy tắc 3 dưới đây.

1. Mọi khẳng định không hiển nhiên phải có trích dẫn dạng `[n]`.
2. Mọi `[n]` phải có trong `sources.json` (cùng số `n`); mọi mục trong `sources.json` phải được trích dẫn ít nhất một lần trong phần thân.
3. Danh sách `## References` đặt ở **cuối** báo cáo: **một dòng cho mỗi nguồn**, dạng `[n] Tiêu đề. <source>. URL (ngày)`, chứa **đúng một URL** và URL đó bằng `url` trong `sources.json`. Không gộp nhiều nguồn dưới một số.
4. Không có khẳng định hay số liệu nào không có trong ghi chú của researcher. Không bịa nguồn, URL, tên tác giả, số liệu.
5. `source` là một trong: `arxiv`, `hf-daily`, `hf-search`, `web`.

## `sources.json`

Mảng JSON, mỗi nguồn một mục, đánh số từ 1, không trùng URL:

```json
[
  {"n": 1, "id": "2501.00001", "url": "https://arxiv.org/abs/2501.00001", "title": "…", "date": "2025-01-02", "source": "arxiv"}
]
```

## Tự kiểm tra

```bash
python3 check_citations.py reports/<slug>.md reports/<slug>.sources.json
```

Phải in `OK: N sources, all citations resolve`.
