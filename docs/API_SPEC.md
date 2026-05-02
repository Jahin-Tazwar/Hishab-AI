# HishabAI — API Specification

## Base URL: `/api/v1/{resource}`

## Authentication

**Auth is handled by Supabase Auth (GoTrue).** The frontend uses `@supabase/supabase-js`
for sign up, login, and session management. The backend validates Supabase JWTs.

All API endpoints require:
```
Authorization: Bearer <supabase_jwt_token>
```

The backend extracts the user ID from the JWT's `sub` claim, looks up the user's
`tenant_id` from `user_profiles`, and scopes all queries via RLS.

## Response Format

**Success:**
```json
{"success": true, "data": {}, "meta": {"page": 1, "per_page": 20, "total": 150}}
```

**Error:**
```json
{"success": false, "error": {"code": "DOCUMENT_NOT_FOUND", "message": "...", "details": {}}}
```

## Error Codes

`TENANT_NOT_FOUND`, `UNAUTHORIZED`, `FORBIDDEN`, `DOCUMENT_NOT_FOUND`,
`DOCUMENT_STILL_PROCESSING`, `OCR_EXTRACTION_FAILED`, `INVALID_BIN_FORMAT`,
`INVALID_TIN_FORMAT`, `RECONCILIATION_ALREADY_RUNNING`, `CLIENT_NOT_FOUND`,
`NOTICE_NOT_FOUND`, `AI_DRAFT_GENERATION_FAILED`, `PLAN_LIMIT_EXCEEDED`

## Endpoints

### Onboarding (after Supabase Auth sign-up)
- `POST /api/v1/onboard` — Create tenant + user_profile for newly authenticated user

### Tenant (Firm Settings)
- `GET /api/v1/tenant/profile`
- `PUT /api/v1/tenant/profile`
- `GET /api/v1/tenant/team`
- `POST /api/v1/tenant/team/invite`
- `DELETE /api/v1/tenant/team/{user_id}`

### Clients
- `GET /api/v1/clients` — `?search=&entity_type=&page=&per_page=`
- `POST /api/v1/clients`
- `GET /api/v1/clients/{id}`
- `PUT /api/v1/clients/{id}`
- `DELETE /api/v1/clients/{id}` — Soft delete
- `GET /api/v1/clients/{id}/obligations`
- `POST /api/v1/clients/{id}/obligations`
- `DELETE /api/v1/clients/{id}/obligations/{obligation_id}`

### Documents
- `POST /api/v1/documents/upload` — Multipart, max 20MB
- `GET /api/v1/documents` — `?client_id=&doc_type=&status=&page=`
- `GET /api/v1/documents/{id}`
- `GET /api/v1/documents/{id}/download`
- `DELETE /api/v1/documents/{id}` — Soft delete
- `POST /api/v1/documents/{id}/reprocess` — Re-run OCR

### Reconciliation
- `POST /api/v1/reconciliations` — Trigger new run
- `GET /api/v1/reconciliations` — `?client_id=&period=&page=`
- `GET /api/v1/reconciliations/{id}`
- `GET /api/v1/reconciliations/{id}/items` — `?match_status=&page=`
- `PUT /api/v1/reconciliations/{id}/items/{item_id}` — CA override
- `GET /api/v1/reconciliations/{id}/export` — `?format=xlsx`

### NBR Notices
- `POST /api/v1/notices/upload` — Upload notice PDF
- `GET /api/v1/notices` — `?client_id=&status=&page=`
- `GET /api/v1/notices/{id}`
- `PUT /api/v1/notices/{id}` — Update status, save CA reply
- `POST /api/v1/notices/{id}/regenerate-draft`

### Compliance Calendar
- `GET /api/v1/calendar` — `?client_id=&from=&to=&status=`
- `GET /api/v1/calendar/upcoming` — Next 30 days
- `PUT /api/v1/calendar/{event_id}` — Update status
- `POST /api/v1/calendar/custom` — Add custom deadline

### Reports
- `POST /api/v1/reports/mis` — Generate MIS report
- `GET /api/v1/reports` — List generated reports
- `GET /api/v1/reports/{id}/download`

### System
- `GET /health` — Health check
- `GET /ready` — Readiness check
