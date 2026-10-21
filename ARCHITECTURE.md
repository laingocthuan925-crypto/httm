# Kiến trúc: từ tài liệu → bài báo có dẫn chứng kiểm chứng

## Mục tiêu và giới hạn (đọc trước)
- **Làm được (V1):** bài *systematic review / narrative review / conceptual paper* — nội dung 100% xuất phát từ paper đã thu thập,
  mỗi ý khoa học đều có `[paper_id]` truy ngược về **quote nguyên văn đã kiểm chứng**.
- **Chưa làm (V2):** bài *thực nghiệm* — cần dữ liệu thật của người dùng (survey/thí nghiệm) + phân tích thống kê. Hệ thống
  **không được bịa dữ liệu**, nên `paper_type=empirical` bị từ chối cho tới khi có module nhập dữ liệu.
- "Giống người thật" = chất lượng văn (tổng hợp theo ý, có lập trường, nhịp câu đa dạng, đúng phong cách journal), KHÔNG phải
  né công cụ phát hiện AI. Phần Methodology tự khai báo việc dùng LLM; hãy khai báo theo quy định của journal khi nộp.

## Luồng
```
Plan → Search(OpenAlex+S2) → Screen(LLM) → Ingest(PDF→chunks→vector)
     → Analyze(quote verified) → Synthesize(themes/contradictions/gaps)
     ⏸ người xác nhận gap
     → RQ generator (feasibility + novelty grounded) [+ ConceptualModel/Hypothesis]
     ⏸ người chọn RQ            (auto_approve=true bỏ qua 2 điểm dừng)
     → Outline → Draft(từng mục, có "bộ nhớ") → Abstract
     → Review: citation + claim-support + style + structure → Revise (tối đa N vòng)
     → Export (.md/.docx, [W1] → (Smith et al., 2021) + References)
```

## Các chốt chống bịa (điểm khác biệt so với "bảo LLM viết bài")
| Chốt | Ở đâu |
|---|---|
| Quote LLM trích phải nằm thật trong chunk nguồn, không thì bỏ claim | `services/quotes.py`, `routers/analysis.py` |
| ID paper LLM bịa bị lọc khỏi themes/gaps/outline/hypotheses | `synthesis.py`, `writer.py`, `rq_generator.py` |
| Writer chỉ thấy *evidence pack*; cấm dùng kiến thức ngoài | `prompts.writer_system` |
| Methodology dựng từ log tìm kiếm/sàng lọc thật | `evidence.build_process_data` |
| Citation tồn tại + claim được bằng chứng ủng hộ | `citation_checker`, `claim_verifier` |
| Số liệu văn phong (độ dài câu, cụm sáo rỗng, từ nối) | `style_checks` |

## Phân công
- **A:** `prompts.py`, `llm.py`, `pipeline_models.py`, `synthesis.py`, `rq_generator.py`, `writer.py`, `analysis.py`
- **B:** `search.py`, `reader.py`, `openalex.py`, `semantic_scholar.py`, `pdf_*`, `embeddings.py`, `ingest.py`, `retrieval.py`
- **C:** `reviewer.py`, `citation_checker`, `claim_verifier`, `style_checks`, `export.py`, `exporter`, Docker, CI, tests
- File trung tâm: `db.py` (schema mới — báo nhóm), `models.py` (không đổi; schema mới ở `pipeline_models.py`)

## Cách chạy
```
docker compose up --build
curl -X POST localhost:8000/plan -H 'Content-Type: application/json' -d '{"topic":"...", "language":"en"}'   # -> id
curl -X PUT  localhost:8000/pipeline/1/config -H 'Content-Type: application/json' -d '{"paper_type":"systematic_review","language":"en","venue":"Computers & Education"}'
curl -X POST localhost:8000/writer/1/style-profile -H 'Content-Type: application/json' -d '{"samples":["<đoạn mẫu từ journal>"]}'   # tuỳ chọn, nên có
curl -X POST localhost:8000/pipeline/1/run -H 'Content-Type: application/json' -d '{"auto_approve":true}'
curl localhost:8000/pipeline/1/status
curl -o paper.docx "localhost:8000/export/1?format=docx"
```
Chạy từng bước thủ công (khuyên dùng lần đầu): `/search/1` → `/search/1/screen` → `/reader/1/ingest` → `/analyze/1`
→ `/synthesize/1` → `/synthesize/1/confirm` → `/rq/1` → `/rq/1/select` → `/writer/1/outline` → `/writer/1/draft`
→ `/review/1` → `/writer/1/revise` → `/export/1`.
