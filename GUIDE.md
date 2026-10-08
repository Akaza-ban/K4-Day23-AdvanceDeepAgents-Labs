# Hướng dẫn làm bài (GUIDE)

Các "TODO n" trong mã khớp với các mục dưới đây. Tài liệu gốc về sandbox: https://docs.langchain.com/oss/python/deepagents/sandboxes

## 0. Khái niệm nền

- **Deep Agent** = `create_deep_agent(...)`: agent có sẵn công cụ tệp (`ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`), công cụ `task` để giao việc cho **subagent**, tự động tóm tắt ngữ cảnh khi dài, và nạp bộ nhớ/skill. **Lưu ý:** ở `deepagents==0.7.21` công cụ lập kế hoạch `write_todos` **không** có sẵn: hãy thêm `TodoListMiddleware()` (từ `langchain.agents.middleware`) qua tham số `middleware=[...]` của `create_deep_agent`.
- **Backend** là nơi agent làm việc với tệp. Backend kiểu **sandbox** (ở đây là Daytona) thêm công cụ `execute` để chạy lệnh shell trong môi trường cô lập.
- **Subagent chỉ thấy nội dung tin nhắn mà lead gửi cho nó**, không thấy hội thoại của lead. Vì vậy tin nhắn uỷ quyền phải mang **đủ ngữ cảnh**: chủ đề, câu hỏi con, đường dẫn tệp ghi chú, định dạng ghi chú.
- **Mô hình an toàn** (theo tài liệu): sandbox không ngăn prompt injection và không ngăn việc đẩy dữ liệu ra mạng, và **không bao giờ đưa bí mật vào sandbox**. Do đó: công cụ gọi mạng (arXiv, Hugging Face, Exa) chạy ở **host** dưới dạng tool của LangChain, khóa API ở lại host; sandbox chỉ là chỗ lưu tệp và chạy mã phân tích/kiểm tra.
- Cách các tệp liên hệ với nhau: `research.py` mở sandbox, tải `check_citations.py` lên, tạo lead agent từ `agents.py` (nó dùng các tool trong `tools.py`), chạy, rồi tải báo cáo về.

## 1. `tools.py` - công cụ nguồn dữ liệu (TODO 1-5)

Quy ước chung: công cụ trả về **chuỗi**; không bao giờ ném ngoại lệ; rỗng thì `NO RESULTS`; hỏng sau khi đã retry thì `ERROR: ...`. Docstring của công cụ là mô tả mà LLM đọc để chọn công cụ, hãy viết chính xác. Giữ bản ghi gọn (cắt `summary` khoảng 600 ký tự) để không làm đầy ngữ cảnh.

### 1.1 Retry và backoff (TODO 1)

Các nguồn bị giới hạn tốc độ và thỉnh thoảng lỗi tạm thời. `with_retry(fn)` gọi `fn()`, và khi `fn` ném `RetryableError` thì chờ rồi gọi lại.

- Lỗi nên retry: HTTP `429`, `500`, `502`, `503`, `504`, và lỗi mạng (`httpx.TransportError`: timeout, ngắt kết nối).
- Thời gian chờ: nếu server gửi header `Retry-After` (số giây) thì dùng nó; nếu không thì backoff lũy thừa `base * 2**attempt`, chặn trên `cap`, **cộng jitter ngẫu nhiên** để nhiều client không đập server cùng lúc.
- Lần thử cuối thất bại: ném lại lỗi, **không ngủ thêm**.
- Lỗi khác (ví dụ lỗi lập trình) **không** retry: để nó nổi lên.
- Công cụ bọc `with_retry` quanh mọi lời gọi mạng rồi đổi mọi ngoại lệ còn lại thành chuỗi `ERROR: ...`.

### 1.2 arXiv (TODO 2)

- Endpoint: `https://export.arxiv.org/api/query`. **Chỉ dùng HTTPS**: gọi HTTP sẽ bị `301`.
- Tham số: `search_query` (ví dụ `all:world AND all:model`), `sortBy=submittedDate`, `sortOrder=descending`, `max_results`, `start`.
- Kết quả là **Atom XML** (namespace `http://www.w3.org/2005/Atom`). Mỗi `<entry>` có `<id>` (URL dạng `http://arxiv.org/abs/2501.00001v1`), `<published>`, `<title>`, `<summary>`. Tiêu đề và tóm tắt có xuống dòng và khoảng trắng thừa: chuẩn hóa chúng.
- Giữ **ít nhất 3 giây** giữa hai lời gọi arXiv (quy ước sử dụng API của họ).
- Chuẩn hóa bản ghi: `id` bỏ hậu tố phiên bản (`2501.00001v1` → `2501.00001`) và `url = https://arxiv.org/abs/<id>` (HTTPS, không có `vN`), khớp với `REPORT_TEMPLATE.md`.
- arXiv cũng trả **HTTP 429** khi nhiều người dùng chung một địa chỉ IP (cả lớp sau một mạng trường): cho arXiv `cap` dài hơn (ví dụ 60 giây) và vài lần thử nữa thay vì bỏ cuộc sớm.
- Truy vấn là input do LLM sinh ra: chỉ giữ các ký tự chữ/số/gạch nối để dấu nháy, dấu hai chấm hay `AND/OR` thừa không làm hỏng truy vấn; không còn từ nào thì trả `NO RESULTS` mà không gọi mạng.

### 1.3 Hugging Face (TODO 3)

- **Daily Papers** `https://huggingface.co/api/daily_papers` (tham số `limit`, `date=YYYY-MM-DD`): danh sách mục dạng `{"paper": {...}, "title", "summary", "publishedAt", ...}`. Trong `paper` có `id`, `title`, `summary`, `upvotes`, `githubRepo`, `githubStars`, `publishedAt`. Đây là tín hiệu "trending", **không có tìm theo chủ đề**: lọc theo từ khóa ở phía client và sắp theo `upvotes`.
- **Search** `https://huggingface.co/api/papers/search?q=<chủ đề>` (tham số `limit`): cùng dạng mục, thêm `ai_summary` và `ai_keywords`. Ưu tiên `ai_summary` (ngắn, gọn) khi có.
- Bản ghi trả về: `{id, url, published, title, summary, upvotes, github, stars}` với `url = https://huggingface.co/papers/<id>`. Bỏ qua mục không có `paper.id`.

### 1.4 Exa MCP qua HTTP thuần (TODO 4)

Không cần thư viện MCP: một lời gọi công cụ MCP chỉ là một JSON-RPC qua HTTP POST.

```bash
curl -s -X POST https://mcp.exa.ai/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"web_search_exa","arguments":{"query":"survey paper on world models","objective":"find survey papers","numResults":2}}}'
```

- Header `Accept` phải có `text/event-stream`. Phản hồi là **server-sent events**: tìm dòng bắt đầu bằng `data:` rồi `json.loads` phần còn lại. Nội dung văn bản nằm ở `result.content[].text` (các phần tử có `type == "text"`).
- Công cụ: `web_search_exa` (bắt buộc `query`, `objective`; tùy chọn `numResults`) và `web_fetch_exa` (bắt buộc `urls`, **một mảng**). Xem danh sách bằng `{"jsonrpc":"2.0","id":1,"method":"tools/list"}`.
- Lỗi JSON-RPC có khóa `error` thay cho `result`: biến nó thành lỗi.
- **Cẩn thận với giới hạn tốc độ.** Bản miễn phí không trả HTTP 429: nó trả **HTTP 200** kèm một thông báo trong văn bản, và đặt cờ trong `result._meta`. Hãy chạy `curl` ở trên vài lần liên tiếp và nhìn kỹ `result._meta`. Nếu bạn không phát hiện ra, agent sẽ coi thông báo giới hạn tốc độ là "nội dung trang" và nghiên cứu sai. Phát hiện cờ đó và **retry**. Khi một người dùng thì thường hết sau chừng 20 giây; khi **cả lớp dùng chung một IP** thì có thể kéo dài nhiều phút, vượt mọi số lần retry hợp lý — vì vậy **hãy lấy `EXA_API_KEY` miễn phí** trước buổi lab, và cho Exa `cap` dài (ví dụ 60 giây) với đủ số lần thử.
- Khóa tùy chọn `EXA_API_KEY` được gắn vào URL của endpoint dưới dạng tham số truy vấn (hiện là `exaApiKey`, ví dụ `https://mcp.exa.ai/mcp?exaApiKey=<khóa>`; chính thông báo giới hạn tốc độ của Exa cũng nêu tên này — kiểm lại trên https://dashboard.exa.ai/api-keys nếu nó đổi). Hệ quả: **khóa có thể lọt vào văn bản của ngoại lệ** (thông báo lỗi `httpx` chứa cả URL). Hãy che khóa trước khi trả `ERROR: ...` cho agent.
- `web_fetch` cắt nội dung còn khoảng 12000 ký tự.

### 1.5 Đăng ký công cụ (TODO 5)

`SOURCE_TOOLS` đã được liệt kê sẵn; chỉ cần công cụ của bạn đúng tên. Kiểm tra từng cái bằng `python tools.py`.

## 2. `agents.py` - prompt, subagent, lead agent (TODO 1-4)

Quy ước không gian làm việc (cho sẵn trong tệp), tất cả là đường dẫn tuyệt đối trong sandbox:

| Hằng số | Đường dẫn | Nội dung |
|---|---|---|
| `NOTES_DIR` | `/tmp/work/research/notes/` | `<NN>-<slug>.md` do researcher ghi |
| `SOURCES_PATH` | `/tmp/work/research/sources.json` | mảng `{n, id, url, title, date, source}` |
| `VALIDATOR_PATH` | `/tmp/work/research/check_citations.py` | do `research.py` tải lên |
| `REPORT_PATH` | `/tmp/work/report/report.md` | báo cáo cuối |

`source` thuộc `arxiv`, `hf-daily`, `hf-search`, `web`. `source` là **công cụ đã trả về nguồn đó**, không phải tên miền: một bài arXiv tìm thấy qua `web_search` có `source` là `web`. `url` phải khớp với họ: `arxiv` → `https://arxiv.org/abs/<id>`, `hf-daily`/`hf-search` → `https://huggingface.co/papers/<id>`; người chấm đối chiếu điều này.

**Prompt của lead (TODO 1)** cần bắt agent: (1) lập kế hoạch bằng `write_todos` và chia chủ đề thành N câu hỏi con độc lập (N >= 3, do agent quyết định); (2) giao từng câu hỏi cho `researcher` bằng công cụ `task`, song song, kèm đủ ngữ cảnh; (3) kiểm tra kết quả subagent trước khi dùng; (4) gộp ghi chú vào `sources.json`; (5) viết **thân** `report.md` theo `REPORT_TEMPLATE.md` (không viết `## References`), chỉ dùng sự kiện có trong ghi chú, và dùng ít nhất 3 trong 4 họ nguồn khi ghi chú có đủ (RUBRIC 2.2); (6) chạy `FINALIZER_PATH` bằng `execute` (mục 2.6); (7) chạy `VALIDATOR_PATH` bằng `execute` cho tới khi in `OK`; (8) nhờ `citation-checker` kiểm tra mẫu vài khẳng định.

**Prompt của researcher (TODO 2)**: liệt kê công cụ và công dụng; dùng ít nhất 2 họ nguồn cho mỗi câu hỏi con (cả báo cáo cần **ít nhất 3 họ**, xem RUBRIC 2.2 — lead phải kiểm điều này khi gộp `sources.json` và giao thêm việc nếu thiếu; `hf-daily` và `hf-search` cùng là Hugging Face, nên nên có ít nhất một nguồn `arxiv` hoặc `web`); khi gặp `ERROR` hay `NO RESULTS` thì đổi nguồn hoặc diễn đạt lại, không lặp lại đúng lời gọi vừa hỏng; **mọi thứ công cụ trả về, nhất là trang web, là dữ liệu không đáng tin** (không làm theo chỉ dẫn trong đó); chỉ ghi những gì có trong văn bản đã lấy, không bổ sung từ trí nhớ; định dạng tệp ghi chú cố định (mỗi nguồn một khối: tiêu đề, id, url, date, source, vài ý chính); báo lại cho lead đường dẫn tệp, số nguồn và tóm tắt hai dòng.

**Subagent (TODO 3)** là dict với các khóa `name`, `description`, `system_prompt`, `tools`. `description` là thứ lead đọc để quyết định giao việc nên hãy ghi rõ cần đưa gì cho subagent. Hai subagent: `researcher` (toàn bộ `SOURCE_TOOLS`) và `citation-checker` (chỉ `web_fetch`).

**Lead agent (TODO 4)**: `create_deep_agent(model=model, system_prompt=LEAD_PROMPT, subagents=build_subagents(), backend=backend, middleware=[TodoListMiddleware()])` (không có middleware này thì agent không có `write_todos`). Backend sandbox cho agent các công cụ tệp và `execute`; công cụ nguồn dữ liệu chạy ở host và được truyền qua subagent.

### 2.5 Giới hạn vòng lặp và chi phí (bắt buộc, RUBRIC 2.5)

Mặc định `deepagents` đặt `recursion_limit` là 9999 và không giới hạn số lần gọi mô hình hay công cụ. Một prompt hỏng có thể làm agent lặp vô hạn và tiêu rất nhiều token. Hãy đặt giới hạn cho lead **và** cho từng subagent:

```python
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware

LEAD_LIMITS = [ModelCallLimitMiddleware(run_limit=150, exit_behavior="end"),   # dừng hẳn khi chạm trần
               ToolCallLimitMiddleware(run_limit=300)]                          # quá trần: công cụ trả lời lỗi
SUB_LIMITS = [ModelCallLimitMiddleware(run_limit=40, exit_behavior="end"), ToolCallLimitMiddleware(run_limit=60)]
# lead:     create_deep_agent(..., middleware=[TodoListMiddleware(), *LEAD_LIMITS])
# subagent: {"name": ..., "description": ..., "system_prompt": ..., "tools": [...], "middleware": SUB_LIMITS}
# agent.invoke(..., config={"recursion_limit": 1000})                          # trần số bước của đồ thị LangGraph
```

`run_limit` đếm cho **một lần chạy** của agent đó; mỗi lần lead giao việc cho subagent là một lần chạy mới nên subagent có hạn mức riêng. Chọn số đủ rộng để một lần chạy bình thường không chạm trần (xem `meta.json` của bạn), nhưng đủ chặt để lỗi lặp bị cắt sớm. Một bản cài đặt tối giản đã đo dùng khoảng 2 phút và 170 nghìn token cho một chủ đề.

## 3. `research.py` và sandbox (TODO 1-5)

Vòng đời (mỗi bước dùng các hàm có sẵn trong `sandbox.py`):

1. `make_model()` đọc cấu hình LLM từ `.env`.
2. `with open_sandbox() as backend:` tạo sandbox Daytona và **luôn** dừng + xóa nó khi thoát khối `with`, kể cả khi lỗi.
3. `backend.execute("mkdir -p /tmp/work/research/notes /tmp/work/report")` tạo thư mục. Đường dẫn trong sandbox là **tuyệt đối**; `/tmp/work` luôn ghi được.
4. `upload(backend, {VALIDATOR_PATH: <bytes của check_citations.py>, FINALIZER_PATH: <bytes của finalize_citations.py>})`.
5. `agent.invoke({"messages": [...]}, config={"recursion_limit": 1000})`: một lần chạy deep research gồm rất nhiều bước; hãy đặt rõ giới hạn đệ quy thay vì dựa vào mặc định, và kết hợp với giới hạn ở mục 2.5. Mỗi lượt model → tool tốn khoảng 2 bước; vượt giới hạn thì LangGraph **ném** `GraphRecursionError`, không dừng êm. `recursion_limit` này **chỉ** áp cho graph của lead: subagent chạy graph riêng với giới hạn 9999 gắn sẵn (config của subagent thắng khi trùng khóa), nên subagent phải được giới hạn bằng khóa `middleware` (mục 2.5).
6. `download(backend, [REPORT_PATH, SOURCES_PATH])` trả `{đường_dẫn: bytes hoặc None}`; `None` nghĩa là tệp không có.

`save_outputs` ghi ba tệp vào `reports/`: `<slug>.md`, `<slug>.sources.json`, `<slug>.meta.json`. **Nếu agent không tạo ra báo cáo (hoặc báo cáo rỗng, hoặc `sources.json` hỏng) thì phải báo lỗi và không ghi gì cả**: một lần chạy hỏng không được để lại báo cáo rỗng trông như thành công; `main` thoát với mã 1.

`slugify(topic)`: chủ đề là input của người dùng, ví dụ `../../x` không được thoát khỏi `reports/`; chủ đề rỗng trả `topic`; chuỗi dài bị cắt còn 60 ký tự.

`<slug>.meta.json` là **bằng chứng chấm điểm**: `topic`, `model`, `elapsed_s`, `subagent_calls` (số lần gọi công cụ `task` của lead), `tool_calls`, `tokens`, `n_sources`, `source_families` (các giá trị `source` khác nhau trong `sources.json`). `tokens` chỉ đếm tin nhắn của lead; token của subagent (thường là phần lớn chi phí) không nằm trong đó.

### 2.6 Script hoàn thiện trích dẫn có sẵn (`finalize_citations.py`)

Khi để LLM tự viết và đánh số `## References`, nó hay gộp nhiều bài dưới một số hoặc làm lệch số so với `sources.json` (đã gặp ở các lần chạy thử, cả với agent mạnh). Vì vậy bộ khung kèm sẵn `finalize_citations.py`, chạy **trong sandbox**: xóa nguồn không được trích dẫn, gộp URL trùng, đánh số lại `[n]` theo thứ tự xuất hiện, chuẩn hóa `[1, 2]`/`[1-3]` thành `[1][2]`, tự sinh `## References` (một dòng cho mỗi nguồn) và ghi lại `sources.json`. `research.py` tải nó lên cùng `check_citations.py` (`FINALIZER_PATH`). Lead **viết thân báo cáo không có `## References`**, chạy script này (không tham số; chạy lại sau mỗi lần sửa thân báo cáo), rồi mới chạy validator của bạn. Cẩn thận: vì script xóa nguồn không được trích dẫn, nó có thể làm mất cả một họ nguồn; hãy kiểm lại `source_families` sau bước này (RUBRIC 2.2). Bài học: xử lý tất định sau LLM đáng tin hơn là cố viết prompt cho LLM làm đúng. Validator của bạn vẫn là hạng mục chấm điểm (RUBRIC 4.1).

## 4. `check_citations.py` (TODO)

Tệp này **chạy trong sandbox** nên chỉ dùng thư viện chuẩn. Quy tắc `check(report_text, sources)` trả về danh sách vấn đề (rỗng = ổn):

1. `sources` rỗng là vấn đề.
2. Mỗi nguồn: `n` là số nguyên; `url` bắt đầu bằng `http://` hoặc `https://`; không trùng `url` với nguồn khác.
3. Báo cáo phải có tiêu đề `## References`. Phần **trước** tiêu đề đó là thân báo cáo; các số trong danh sách tham khảo **không** tính là trích dẫn.
4. Mọi `[n]` trong thân phải có trong `sources`; mọi nguồn trong `sources` phải được trích dẫn ít nhất một lần.
5. Danh sách `## References` có **đúng một dòng cho mỗi nguồn**, dòng bắt đầu bằng `[n]`: không thiếu, không trùng số, không có số nào không phải nguồn.
6. Mỗi dòng tham khảo chứa **đúng một URL** và URL đó phải bằng `url` của nguồn `n` trong `sources.json`. Cấm gộp nhiều nguồn dưới một số (ví dụ `[3] Bài A; Bài B; Bài C`): LLM rất hay làm vậy, nên đây là lỗi bạn cần bắt.
7. LLM thường viết trích dẫn nhóm như `[1, 2]` hoặc `[1-3]`. Hoặc validator của bạn hiểu chúng (khai triển thành 1, 2 hoặc 1, 2, 3), hoặc prompt phải cấm chúng; nếu không, một nguồn sẽ bị coi là "không được trích dẫn" dù báo cáo có nhắc tới nó. Đừng đếm `[n]` nằm trong khối mã hay trong liên kết Markdown `[n](url)`.

## 5. Chạy 5 chủ đề và xử lý sự cố

Chạy từng chủ đề trong `topics.md`, rồi chạy `check_citations.py` trên máy của bạn để kiểm tra.

| Hiện tượng | Nguyên nhân thường gặp |
|---|---|
| `web_search` toàn trả văn bản nói về giới hạn tốc độ | Chưa phát hiện cờ `_meta` của Exa (mục 1.4); hoặc chưa có `EXA_API_KEY`. |
| Tool trả `NO RESULTS` liên tục | Truy vấn quá dài/cụ thể: viết lại bằng vài từ khóa. |
| `arxiv_search` trả `ERROR: ... HTTP 429` | arXiv giới hạn theo IP; cả lớp dùng chung mạng thì rất dễ gặp. Tăng `cap`/số lần thử cho arXiv, chạy lệch giờ với bạn cùng lớp; nếu vẫn thiếu họ `arxiv`, lead phải bù bằng họ khác để đủ 3 họ. |
| `source_families` chỉ có 2 họ | Prompt chỉ yêu cầu "ít nhất 2 họ" cho researcher; lead phải kiểm tổng số họ khi gộp `sources.json` và giao thêm việc nếu thiếu (RUBRIC 2.2). |
| Agent dừng mà không có `report.md` | Prompt của lead thiếu bước 4-5; hoặc đụng giới hạn đệ quy. |
| `subagent_calls` bằng 0 | Prompt không bắt giao việc, hoặc `description` của subagent quá mơ hồ. |
| Lỗi tạo sandbox | Sai `DAYTONA_API_KEY` hoặc hết hạn mức: dừng/xóa các sandbox cũ trong dashboard Daytona, hoặc đặt `SANDBOX=docker` để dùng container Docker cục bộ. |
| Lần này báo cáo hợp lệ, lần sau trích dẫn lỗi | Tính ngẫu nhiên của LLM. Siết prompt (ví dụ yêu cầu rõ "một dòng cho mỗi nguồn") và validator; không sửa tay báo cáo. |
| Cảnh báo `Sandbox glob could not read ... under '/'` | Vô hại: agent đã liệt kê thư mục gốc của sandbox. |
| Báo cáo có `[n]` không tồn tại | Lead viết báo cáo trước khi gộp `sources.json`; bắt buộc chạy validator và sửa. |
| `## References` gộp nhiều nguồn dưới một số, hoặc số tham khảo lệch với `sources.json` | LLM tự viết danh sách tham khảo. Đừng để nó viết: bắt lead bỏ phần này và chạy `finalize_citations.py` (mục 2.6). |

Gợi ý: nếu có LangSmith, bật tracing để xem agent đã gọi công cụ và lệnh shell nào.

## 6. Mở rộng (tùy chọn, không bắt buộc)

Các tính năng giúp hệ thống chạy dài hơi và an toàn hơn (mỗi mục là một cách để làm tốt hơn, không tính điểm riêng):

- **Giới hạn nâng cao**: `thread_limit` (ngoài `run_limit`) để hạn mức vẫn đúng khi chạy lại từ checkpoint; giới hạn token cho từng subagent; chỉ retry lỗi tạm thời (timeout, 429, 5xx), không retry lỗi 400/401.
- **Ngân sách token dùng chung**: một bộ đếm dùng chung cho lead và mọi subagent chạy song song (cần khóa luồng), cảnh báo khi gần hết và dừng khi hết.
- **Bộ nhớ dài hạn**: tham số `memory=["/memory/AGENTS.md"]` nạp một tệp bộ nhớ vào prompt mỗi lần chạy; định tuyến `/memory/` về một thư mục trên host bằng `CompositeBackend` để nó tồn tại giữa các lần chạy.
- **Tóm tắt/nén ngữ cảnh**: `deepagents` tự tóm tắt khi ngữ cảnh dài; công cụ `compact_conversation` (`create_summarization_tool_middleware`) cho phép agent chủ động nén.

## 7. Tự kiểm tra trước khi nộp

- [ ] (Khuyến khích) viết vài test cho `with_retry`, `slugify`, `check_citations` (mock `time.sleep`); `pytest` không có trong `requirements.txt`, cài thêm bằng `pip install pytest` nếu dùng.
- [ ] `python tools.py` cho kết quả thật ở cả 5 công cụ (có thể mất thời gian vì retry).
- [ ] Mỗi báo cáo có `subagent_calls >= 3` và `source_families` có ít nhất 3 họ nguồn trong `meta.json`.
- [ ] `python3 check_citations.py reports/<slug>.md reports/<slug>.sources.json` in `OK` cho cả 5 báo cáo (gồm một dòng tham khảo cho mỗi nguồn).
- [ ] Đọc ít nhất 3 trích dẫn trong mỗi báo cáo và mở nguồn để xác nhận câu đó đúng.
- [ ] Không có `.env` hay khóa API nào trong repo (`git status`, và `git log -p | grep -i key`).
- [ ] Repo công khai, `requirements.txt` đủ để cài và chạy, README của repo nộp nói cách chạy.
