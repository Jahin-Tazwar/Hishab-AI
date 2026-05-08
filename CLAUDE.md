# HishabAI — AI Assistant Guidelines

Welcome to HishabAI! This document outlines the project's architecture, tech stack, and coding conventions. As an AI assistant, you should adhere to these guidelines to maintain a high-quality, consistent codebase.

## 1. Project Overview
HishabAI is a multi-tenant SaaS platform built for Bangladeshi Chartered Accountancy (CA) firms. It automates unstructured data handling, VAT reconciliation, compliance deadline tracking, and NBR (National Board of Revenue) notice drafting.

## 2. Technology Stack

### Backend
*   **Language:** Python 3.11+ (Strictly asynchronous)
*   **Framework:** FastAPI
*   **Database & Auth:** Supabase (PostgreSQL, GoTrue for Auth, Storage)
*   **DB Clients:** `supabase-py` (for auth/storage), `asyncpg` + `SQLAlchemy 2.0` (for complex DB queries)
*   **Task Queue:** Celery 5 + Redis (for asynchronous OCR and AI tasks)
*   **AI/LLM:** Google Vertex AI (Gemini 2.5 Flash)
*   **OCR/Document Parsing:** Tesseract 5, `pdfplumber`, `opencv-python-headless`

### Frontend
*   **Framework:** React 18 + TypeScript + Vite
*   **State Management:** Zustand
*   **UI/Styling:** shadcn/ui + Tailwind CSS
*   **Supabase Client:** `@supabase/supabase-js`

## 3. Core Architectural Principles

1.  **Multi-Tenancy & Security:** Multi-tenancy is strictly enforced at the database level using Supabase Row-Level Security (RLS). Every tenant-scoped table MUST have a `tenant_id` column. Never bypass RLS in the backend unless explicitly required for system-level background jobs.
2.  **Asynchronous by Default:** All I/O operations (Database, HTTP, File reads/writes) in the backend must be asynchronous.
3.  **Strict Validation & Typing:**
    *   Backend: Use Pydantic models for all data validation (inputs/outputs) and include type hints on all functions.
    *   Frontend: Use Zod for form validation and strict TypeScript typing.
4.  **Error Handling & Logging:** Log errors internally using `structlog`. Return safe, generic error codes and messages to the API client without exposing internal stack traces.

## 4. Naming Conventions & Terminology

Strictly adhere to the following naming conventions related to Bangladeshi tax terminology:
*   `tin` (Not `taxpayer_id` or `tax_number`)
*   `bin` (Not `vat_reg` — always `bin`)
*   `mushak_no` (Refers to the MushaK form number)
*   `nbr` (Always uppercase, stands for National Board of Revenue)
*   `bdt` (Suffix for all monetary fields in Bangladeshi Taka, e.g., `total_amount_bdt`)

## 5. Directory Structure

*   `docs/`: Product specs, API documentation, architecture, and business logic.
*   `backend/`:
    *   `app/`: FastAPI application code (divided by domains like `tenants/`, `clients/`, `documents/`, `reconciliation/`, `notices/`, `calendar/`).
    *   `tests/`: Pytest test suite (aim for 85%+ coverage on business logic).
*   `frontend/`: React + Vite application.

## 6. Code Quality Standards

*   Ensure comprehensive test coverage for all new business logic.
*   Maintain clean, documented code. Use docstrings for complex logic.
*   Follow PEP 8 for Python and standard ESLint/Prettier rules for TypeScript/React.
*   Use Playwright tool to automate browser usage.
