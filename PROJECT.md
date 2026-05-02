# HISHABAI — MASTER BUILD PROMPT

## For: Claude Opus 4.6 | Role: Lead Architect & Engineer

## Classification: Engineering Execution Prompt v1.

## BEFORE YOU READ A SINGLE REQUIREMENT

#### Stop. Read this section first.

#### You are being asked to build a real, produc tion-grade SaaS produc t — not a demo, not a

#### prototype with TODO comments, not a scaffold. Every line of code you write should be

#### something that a Dhaka-based CA firm could use with their actual client data tomorrow.

#### This means:

#### Never leave placeholder logic where real logic is needed for the MVP. Write it or say

#### why you can’t.

#### When you are uncertain, state your assumption explicitly, make the most defensible

#### choice, and flag it for review. Do not silently default.

#### Bangladesh-first thinking applies to every decision: naming, error messages, date

#### formats, currency formatting, regulatory logic, everything.

#### The CA is always in control. No feature should autonomously act on behalf of the user

#### with regulatory bodies. Every AI output is a draft until the CA approves it. This is both a

#### product principle and an ethical requirement.

#### Think in systems, not features. Before writing any module, understand how it

#### connects to every other module. A document uploaded in the ingestion service

#### eventually feeds the reconciliation engine, which feeds the client report. Build with that

#### chain in mind.

#### You will work through this document sec tion by sec tion. At the end of each major sec tion,

#### re-read what you’ve built and ask: “Would a CA at a 20-person Dhaka firm trust this with

#### their clients’ data?” If the answer is no, fix it before moving on.


## PART 1: PRODUCT IDENTITY

### 1.1 What Is HishabAI?

#### HishabAI (িহসাব AI) is a multi-tenant SaaS platform that automates the pre-advisory

#### workflow of Chartered Accountancy firms in Bangladesh. It sits as an intelligent middleware

#### layer between unstructured client data (invoices, bank statements, photos of receipts) and

#### the CA’s existing tools (Tally, Excel, NBR portals).

#### The name: িহসাব (hishab) means “accounts” or “calculation” in Bengali. The brand is

#### deliberately Bangladeshi.

### 1.2 The Core Loop (Never Lose Sight of This)

```
CLIENT submits chaotic documents
↓
HISHABAI reads, classifies, extracts, reconciles, drafts
↓
CA reviews flagged items, edits AI drafts, approves
↓
CA advises client, files returns, responds to notices
```
#### HishabAI owns the middle step entirely. That is its entire value proposition.

### 1.3 The One Metric That Matters at Launch

#### Hours saved per CA per month. Every feature decision should be evaluated against this

#### metric. Features that save 30+ minutes/month per active user are in scope for MVP.

#### Features that save less than 5 minutes are Phase 2+.

## PART 2: BANGLADESH REGULATORY CONTEXT

### (Critical knowledge you MUST have before writing any business logic)

#### 2.1 The MushaK ( মুসক ) VAT System

#### Bangladesh’s VAT system is governed by the VAT and Supplementary Duty Act, 2012

#### (effective from 2019). The key instrument is the MushaK (মুসক) form system.

#### Critical forms you must understand:


```
Form Name Purpose Key Fields
```
```
Mushak
6.
```
```
Purchase
Register
```
```
Records all
purchases
```
```
Seller BIN, Buyer BIN, Invoice No, Invoice Date,
Ta x a b l e Va l u e ( B DT ) , VAT A m o u n t ( 1 5 % ) , H S
Code
```
```
Mushak
6.
```
```
Sales
Register
```
```
Records all
sales
```
```
Same as 6.1 from seller perspective
```
```
Mushak
6.
```
```
Rebate
Register
```
```
Records Input
Ta x C r e d i t
claims
```
```
Eligible purchases, rebate amount, period
```
```
Mushak
9.
```
```
Monthly
VAT
Return
```
```
Filed by 15th
of following
month
```
```
To t a l s a l e s , t o t a l p u rc h a s e s , n e t VAT p aya b l e
```
#### BIN (Business Identification Number):

#### Format: 9 digits, issued by NBR

#### Every VAT-registered business has one

#### Used as the primary key for supplier/buyer matching

#### Validation regex: ^\d{9}$

#### Public lookup available at: https://bin.nbr.gov.bd

#### TIN (Taxpayer Identification Number):

#### Format: 12 digits

#### Used for income tax, not VAT

#### Validation regex: ^\d{12}$

#### VAT Rate: Standard rate is 15% in Bangladesh. Some goods have supplementary duty on

#### top. For MVP, assume 15% unless otherwise specified.

#### The reconciliation problem in detail: When a business claims Input Tax Credit (ITC) on

#### purchases, the NBR cross-checks whether the supplier actually filed a return declaring that

#### sale. If the supplier filed with a different invoice number, date, or amount — or did not file at

#### all — the buyer’s ITC claim is disallowed. This check is done manually today. HishabAI

#### automates it.

#### 2.2 Income Tax Framework


#### Governed by the Income Tax Ordinance, 1984 (ITO 1984) and updated annually through

#### Finance Acts.

#### Key deadlines:

#### Individual income tax return: 30 November

#### Company income tax return: 15 January (for companies with June 30 fiscal year end)

#### Advance tax: Quarterly (15 Sep, 15 Dec, 15 Mar, 15 Jun)

#### TDS (Tax Deducted at Source) return: 20th of following month

#### TDS challan deposit: 7th of following month

#### Common TDS sections CAs deal with:

#### Section 52: TDS on supply of goods

#### Section 52A: TDS on commission

#### Section 53BB: TDS on royalties

#### Section 56: TDS on service fees (6.5% or 10%)

#### 2.3 RJSC (Registrar of Joint Stock Companies and Firms)

#### Under the Companies Act, 1994, all registered companies must:

#### Hold AGM within 18 months of incorporation, then annually

#### File annual return within 21 days of AGM

#### Submit audited financial statements

#### 2.4 NBR Notice Types (for the Notice AI module)

```
Notice Type Governing Law Common Reason
```
```
Show Cause Notice (SCN) VAT Act s.55 Alleged VAT underpayment
```
```
Assessment Order ITO 1984 s.83 Income tax assessment by DCT
```
```
Demand Notice VAT Act VAT demand after audit
```
```
Audit Notice VAT Act s.63 VAT audit selection
```
```
Interest Notice VAT Act s.37 Late return interest
```

```
TDS Default Notice ITO 1984 s.137 Failure to deduct/deposit TDS
```
#### 2.5 Bangladesh-Specific Formatting Rules

#### These must be applied consistently throughout the application:

```
# Currency
CURRENCY_SYMBOL = "৳" # Unicode U+09F
# Format: ৳ 1,25,000.00 (South Asian numbering: lakh/crore system)
# 1,00,000 = 1 lakh; 1,00,00,000 = 1 crore
```
```
# Number formatting (South Asian)
def format_bdt(amount: float) -> str:
# 1234567.89 → ৳ 12,34,567.
...
```
```
# Date format in official documents: DD/MM/YYYY (for display)
# Internal storage: ISO 8601 (YYYY-MM-DD)
```
```
# Fiscal Year: July 1 – June 30
# FY 2023-24 means July 1, 2023 to June 30, 2024
```
```
# Tax year = Assessment Year = financial year (Bangladesh uses fiscal year)
```
#### 2.6 What Is NOT in NBR’s Public API (as of 2024)

#### Be honest about this in the code and UI. The following require authenticated portal access

#### or manual input — do NOT pretend to have real-time NBR data unless you’ve actually built

#### the integration:

#### Supplier VAT return filing status (requires NBR VAT Online credentials)

#### TIN holder details (requires NBR eTIN portal credentials)

#### Outstanding tax demands (requires NBR iBAS++ credentials)

#### Real-time BIN validity (BIN lookup is public but not API-accessible; use scraping or

#### cache)

#### For MVP: Build the reconciliation logic assuming the CA will manually export supplier data

#### from NBR VAT Online as an Excel/CSV file and upload it. Do not attempt to scrape NBR

#### portals in MVP. Mark integration points clearly with # TODO: NBR_INTEGRATION comments.


## PART 3: ARCHITECTURE — ALREADY-DECIDED (DO NOT

## REINVENT)

#### These decisions have been made. Do not propose alternatives unless you find a critical

#### technical flaw.

### 3.1 System Architecture

##### ┌─────────────────────────────────────────────────────────────┐

```
│ FRONTEND (React + TypeScript) │
│ CA Dashboard App │ Client Upload Portal │
└───────────────────────┬───────────────────┬─────────────────┘
│ REST / JSON │
▼ ▼
┌───────────────────────────────────────────────────────────--┐
│ BACKEND (FastAPI, Python 3.11+) │
│ │
│ Auth │ Documents │ Reconciliation │ AI Pipeline │
│ Calendar │ Notices │ Reports │ Clients │
└───────────────────────┬─────────────────────────────────────┘
│
┌─────────────┼──────────────┐
▼ ▼ ▼
PostgreSQL Redis S3-compatible
(primary DB) (cache+queue) (document store)
│ │
└──────────── Celery Workers (async tasks)
│
AI Services
(Claude API + Tesseract)
```
### 3.2 Multi-Tenancy Model

#### Te n a n t = CA F i r m (one ICAB-registered firm = one tenant)

#### Schema-per-tenant in PostgreSQL (not row-level — schema-per-tenant for proper

#### isolation)

#### Schema naming convention: tenant_{tenant_id_short} (e.g., tenant_a1b2c3)

#### Shared schema: public — for system-level data only (tenants table, plans, etc.)

#### Every API request must validate tenant_id from the JWT claim against the resource

#### being accessed


### 3.3 Technology Stack (Fixed)

#### Backend:

```
Language: Python 3.11+
Framework: FastAPI (async)
ORM: SQLAlchemy 2.0 (async) with Alembic migrations
Task Queue: Celery 5 + Redis
Caching: Redis (redis-py async)
Auth: JWT (python-jose) + bcrypt passwords
File Storage: MinIO (local dev) / AWS S3 (production) via boto
Search: PostgreSQL full-text search (MVP), Elasticsearch (Phase 2)
Email: SendGrid API
SMS: SSL Wireless (Bangladesh) — sslwireless.com API
```
#### Frontend:

```
Framework: React 18 + TypeScript
State: Zustand
UI: shadcn/ui + Tailwind CSS
Charts: Recharts
Forms: React Hook Form + Zod
HTTP: Axios with interceptors
```
#### AI/ML:

```
OCR (primary): Tesseract 5 with 'ben' (Bengali) + 'eng' language packs
OCR (fallback): Google Cloud Vision API (when Tesseract confidence < 80%)
Image processing: OpenCV (pre-processing before OCR)
LLM: Anthropic Claude API (claude-sonnet-4-6 for drafting)
PDF parsing: pdfplumber (text PDFs) + pdf2image (scanned PDFs)
```
#### Infrastructure:

```
Containers: Docker + Docker Compose (development)
Kubernetes / ECS (production — decide at deployment)
Database: PostgreSQL 15
Cache/Queue: Redis 7
Object Storage: MinIO (dev), AWS S3 (prod)
```
## PART 4: PROJECT STRUCTURE


hishabai/
├── backend/
│ ├── app/
│ │ ├── main.py # FastAPI app factory
│ │ ├── config.py # Settings (pydantic-settings)
│ │ ├── database.py # DB engine, session factory
│ │ ├── dependencies.py # FastAPI dependencies (auth, tenant, db)
│ │ │
│ │ ├── auth/
│ │ │ ├── router.py
│ │ │ ├── service.py
│ │ │ ├── schemas.py
│ │ │ └── models.py
│ │ │
│ │ ├── tenants/ # CA Firm management
│ │ │ ├── router.py
│ │ │ ├── service.py
│ │ │ ├── schemas.py
│ │ │ └── models.py
│ │ │
│ │ ├── clients/ # CA's clients
│ │ │ ├── router.py
│ │ │ ├── service.py
│ │ │ ├── schemas.py
│ │ │ └── models.py
│ │ │
│ │ ├── documents/ # Document ingestion + OCR
│ │ │ ├── router.py
│ │ │ ├── service.py
│ │ │ ├── schemas.py
│ │ │ ├── models.py
│ │ │ ├── ocr/
│ │ │ │ ├── engine.py # Tesseract + fallback orchestrator
│ │ │ │ ├── preprocessor.py # OpenCV image preprocessing
│ │ │ │ ├── extractors/
│ │ │ │ │ ├── mushak_61.py
│ │ │ │ │ ├── mushak_62.py
│ │ │ │ │ ├── bank_statement.py
│ │ │ │ │ ├── nbr_notice.py
│ │ │ │ │ └── generic.py
│ │ │ │ └── confidence.py
│ │ │ └── tasks.py # Celery tasks for async processing
│ │ │
│ │ ├── reconciliation/ # VAT reconciliation engine
│ │ │ ├── router.py
│ │ │ ├── service.py
│ │ │ ├── schemas.py


│ │ │ ├── models.py
│ │ │ ├── engine.py # Core matching algorithm
│ │ │ ├── matchers.py # Exact, fuzzy, partial matchers
│ │ │ └── tasks.py
│ │ │
│ │ ├── notices/ # NBR notice AI
│ │ │ ├── router.py
│ │ │ ├── service.py
│ │ │ ├── schemas.py
│ │ │ ├── models.py
│ │ │ ├── classifier.py # Notice type classification
│ │ │ ├── drafter.py # AI reply drafting
│ │ │ └── legal_db.py # BD tax law reference data
│ │ │
│ │ ├── calendar/ # Compliance calendar
│ │ │ ├── router.py
│ │ │ ├── service.py
│ │ │ ├── schemas.py
│ │ │ ├── models.py
│ │ │ ├── bd_deadlines.py # All BD regulatory deadlines
│ │ │ └── tasks.py # Reminder dispatch
│ │ │
│ │ ├── reports/ # MIS report generator
│ │ │ ├── router.py
│ │ │ ├── service.py
│ │ │ ├── schemas.py
│ │ │ └── generators/
│ │ │ ├── mis_report.py
│ │ │ └── pdf_builder.py
│ │ │
│ │ ├── ai/ # Shared AI utilities
│ │ │ ├── claude_client.py # Anthropic API wrapper
│ │ │ ├── prompts/ # All prompt templates as .txt or .py
│ │ │ │ ├── notice_classify.txt
│ │ │ │ ├── notice_draft_reply.txt
│ │ │ │ ├── mis_narrative.txt
│ │ │ │ └── document_extract.txt
│ │ │ └── validators.py # Validate LLM outputs
│ │ │
│ │ └── core/
│ │ ├── security.py # Encryption, hashing utils
│ │ ├── formatting.py # BDT formatting, date utils
│ │ ├── storage.py # S3/MinIO abstraction
│ │ ├── exceptions.py # Custom exception classes
│ │ └── middleware.py # Tenant resolution, logging
│ │
│ ├── migrations/ # Alembic migration files


```
│ ├── tests/
│ │ ├── unit/
│ │ ├── integration/
│ │ └── fixtures/
│ ├── requirements.txt
│ ├── Dockerfile
│ └── alembic.ini
│
├── frontend/
│ ├── src/
│ │ ├── app/ # Route layouts
│ │ ├── features/ # Feature-sliced structure
│ │ │ ├── auth/
│ │ │ ├── dashboard/
│ │ │ ├── clients/
│ │ │ ├── documents/
│ │ │ ├── reconciliation/
│ │ │ ├── notices/
│ │ │ ├── calendar/
│ │ │ └── reports/
│ │ ├── shared/
│ │ │ ├── components/
│ │ │ ├── hooks/
│ │ │ ├── lib/ # axios, utils, formatters
│ │ │ └── types/
│ │ └── main.tsx
│ ├── public/
│ ├── package.json
│ └── Dockerfile
│
├── docker-compose.yml # Full local dev stack
├── docker-compose.test.yml
└── README.md
```
## PART 5: DATABASE SCHEMA (CANONICAL — IMPLEMENT THIS

## EXACTLY)

#### The following is the complete MVP database schema. Implement this precisely. All tables

#### live in the tenant-specific schema unless prefixed with public..

### 5.1 Public Schema (System-Level)

##### -- ============================================================


### 5.2 Tenant Schema (Per-Firm Data)

```
-- PUBLIC SCHEMA — System tables, not tenant-specific
-- ============================================================
```
```
CREATE TABLE public.tenants (
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
firm_name VARCHAR(255) NOT NULL,
firm_name_bn VARCHAR(255), -- Bangla name
icab_reg_no VARCHAR(32) UNIQUE, -- ICAB registration
email VARCHAR(255) UNIQUE NOT NULL,
phone VARCHAR(20),
address TEXT,
plan VARCHAR(32) NOT NULL DEFAULT 'starter',
-- 'starter' | 'professional' | 'enterprise'
plan_expires_at TIMESTAMPTZ,
is_active BOOLEAN NOT NULL DEFAULT TRUE,
schema_name VARCHAR(64) UNIQUE NOT NULL, -- e.g. tenant_a1b2c
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
```
CREATE TABLE public.users (
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
email VARCHAR(255) UNIQUE NOT NULL,
password_hash VARCHAR(255) NOT NULL,
full_name VARCHAR(255) NOT NULL,
role VARCHAR(32) NOT NULL DEFAULT 'junior_ca',
-- 'firm_admin' | 'senior_ca' | 'junior_ca'
is_active BOOLEAN NOT NULL DEFAULT TRUE,
last_login_at TIMESTAMPTZ,
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
```
CREATE INDEX idx_users_tenant ON public.users(tenant_id);
CREATE INDEX idx_users_email ON public.users(email);
```
##### -- ============================================================

```
-- TENANT SCHEMA — Created dynamically per firm
-- All tables below live in schema: tenant_{id_short}
-- ============================================================
```
```
CREATE TABLE clients (
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
```

name VARCHAR(255) NOT NULL,
name_bn VARCHAR(255),
tin VARCHAR(12), -- 12-digit TIN
bin VARCHAR(9), -- 9-digit BIN (if VAT registered)
entity_type VARCHAR(32) NOT NULL,
-- 'company' | 'individual' | 'partnership' | 'ngo' | 'bank'
industry VARCHAR(64),
fiscal_year_end VARCHAR(5) DEFAULT '06-30', -- MM-DD format
is_vat_registered BOOLEAN NOT NULL DEFAULT FALSE,
is_listed BOOLEAN NOT NULL DEFAULT FALSE, -- Listed on DSE/CSE
contact_email VARCHAR(255),
contact_phone VARCHAR(20),
portal_access BOOLEAN NOT NULL DEFAULT FALSE,
portal_token VARCHAR(64) UNIQUE, -- For client portal access
notes TEXT,
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
created_by UUID NOT NULL, -- references public.users

CONSTRAINT valid_tin CHECK (tin ~ '^\d{12}$' OR tin IS NULL),
CONSTRAINT valid_bin CHECK (bin ~ '^\d{9}$' OR bin IS NULL)
);

CREATE TABLE compliance_obligations (
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
obligation_type VARCHAR(64) NOT NULL,
-- 'vat_return' | 'tds_return' | 'income_tax_company' |
-- 'income_tax_individual' | 'rjsc_annual' | 'advance_tax' |
-- 'dse_quarterly' | 'audit_report' | 'custom'
is_active BOOLEAN NOT NULL DEFAULT TRUE,
custom_note TEXT,
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE compliance_events (
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
obligation_type VARCHAR(64) NOT NULL,
period_label VARCHAR(32), -- e.g. '2024-01', 'FY2023-24', 'Q1 FY2024'
due_date DATE NOT NULL,
status VARCHAR(32) NOT NULL DEFAULT 'pending',
-- 'pending' | 'filed' | 'overdue' | 'waived' | 'not_applicable'
filed_date DATE,
penalty_risk_bdt DECIMAL(15, 2),
notes TEXT,
reminder_30d_sent BOOLEAN DEFAULT FALSE,


reminder_7d_sent BOOLEAN DEFAULT FALSE,
reminder_1d_sent BOOLEAN DEFAULT FALSE,
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_due ON compliance_events(due_date, status);
CREATE INDEX idx_events_client ON compliance_events(client_id, status);

CREATE TABLE documents (
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
original_filename VARCHAR(512) NOT NULL,
storage_path TEXT NOT NULL, -- S3/MinIO path
file_size_bytes INTEGER,
mime_type VARCHAR(64),
doc_type VARCHAR(64),
-- 'mushak_61' | 'mushak_62' | 'mushak_63' | 'mushak_91' |
-- 'bank_statement' | 'nbr_notice' | 'tds_certificate' |
-- 'trade_licence' | 'tin_certificate' | 'invoice' | 'unknown'
source VARCHAR(32) DEFAULT 'portal',
-- 'portal' | 'email' | 'api' | 'manual'
processing_status VARCHAR(32) NOT NULL DEFAULT 'queued',
-- 'queued' | 'processing' | 'extracted' | 'error' | 'review_needed'
ocr_engine_used VARCHAR(32),
-- 'tesseract' | 'google_vision' | 'pdfplumber' | 'none'
ocr_confidence DECIMAL(5, 2), -- 0.00 to 100.
extracted_data JSONB, -- Structured extraction result
extraction_errors JSONB, -- Fields with low confidence
processing_error TEXT,
uploaded_by UUID, -- NULL if uploaded via client portal
is_client_upload BOOLEAN NOT NULL DEFAULT FALSE,
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_docs_client ON documents(client_id);
CREATE INDEX idx_docs_type_status ON documents(doc_type, processing_status);

-- ============================================================
-- VAT RECONCILIATION
-- ============================================================

CREATE TABLE vat_reconciliations (
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
period CHAR(7) NOT NULL, -- 'YYYY-MM' format


status VARCHAR(32) NOT NULL DEFAULT 'running',
-- 'running' | 'completed' | 'error' | 'archived'
total_invoices INTEGER,
matched_exact INTEGER,
matched_fuzzy INTEGER,
partial_match INTEGER,
no_match INTEGER,
itc_risk_bdt DECIMAL(15, 2),
purchase_register_doc_id UUID REFERENCES documents(id),
supplier_data_doc_id UUID REFERENCES documents(id),
summary_notes TEXT,
run_by UUID NOT NULL,
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
completed_at TIMESTAMPTZ,

UNIQUE(client_id, period)
);

CREATE TABLE recon_line_items (
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
reconciliation_id UUID NOT NULL REFERENCES vat_reconciliations(id) ON DELETE CASCADE,
-- Purchase register data (what CA has)
pr_invoice_no VARCHAR(64),
pr_supplier_bin VARCHAR(9),
pr_supplier_name VARCHAR(255),
pr_invoice_date DATE,
pr_taxable_amount DECIMAL(15, 2),
pr_vat_amount DECIMAL(15, 2),
-- Supplier-filed data (what NBR has)
sf_invoice_no VARCHAR(64),
sf_invoice_date DATE,
sf_taxable_amount DECIMAL(15, 2),
sf_vat_amount DECIMAL(15, 2),
-- Match result
match_status VARCHAR(32) NOT NULL,
-- 'exact' | 'fuzzy' | 'partial' | 'no_match'
match_score DECIMAL(5, 2), -- 0.00 to 1.
discrepancy_flags JSONB,
-- e.g. {"date_off_by_days": 2, "amount_diff": 50.00}
ca_override VARCHAR(32),
-- If CA manually overrides: 'approved' | 'disputed' | 'ignore'
ca_notes TEXT,
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_recon_items_recon ON recon_line_items(reconciliation_id);
CREATE INDEX idx_recon_items_status ON recon_line_items(match_status);


## PART 6: API DESIGN — CONVENTIONS

### 6.1 Base URL and Versioning

```
/api/v1/{resource}
```
### 6.2 Authentication

#### All endpoints except /api/v1/auth/login and /api/v1/auth/register and

#### /api/v1/portal/* require:

##### -- ============================================================

##### -- NBR NOTICES

##### -- ============================================================

```
CREATE TABLE nbr_notices (
id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
document_id UUID REFERENCES documents(id),
notice_type VARCHAR(64),
-- 'show_cause_vat' | 'assessment_income_tax' | 'demand_vat' |
-- 'audit_vat' | 'interest_vat' | 'tds_default'
assessment_year VARCHAR(9), -- e.g. '2023-2024'
demand_amount_bdt DECIMAL(15, 2),
demand_currency VARCHAR(3) DEFAULT 'BDT',
response_deadline DATE,
grounds TEXT[], -- Array of ground descriptions
extracted_data JSONB, -- Full extracted notice data
ai_draft_reply TEXT, -- LLM-generated draft
ai_draft_version INTEGER DEFAULT 1,
ai_draft_legal_sections TEXT[], -- Sections cited by AI
ca_edited_reply TEXT, -- CA's final edited version
status VARCHAR(32) NOT NULL DEFAULT 'received',
-- 'received' | 'in_progress' | 'draft_ready' | 'responded' | 'closed'
responded_date DATE,
created_by UUID NOT NULL,
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
```
CREATE INDEX idx_notices_client ON nbr_notices(client_id, status);
CREATE INDEX idx_notices_deadline ON nbr_notices(response_deadline) WHERE status != 'closed';
```

```
Authorization: Bearer <jwt_token>
```
#### JWT payload must contain:

##### {

```
"sub": "user_uuid",
"tenant_id": "tenant_uuid",
"schema_name": "tenant_a1b2c3",
"role": "senior_ca",
"exp": 1234567890
}
```
### 6.3 Standard Response Format

#### Success:

##### {

```
"success": true,
"data": { ... },
"meta": {
"page": 1,
"per_page": 20,
"total": 150
}
}
```
#### Error:

##### {

```
"success": false,
"error": {
"code": "DOCUMENT_NOT_FOUND",
"message": "Document with ID abc123 not found in this workspace.",
"details": {}
}
}
```
### 6.4 Error Codes (Custom)

#### Define these in app/core/exceptions.py:

##### TENANT_NOT_FOUND = "TENANT_NOT_FOUND"

##### UNAUTHORIZED = "UNAUTHORIZED"


##### FORBIDDEN = "FORBIDDEN"

##### DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"

##### DOCUMENT_PROCESSING = "DOCUMENT_STILL_PROCESSING"

##### OCR_FAILED = "OCR_EXTRACTION_FAILED"

##### INVALID_BIN = "INVALID_BIN_FORMAT"

##### INVALID_TIN = "INVALID_TIN_FORMAT"

##### RECONCILIATION_RUNNING = "RECONCILIATION_ALREADY_RUNNING"

##### CLIENT_NOT_FOUND = "CLIENT_NOT_FOUND"

##### NOTICE_NOT_FOUND = "NOTICE_NOT_FOUND"

##### AI_DRAFT_FAILED = "AI_DRAFT_GENERATION_FAILED"

##### PLAN_LIMIT_EXCEEDED = "PLAN_LIMIT_EXCEEDED"

### 6.5 Complete Endpoint Map (MVP)

##### # AUTH

```
POST /api/v1/auth/register # New firm registration
POST /api/v1/auth/login # Returns access + refresh tokens
POST /api/v1/auth/refresh # Refresh access token
POST /api/v1/auth/logout
```
```
# TENANT (Firm Settings)
GET /api/v1/tenant/profile
PUT /api/v1/tenant/profile
GET /api/v1/tenant/team
POST /api/v1/tenant/team/invite
DELETE /api/v1/tenant/team/{user_id}
```
```
# CLIENTS
GET /api/v1/clients # ?search=&entity_type=&page=&per_page=
POST /api/v1/clients
GET /api/v1/clients/{id}
PUT /api/v1/clients/{id}
DELETE /api/v1/clients/{id} # Soft delete
POST /api/v1/clients/{id}/portal-invite # Send portal access link
GET /api/v1/clients/{id}/obligations
POST /api/v1/clients/{id}/obligations
DELETE /api/v1/clients/{id}/obligations/{obligation_id}
```
```
# DOCUMENTS
POST /api/v1/documents/upload # Multipart, max 20MB
GET /api/v1/documents # ?client_id=&doc_type=&status=&page=
GET /api/v1/documents/{id}
GET /api/v1/documents/{id}/download
DELETE /api/v1/documents/{id} # Soft delete
POST /api/v1/documents/{id}/reprocess # Re-run OCR
```

##### # RECONCILIATION

```
POST /api/v1/reconciliations # Trigger new reconciliation
GET /api/v1/reconciliations # ?client_id=&period=&page=
GET /api/v1/reconciliations/{id}
GET /api/v1/reconciliations/{id}/items # ?match_status=&page=
PUT /api/v1/reconciliations/{id}/items/{item_id} # CA override
GET /api/v1/reconciliations/{id}/export # ?format=xlsx|pdf
```
```
# NBR NOTICES
POST /api/v1/notices/upload # Upload notice PDF
GET /api/v1/notices # ?client_id=&status=&page=
GET /api/v1/notices/{id}
PUT /api/v1/notices/{id} # Update status, save CA reply
POST /api/v1/notices/{id}/regenerate-draft # Re-run AI draft
```
##### # COMPLIANCE CALENDAR

```
GET /api/v1/calendar # ?client_id=&from=&to=&status=
GET /api/v1/calendar/upcoming # Next 30 days, all clients
PUT /api/v1/calendar/{event_id} # Update status
POST /api/v1/calendar/custom # Add custom deadline
```
##### # REPORTS

```
POST /api/v1/reports/mis # Generate MIS report
GET /api/v1/reports # List generated reports
GET /api/v1/reports/{id}/download
```
```
# CLIENT PORTAL (unauthenticated except portal token)
GET /api/v1/portal/{token} # Portal landing (verify token)
POST /api/v1/portal/{token}/upload # Client document upload
GET /api/v1/portal/{token}/status # Client's compliance status
GET /api/v1/portal/{token}/deadlines # Client's upcoming deadlines
```
## PART 7: CORE BUSINESS LOGIC — DETAILED SPECS

### 7.1 D o c u m e n t P r o c e s s i n g P i p e l i n e

#### This is the heart of the system. Every document goes through this exact flow:

```
# documents/tasks.py — Celery task
@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def process_document(self, document_id: str, tenant_schema: str):
"""
Full document processing pipeline.
Runs asynchronously after upload.
```

##### """

```
# 1. Fetch document record from DB
# 2. Download file from S3/MinIO
# 3. Determine processing strategy by MIME type:
# - PDF (text-based): pdfplumber → extract text → LLM extraction
# - PDF (image-based/scanned): pdf2image → each page → OCR pipeline
# - Image (JPEG/PNG/WEBP): OCR pipeline directly
# - Excel/CSV: pandas parse → map columns
# 4. Run OCR pipeline (see below)
# 5. Run field extractor based on detected doc_type
# 6. Calculate confidence scores
# 7. Save extracted_data + confidence to DB
# 8. Update document status
# 9. Trigger downstream notifications (websocket or polling)
```
#### OCR Pipeline (documents/ocr/engine.py):

#### MushaK 6.2 Extractor (ocr/extractors/mushak_62.py):

```
class OCREngine:
CONFIDENCE_THRESHOLD_TESSERACT = 80.
```
```
def extract(self, image_bytes: bytes, language: str = "ben+eng") -> OCRResult:
"""
```
1. Preprocess image (preprocessor.py)
2. Run Tesseract
3. If confidence < threshold → fallback to Google Vision
4. Return OCRResult with text, confidence, bounding boxes
"""

```
def preprocess(self, image_bytes: bytes) -> bytes:
"""
OpenCV pipeline:
```
1. Convert to grayscale
2. Deskew (detect and correct rotation)
3. Denoise (fastNlMeansDenoising)
4. Binarize (Otsu's thresholding)
5. Remove borders/shadows
Return processed image bytes
"""

##### MUSHAK_62_FIELDS = {

```
"seller_bin": {"pattern": r"িবআইএন[:\s]+(\d{9})", "type": "bin", "required": True},
"seller_name": {"type": "text", "required": True},
"buyer_bin": {"pattern": r"./তার\s+িবআইএন[:\s]+(\d{9})", "type": "bin"},
"invoice_no": {"type": "text", "required": True},
```

### 7. 2 VAT R e c o n c i l i a t i o n E n g i n e

#### This is the highest-stakes module. Implement it defensively.

```
"invoice_date": {"type": "date", "format": "DD/MM/YYYY", "required": True},
"hs_code": {"pattern": r"এইচএস\s+.কাড[:\s]+(\d{4}\.\d{2})", "type": "text"},
"description": {"type": "text", "required": True},
"quantity": {"type": "number"},
"unit_price": {"type": "currency", "required": True},
"taxable_value": {"type": "currency", "required": True},
"vat_amount": {"type": "currency", "required": True},
"total_amount": {"type": "currency", "required": True},
}
```
```
# Validation: vat_amount should be approximately taxable_value * 0.
# Flag if difference > 1% as potential extraction error
```
```
# reconciliation/engine.py
```
```
class VATReconciliationEngine:
"""
Reconciles purchase register against supplier-filed VAT returns.
```
```
Input:
```
- purchase_register: List of InvoiceRecord (from Mushak 6.2 or uploaded Excel)
- supplier_returns: List of InvoiceRecord (uploaded by CA from NBR portal export)

```
Output:
```
- ReconciliationReport with per-invoice match results
"""

```
# Matching thresholds
FUZZY_DATE_TOLERANCE_DAYS = 3
FUZZY_AMOUNT_TOLERANCE_PCT = 0.5 # 0.5% difference allowed
EXACT_SCORE = 1.
FUZZY_SCORE = 0.
PARTIAL_SCORE = 0.
NO_MATCH_SCORE = 0.
```
```
def match_invoice(
self,
pr_invoice: InvoiceRecord, # From purchase register
supplier_pool: list[InvoiceRecord] # All supplier-filed invoices with same BIN
) -> MatchResult:
"""
Match priority (in order):
```

#### Reconciliation Report Output:

```
class ReconciliationReport(BaseModel):
period: str # 'YYYY-MM'
run_at: datetime
total_invoices: int
matched_exact: int
matched_fuzzy: int
partial_match: int
no_match: int
total_vat_claimed: Decimal # BDT
safe_itc: Decimal # From exact + fuzzy matches
at_risk_itc: Decimal # From partial + no_match
flagged_suppliers: list[str] # BINs with no_match
line_items: list[ReconLineItem]
```
```
# Computed property
```
1. EXACT: BIN + invoice_no (normalized) + date (exact) + amount (exact)
→ auto_approve, no CA review needed
2. FUZZY: BIN + invoice_no (normalized) + date within ±3 days
+ amount within ±0.5%
→ suggest_approve, flag discrepancy details
3. PARTIAL: Only BIN matches
→ manual_review, high ITC risk flag
4. NO_MATCH: BIN not found in supplier pool at all
→ flag_supplier, critical ITC risk

```
Invoice number normalization:
```
- Remove spaces, hyphens, leading zeros
- Lowercase
- e.g. "INV-0023/2024" → "inv0023/2024"

```
IMPORTANT: A no_match result means potential ITC disallowance.
The CA must be clearly warned. Do not soften this message.
"""
```
```
def calculate_itc_risk(self, line_items: list[MatchResult]) -> Decimal:
"""
ITC risk = sum of vat_amount for all no_match + partial_match items
This is the maximum amount NBR could disallow.
"""
```

```
@property
def risk_percentage(self) -> float:
if self.total_vat_claimed == 0:
return 0
return float(self.at_risk_itc / self.total_vat_claimed * 100)
```
### 7. 3 N B R N o t i c e A I M o d u l e

```
# notices/drafter.py
```
##### NOTICE_SYSTEM_PROMPT = """

```
You are an expert Bangladeshi tax consultant assisting a Chartered Accountant
registered with ICAB (Institute of Chartered Accountants of Bangladesh).
```
```
You are drafting a FORMAL LEGAL RESPONSE to an NBR (National Board of Revenue) notice.
```
```
CRITICAL RULES:
```
1. Cite ONLY these laws (do not invent section numbers):
- VAT and Supplementary Duty Act, 2012
- Income Tax Ordinance, 1984 (and applicable Finance Act year)
- Companies Act, 1994
2. Structure the reply EXACTLY as:
[Date]
To: The Deputy Commissioner of Taxes / VAT Circle Officer
Subject: Reply to [Notice Type] dated [Date], Reference: [Ref No]

```
Respectful Introduction
Point-by-point responses to each ground raised
Supporting facts from provided financial data
Legal citations for each point
Closing prayer / request
```
3. DO NOT make up financial figures. Use ONLY the data provided in the context.
4. Mark any section where CA must INSERT specific figures with: [[INSERT: description]]
5. If a ground in the notice cannot be addressed with available data,
explicitly state: [[INSUFFICIENT DATA: explain what is needed]]
6. Language: Formal English. Client name should appear as provided.
7. This is a DRAFT. The CA will review and modify before sending.

```
Output format: Plain text, ready to paste into a letterhead document.
"""
```
```
def generate_notice_reply(
notice_data: NoticeExtract, # Extracted notice details
client_financials: dict, # Relevant financial data from DB
```

### 7. 4 C o m p l i a n c e C a l e n d a r E n g i n e

```
legal_db: BDLegalDatabase # Reference tax law database
) -> str:
"""
Build context from notice_data + client_financials.
Call Claude API with NOTICE_SYSTEM_PROMPT.
Validate output contains no hallucinated section numbers.
Return draft text.
"""
```
```
# calendar/bd_deadlines.py
```
```
class BangladeshDeadlines:
"""
Single source of truth for all Bangladesh regulatory deadlines.
Updated after each Finance Act (annual review required).
Last updated: Finance Act 2024.
"""
```
##### MONTHLY_OBLIGATIONS = {

```
"vat_return": {
"name": "VAT Return (Mushak 9.1)",
"law": "VAT Act 2012, Section 64",
"due": lambda year, month: date(year, month, 15) + relativedelta(months=1),
"penalty_per_day": Decimal("250.00"), # BDT per day late
"applies_to": ["company", "partnership"],
"requires": "bin"
},
"tds_return": {
"name": "TDS Return",
"law": "ITO 1984, Section 75A",
"due": lambda year, month: date(year, month, 20) + relativedelta(months=1),
"penalty_per_month": Decimal("5000.00"),
"applies_to": "all"
},
"tds_deposit": {
"name": "TDS Challan Deposit",
"law": "ITO 1984, Section 58",
"due": lambda year, month: date(year, month, 7) + relativedelta(months=1),
"interest_rate": Decimal("0.02"), # 2% per month on delayed amount
"applies_to": "all"
},
}
```
##### ANNUAL_OBLIGATIONS = {


## PART 8: AI INTEGRATION GUIDELINES

### 8.1 Claude API Wrapper

```
# ai/claude_client.py
```
```
class ClaudeClient:
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
```
```
"income_tax_company": {
"name": "Company Income Tax Return",
"law": "ITO 1984, Section 75",
"due_rule": "15_jan_after_fy_end", # 15th Jan following June FY end
"penalty": "1% per month of tax payable",
"applies_to": ["company"]
},
"income_tax_individual": {
"name": "Individual Income Tax Return",
"law": "ITO 1984, Section 75",
"due": date(2025, 11, 30), # 30th November annually
"applies_to": ["individual"]
},
"rjsc_annual_return": {
"name": "RJSC Annual Return",
"law": "Companies Act 1994, Section 190",
"due_rule": "21_days_after_agm",
"penalty": "BDT 500 per day default",
"applies_to": ["company"]
},
}
```
```
def generate_events_for_client(
self,
client: Client,
from_date: date,
to_date: date
) -> list[ComplianceEvent]:
"""
Generate all due dates for a client for the given date range.
Creates one ComplianceEvent per obligation per period.
"""
```

```
def __init__(self):
self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
```
```
async def complete(
self,
system: str,
user: str,
max_tokens: int = 2048,
temperature: float = 0.2 # Low temperature for legal/financial tasks
) -> str:
"""
Wraps Claude API call.
Handles rate limits with exponential backoff.
Logs token usage for billing tracking.
Never raises — returns error string if failed.
"""
```
```
async def extract_structured(
self,
prompt: str,
output_schema: dict,
fallback: dict = None
) -> dict:
"""
Asks Claude to return JSON matching output_schema.
Validates output against schema.
Returns fallback on failure.
Always wraps extraction prompts with:
'Respond with ONLY valid JSON. No explanation, no markdown.'
"""
```
### 8.2 Prompt Engineering Rules

#### Every prompt file in ai/prompts/ must:

#### 1. Start with explicit role definition (who Claude is in this context)

#### 2. Include Bangladesh-specific regulatory context relevant to that task

#### 3. Have explicit output format instructions

#### 4. Include a “CRITICAL RULES” section for safety constraints

#### 5. Be tested against at least 5 real examples before deployment

#### To ke n b u d g e t g u i d e l i n e s :

#### Notice drafting: 2,000–3,000 tokens output


#### MIS narrative: 1,000–1,500 tokens output

#### Document extraction: 500–800 tokens output

#### Classification: 200 tokens output (JSON only)

### 8.3 LLM Output Validation

#### All LLM outputs must go through validation before being saved or shown to users:

## PART 9: SECURITY REQUIREMENTS

#### These are non-negotiable. Every single one must be implemented in MVP.

### 9.1 Tenant Isolation

```
# dependencies.py
```
```
async def get_tenant_db_session(
token: str = Depends(oauth2_scheme),
db: AsyncSession = Depends(get_db)
```
```
# ai/validators.py
```
```
def validate_notice_draft(draft_text: str, notice_type: str) -> ValidationResult:
"""
Check:
```
1. Draft contains required structural elements (To:, Subject:, date, closing)
2. No obviously fake section numbers cited
(check against KNOWN_BD_TAX_SECTIONS list)
3. Draft is in English (not Bangla for formal legal replies)
4. Draft mentions client name/reference
5. All [[INSERT: ...]] tags are present and readable

```
If validation fails → return with warnings, do NOT block showing draft
but flag clearly to CA
"""
```
```
KNOWN_BD_TAX_SECTIONS = {
"vat_2012": ["Section 2", "Section 37", "Section 55", "Section 63", "Section 64"],
"ito_1984": ["Section 52", "Section 56", "Section 58", "Section 75", "Section 75A",
"Section 83", "Section 137"],
# Extend this list — do not hallucinate sections
}
```

```
) -> AsyncGenerator[AsyncSession, None]:
"""
CRITICAL: Every database session for tenant operations
must be scoped to that tenant's schema.
```
```
DO: SET search_path TO tenant_a1b2c3, public
DO: Validate that resource.tenant_id matches JWT tenant_id
DON'T: Allow any query that crosses tenant schemas
"""
payload = verify_jwt(token)
schema = payload["schema_name"]
await db.execute(text(f"SET search_path TO {schema}, public"))
yield db
```
### 9.2 Document Encryption

### 9.3 Input Validation

```
# Every API input must be validated:
# - BIN: Must match ^\d{9}$
# - TIN: Must match ^\d{12}$
# - Dates: ISO 8601 format, not in far future
# - Currency amounts: Must be positive Decimal, max 15 digits before decimal
# - File uploads: Validate MIME type server-side (not just extension)
# Allowed: application/pdf, image/jpeg, image/png, image/webp,
# application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,
# text/csv
# - Max file size: 20MB
# - Filenames: Sanitize with pathlib, reject path traversal attempts
```
### 9.4 Rate Limiting

```
# All documents in S3/MinIO must be:
# 1. Stored with server-side encryption (AES-256)
# 2. Paths must be non-guessable (UUID-based, not sequential)
# 3. Presigned URLs expire in 15 minutes
# 4. Direct S3 access never exposed to frontend — always proxy through API
```
```
def generate_secure_storage_path(tenant_id: str, doc_id: str, filename: str) -> str:
ext = Path(filename).suffix
return f"tenants/{tenant_id}/documents/{doc_id}{ext}"
# NEVER use original filename in the storage path
```

```
# Per-tenant limits (stored in Redis):
RATE_LIMITS = {
"document_upload": "50/hour",
"ai_notice_draft": "20/hour",
"reconciliation_run": "10/hour",
"api_global": "500/hour",
}
```
## PART 10: DEVELOPMENT EXECUTION ORDER

#### This is the order in which to build. Do not skip ahead. Each phase produces a working,

#### testable system.

### Phase A: Foundation (Build First — Everything Depends on This)

1. Docker Compose setup
- PostgreSQL 15
- Redis 7
- MinIO
- Backend (FastAPI, hot reload)
- Frontend (Vite dev server)
2. Database foundation
- Alembic setup
- Public schema: tenants, users
- Tenant schema creation function
- Schema migration on tenant registration
3. Authentication
- Register endpoint (creates tenant + admin user + tenant schema)
- Login endpoint (JWT access + refresh tokens)
- JWT middleware
- Role-based access decorator
4. Tenant infrastructure
- Tenant DB session with schema switching
- Tenant isolation middleware
- Basic tenant profile endpoints

```
ACCEPTANCE: Can register a firm, login, get a JWT, make authenticated API calls.
All tenant data goes into correct schema. Cross-tenant access returns 403.
```

### Phase B: Client Management

5. Clients CRUD
- Create, read, update, delete clients
- BIN/TIN validation
- Client search/filter
6. Compliance obligations setup
- Assign obligations to clients
- Compliance calendar generation
- Basic calendar view API

```
ACCEPTANCE: Can add 10 clients with different entity types.
Each client has a compliance calendar populated with correct BD deadlines.
```
### Phase C: Document Intelligence (Highest Complexity — Budget More Time)

7. File upload infrastructure
- MinIO/S3 abstraction layer
- Presigned URL generation
- Document model and status tracking
8. Celery worker setup
- Worker connects to Redis
- Basic task routing
- Task result tracking
9. OCR engine
- Tesseract integration with ben+eng packs
- OpenCV preprocessing pipeline
- Confidence scoring
- Google Vision API fallback (with feature flag to disable in dev)
10. Document type detection
- Classify uploaded document by type
- Route to appropriate extractor
11. Mushak 6.2 extractor (MVP's most critical extractor)
- Field extraction with regex + LLM hybrid approach
- Bangla numeral normalization
- Confidence scoring per field
- Validation (VAT = taxable * 0.15 check)
12. Bank statement parser
- Support at least: BRAC Bank, Dutch-Bangla Bank templates


- Transaction categorization

```
ACCEPTANCE: Upload a MushaK 6.2 form photo. System extracts all fields with
confidence scores. BIN and invoice number are correctly extracted.
Confidence < 85% fields are flagged for review.
```
### Phase D: Reconciliation Engine

13. Reconciliation data models and API
14. Core matching algorithm (exact → fuzzy → partial → no_match)
15. Reconciliation report generation
16. Excel export
17. CA override functionality

```
ACCEPTANCE: Upload a purchase register (Excel) and a supplier return export.
System reconciles 100 invoices in < 30 seconds.
Report shows correct breakdown with match types.
CA can override individual matches.
```
### Phase E: NBR Notice Assistant

18. Notice upload + OCR pipeline
19. Notice classification (rule-based + LLM)
20. Notice data extraction (type, demand, deadline, grounds)
21. AI draft reply generation
22. BD legal section validator
23. Notice status tracking

```
ACCEPTANCE: Upload a real NBR VAT show-cause notice PDF.
System correctly identifies notice type, demand amount, and deadline.
AI generates a structured draft reply with correct legal citations.
Draft is clearly labelled as AI-generated, awaiting CA review.
```
### Phase F: Frontend

24. React app scaffold with routing
25. Auth pages (login, register)
26. Dashboard (overview: upcoming deadlines, recent docs, stats)
27. Client list and detail pages
28. Document upload + status tracking UI
29. Reconciliation results view
30. Notice management UI
31. Compliance calendar view


```
ACCEPTANCE: Full end-to-end flow works in browser.
CA can register, add clients, upload MushaK, see reconciliation results,
view notices with AI drafts, and see compliance calendar.
```
### Phase G: Notifications + Polish

32. Email notifications (SendGrid)
33. Compliance deadline reminders (Celery beat scheduler)
34. Client portal (separate simple Next.js app)
35. MIS report generator

## PART 11: CODE QUALITY STANDARDS

### 11.1 Non-Negotiables

#### Type hints everywhere. No untyped Python functions. Use Pydantic models for all

#### inputs/outputs.

#### Async all the way. All DB calls, HTTP calls, and file I/O must be async. No blocking calls

#### in FastAPI routes.

#### Never trust user input. Every field from every source (upload, API, portal) goes through

#### Pydantic validation.

#### Log but don’t expose. Log errors with full traceback internally. API errors return only

#### the error.code and a safe message — never stack traces.

#### Te s t b u s i n e s s l o g i c. Every function in reconciliation/engine.py,

#### calendar/bd_deadlines.py, ocr/extractors/, and ai/validators.py must have unit

#### tests. Target 85%+ coverage on these files.

### 11.2 Naming Conventions

```
# Bangladesh-specific field names — use these exact names everywhere
# for consistency across DB, API, and frontend:
```
```
tin # Not 'taxpayer_id' or 'tax_number'
bin # Not 'vat_reg' or 'vat_number' — always 'bin'
mushak_no # The MushaK form number
nbr # Always uppercase abbreviation
ito_1984 # Reference to Income Tax Ordinance
```

```
bdt # BDT suffix for all monetary fields denominated in Taka
```
```
# Example:
class Invoice(BaseModel):
invoice_no: str
seller_bin: str # NOT seller_vat_id
buyer_bin: Optional[str]
taxable_value_bdt: Decimal # NOT taxable_amount
vat_amount_bdt: Decimal # NOT tax_amount
```
### 11.3 Configuration

```
# config.py — All configuration via environment variables
class Settings(BaseSettings):
# Database
DATABASE_URL: str
```
```
# Redis
REDIS_URL: str
```
```
# Storage
MINIO_ENDPOINT: str = "localhost:9000"
MINIO_ACCESS_KEY: str
MINIO_SECRET_KEY: str
MINIO_BUCKET: str = "hishabai-documents"
USE_S3: bool = False # Switch to True for production AWS S3
```
```
# AI
ANTHROPIC_API_KEY: str
GOOGLE_VISION_API_KEY: Optional[str] = None
ENABLE_GOOGLE_VISION_FALLBACK: bool = False # Off by default in dev
```
```
# SMS (Bangladesh)
SSL_WIRELESS_API_KEY: Optional[str] = None
ENABLE_SMS: bool = False # Off by default
```
```
# App
JWT_SECRET_KEY: str
JWT_ACCESS_EXPIRE_MINUTES: int = 60
JWT_REFRESH_EXPIRE_DAYS: int = 30
MAX_UPLOAD_SIZE_MB: int = 20
```
```
# Feature flags
FEATURE_CLIENT_PORTAL: bool = True
FEATURE_MIS_REPORTS: bool = True
FEATURE_GOOGLE_VISION: bool = False
```

```
class Config:
env_file = ".env"
```
## PART 12: WHAT NOT TO BUILD (SCOPE GUARD)

#### Read this before starting any new feature. If it’s on this list, it’s Phase 2+. Do not touch it in

#### MVP.

#### Direct NBR portal filing — HishabAI prepares, CA files manually. E-signature

#### integration — Out of scope. Payroll module — Separate product entirely. Mobile

#### native app — Web-responsive is sufficient for MVP. Ta l l y d i r e c t i n t e g r a t i o n — Use

#### Excel/CSV import for MVP. Custom AI model training — Use Claude API. Fine-tuning is

#### Phase 3. WhatsApp Business API integration — Portal is the document channel for

#### MVP. Audit management — Full audit workflow is separate from compliance workflow.

#### Multi-currency support — BDT only for MVP. DSE/CSE listed company specific

#### reporting — Too niche for MVP. Automatic BIN lookup scraping — Manual BIN entry

#### with format validation only.

## PART 13: HOW TO START

#### When you begin working on this, do the following in order:

#### 1. Read this entire document. Not skimming — reading. Re-read Part 2 (Bangladesh

#### regulatory context) twice.

#### 2. Ask yourself: “What are the 3 most critical things that could go wrong in this system

#### that would destroy a CA’s client relationship?” Answer: (a) Cross-tenant data leakage,

#### (b) Incorrect ITC risk calculation, (c) Wrong legal citations in notice replies. Build

#### defenses against all three on day one.

#### 3. Start with docker-compose.yml. Get the entire infrastructure running locally in one

#### command before writing any application code.

#### 4. Build the data model before the API. Get the schemas right. Changing a schema after

#### data exists is painful. Changing an API after the schema is stable is easy.

#### 5. When writing AI prompts: Test every prompt with at least 3 real examples of

#### Bangladeshi tax documents before considering it done. The prompts are as important as

#### the code.


#### 6. Every time you complete a Phase (A through G): Run through the Acceptance

#### Criteria. If anything fails, fix it before moving to the next phase.

## FINAL REMINDERS

#### The currency is BDT (Bangladeshi Taka), symbol ৳ (U+09F3).

#### The fiscal year runs July 1 to June 30. “FY 2024” means July 2023 – June 2024.

#### Bangla/Bengali is an official language of Bangladesh. Forms, notices, and UI elements

#### should support Bangla text rendering. Use UTF-8 everywhere.

#### CAs in Bangladesh are registered with ICAB — not ACCA, ICAI, or any other body.

#### Always refer to ICAB.

#### NBR = National Board of Revenue (tax authority, Bangladesh)

#### RJSC = Registrar of Joint Stock Companies and Firms

#### DSE = Dhaka Stock Exchange

#### When in doubt about any Bangladesh-specific regulatory detail, flag it with:

```
# REGULATORY_REVIEW_NEEDED: [describe what needs verification]
# Source: [cite the law/section if known, or 'Unknown - needs expert review']
```
#### Do not silently assume. Do not guess about legal rules. Flag and continue.

#### This prompt is the single source of truth for HishabAI’s MVP build.

#### Version 1.0 | Product: HishabAI | Audience: Claude Opus 4.6


