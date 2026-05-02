# HishabAI — Business Logic Specifications

## 1. Document Processing Pipeline

Every document goes through this flow (Celery async task):

1. Fetch document record from Supabase DB
2. Download file from Supabase Storage (signed URL)
3. Determine strategy by MIME type:
   - PDF (text-based): pdfplumber → extract text → Gemini extraction
   - PDF (scanned): pdf2image → each page → OCR pipeline
   - Image (JPEG/PNG/WEBP): OCR pipeline directly
   - Excel/CSV: pandas parse → map columns
4. Run OCR pipeline (Tesseract ben+eng, confidence threshold 80%)
5. Run field extractor based on detected doc_type
6. Calculate confidence scores
7. Save extracted_data + confidence to document_extractions table
8. Update document status
9. Trigger Supabase Realtime notification for connected clients

## 2. VAT Reconciliation Engine

Reconciles purchase register against supplier-filed VAT returns.

**Match priority (in order):**
1. **EXACT** (score 1.0): BIN + invoice_no (normalized) + date (exact) + amount (exact) → auto_approve
2. **FUZZY** (score 0.8): BIN + invoice_no + date within ±3 days + amount within ±0.5% → suggest_approve
3. **PARTIAL** (score 0.4): Only BIN matches → manual_review, high ITC risk
4. **NO_MATCH** (score 0.0): BIN not found at all → flag_supplier, critical ITC risk

**Invoice number normalization:** Remove spaces, hyphens, leading zeros, lowercase.

**ITC risk = sum of vat_amount for all no_match + partial_match items.**

## 3. NBR Notice AI Module

Uses **Vertex AI (Gemini 2.5 Flash)** with strict system prompt for drafting legal responses.
- Cites only real BD tax law sections (validated against known sections list)
- Uses `[[INSERT: ...]]` tags where CA must add specific figures
- Uses `[[INSUFFICIENT DATA: ...]]` where data is missing
- MVP: Support Show Cause VAT notices only

## 4. Compliance Calendar Engine

Single source of truth for all Bangladesh regulatory deadlines.
Generates ComplianceEvent records per client based on their entity type and obligations.

**Monthly:** VAT Return (15th), TDS Return (20th), TDS Deposit (7th)
**Annual:** Company IT Return (15 Jan), Individual IT Return (30 Nov), RJSC Annual Return

## 5. AI Integration Rules

- LLM: **Google Vertex AI — Gemini 2.5 Flash** (fast, cost-effective, good multilingual support)
- All prompts start with role definition + BD regulatory context
- Low temperature (0.2) for legal/financial tasks
- All LLM outputs validated before display
- Token usage logged to ai_token_usage table for billing tracking
- Retry with exponential backoff on transient failures
