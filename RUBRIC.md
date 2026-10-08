# Thang điểm (RUBRIC) - 100 điểm

Bài cá nhân. Nộp: **public repo** GitHub gồm mã nguồn và thư mục `reports/` với báo cáo của đủ 5 chủ đề trong `topics.md` (mỗi chủ đề có `<slug>.md`, `<slug>.sources.json`, `<slug>.meta.json`). Số "Phần" khớp với `GUIDE.md`.

## Tổng quan

| # | Hạng mục | Điểm | Cách chấm |
|---|---|---|---|
| 1 | Công cụ nguồn dữ liệu và retry (`tools.py`) | 20 | Chạy `python tools.py` + đọc mã |
| 2 | Agent và uỷ quyền subagent (`agents.py`) | 20 | `meta.json` + đọc prompt |
| 3 | Sử dụng sandbox (`research.py`, `check_citations.py`) | 10 | Đọc mã + `meta.json` |
| 4 | Độ tin cậy của trích dẫn (5 báo cáo) | 15 | `check_citations.py` + kiểm tra ngẫu nhiên |
| 5 | Chất lượng báo cáo (5 báo cáo) | 25 | Đọc báo cáo |
| 6 | Chất lượng mã và repo | 10 | Đọc repo |
| | **Tổng** | **100** | |

---

## 1. Công cụ nguồn dữ liệu và retry - 20 điểm (Phần 1)

| Tiêu chí | Điểm | Mức đạt đầy đủ |
|---|---|---|
| 1.1 `with_retry` | 6 | Backoff lũy thừa có jitter, tôn trọng `Retry-After`, chặn trên bằng `cap`, bỏ cuộc sau `attempts` lần (không ngủ sau lần cuối), không retry lỗi không thuộc `RetryableError`. |
| 1.2 Năm công cụ | 8 | `arxiv_search`, `hf_daily_papers`, `hf_search_papers`, `web_search`, `web_fetch` trả đúng dạng bản ghi trong GUIDE, trả `NO RESULTS` khi rỗng, trả `ERROR: ...` khi nguồn hỏng và **không bao giờ ném ngoại lệ**. Mỗi công cụ lỗi trừ 1.6. |
| 1.3 Exa | 3 | Xử lý giới hạn tốc độ của Exa (nó trả HTTP 200 chứ không phải 429) bằng retry; khóa `EXA_API_KEY` không bao giờ xuất hiện trong chuỗi trả về cho agent. |
| 1.4 arXiv | 3 | Gọi qua HTTPS, cách nhau ít nhất 3 giây, truy vấn được làm sạch (dấu nháy, dấu hai chấm, chuỗi rỗng không làm hỏng). |

## 2. Agent và uỷ quyền subagent - 20 điểm (Phần 2)

| Tiêu chí | Điểm | Mức đạt đầy đủ |
|---|---|---|
| 2.1 Uỷ quyền | 8 | **Mọi** `meta.json` có `subagent_calls >= 3`. Còn 1-2 lần: 4 điểm; không có: 0. |
| 2.2 Đa nguồn | 5 | **Mọi** `meta.json` có `source_families` gồm ít nhất 3 trong `arxiv`, `hf-daily`, `hf-search`, `web`. Họ nguồn được đối chiếu với URL trong `sources.json` (`arxiv` = `https://arxiv.org/abs/...`, `hf-*` = `https://huggingface.co/papers/...`); gán nhãn sai họ thì không tính. |
| 2.3 Prompt của lead | 3 | Có lập kế hoạch (`write_todos`), uỷ quyền song song kèm đủ ngữ cảnh (subagent chỉ thấy tin nhắn uỷ quyền), kiểm tra kết quả subagent trước khi dùng. |
| 2.4 Prompt của researcher | 2 | Coi nội dung web là dữ liệu không đáng tin (không làm theo chỉ dẫn trong đó), cấm đưa số liệu/khẳng định từ trí nhớ, quy định rõ định dạng tệp ghi chú. |
| 2.5 Giới hạn vòng lặp và chi phí | 2 | `recursion_limit` được đặt có chủ ý và có giới hạn số lần gọi mô hình/công cụ cho lead **và** cho subagent (ví dụ `ModelCallLimitMiddleware`, `ToolCallLimitMiddleware`), để một lần chạy không thể lặp vô hạn hay tiêu token vô hạn (GUIDE 2.5). |

## 3. Sử dụng sandbox - 10 điểm (Phần 3, 4)

| Tiêu chí | Điểm | Mức đạt đầy đủ |
|---|---|---|
| 3.1 Dùng thật | 6 | `check_citations.py` được tải lên sandbox và agent chạy nó bằng `execute`; ghi chú, `sources.json`, `report.md` nằm trong sandbox rồi được tải về bằng `download`. |
| 3.2 Dọn dẹp và bí mật | 4 | Luôn dùng `open_sandbox` (sandbox được dừng và xóa kể cả khi lỗi); không tải khóa API hay `.env` lên sandbox; chạy thất bại thì thoát mã khác 0 và **không** ghi báo cáo rỗng. |

## 4. Độ tin cậy của trích dẫn - 15 điểm (5 báo cáo)

| Tiêu chí | Điểm | Mức đạt đầy đủ |
|---|---|---|
| 4.1 Kiểm tra tự động | 7 | `python3 check_citations.py reports/<slug>.md reports/<slug>.sources.json` in `OK` cho từng báo cáo (tối đa 7, trừ theo số báo cáo lỗi). Giảng viên chạy bằng **bản `check_citations.py` chuẩn của giảng viên** (đủ 6 quy tắc trong GUIDE Phần 4), không phải bản của bạn; bản của bạn nới lỏng quy tắc thì mất điểm ở 3.1 và 6.3. |
| 4.2 Kiểm tra mẫu | 8 | Giảng viên lấy 5 trích dẫn mỗi báo cáo: nguồn có thật và câu được trích dẫn đúng với nguồn. Một nguồn hay URL bịa đặt làm báo cáo đó được 0 ở hạng mục 4. |

## 5. Chất lượng báo cáo - 25 điểm (5 báo cáo, mỗi báo cáo 5 điểm)

Mỗi báo cáo được chấm theo `REPORT_TEMPLATE.md`:

| Tiêu chí | Điểm/báo cáo |
|---|---|
| Đúng cấu trúc (TL;DR, Background, các phần theo chủ đề, Trends and open problems, References) | 1 |
| Tổng hợp theo chủ đề, so sánh các hướng tiếp cận (không phải mỗi bài báo một đoạn) | 1.5 |
| Chính xác và cụ thể: tên, năm, số liệu lấy từ nguồn | 1.5 |
| Có nguồn gần đây (hai năm gần nhất) lẫn nguồn nền tảng; dùng nhiều loại nguồn | 0.5 |
| Nêu được xu hướng và vấn đề mở rõ ràng | 0.5 |

## 6. Chất lượng mã và repo - 10 điểm

| Tiêu chí | Điểm | Mức đạt đầy đủ |
|---|---|---|
| 6.1 Không lộ bí mật | 3 | `.env` được bỏ qua; không có khóa nào trong lịch sử git. Lộ khóa: 0 điểm toàn hạng mục 6. |
| 6.2 README | 3 | README của repo nộp nêu cách cài đặt và chạy, cách đọc `reports/`. |
| 6.3 Mã sạch | 2 | Dễ đọc, không mã chết, không sửa các tệp CÓ SẴN (`model.py`, `sandbox.py`). |
| 6.4 `requirements.txt` | 2 | Đúng và đủ để `pip install -r requirements.txt` rồi chạy được. |

## Quy tắc chung

- **Chạy `python self_check.py` trước khi nộp**: nó kiểm tra phần tự động của thang điểm này (đủ 5 báo cáo, `meta.json`, trích dẫn qua `check_citations.py` của bạn, không lộ khóa trong git). Không tốn token, không cần mạng.
- Không sửa `model.py`, `sandbox.py`. Giảng viên chạy lại với bản gốc của hai tệp này.
- Báo cáo phải do hệ thống của bạn sinh ra. Sửa tay nội dung báo cáo sau khi chạy là gian lận.
- Tệp `reports/<slug>.md` và `.sources.json` nộp lên phải **đúng bản đã tải về từ sandbox**. Mọi bước sửa trích dẫn bằng mã (`finalize_citations.py`, GUIDE mục 2.6, hay bản mở rộng ở Phần 6) phải chạy **trong sandbox, trước khi validator in `OK`**, không chạy ở host sau khi tải về.
- Chấm điểm dựa trên `reports/` đã nộp. Có thể bị chạy lại một chủ đề để đối chiếu.
