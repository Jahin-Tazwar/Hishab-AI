# HishabAI — Product Specification

## 1. What Is HishabAI?

HishabAI (হিসাব AI) is a multi-tenant SaaS platform that automates the pre-advisory
workflow of Chartered Accountancy firms in Bangladesh. It sits as an intelligent middleware
layer between unstructured client data (invoices, bank statements, photos of receipts) and
the CA's existing tools (Tally, Excel, NBR portals).

## 2. The Core Loop

```
CLIENT submits chaotic documents → HISHABAI reads, classifies, extracts, reconciles, drafts → CA reviews, edits, approves → CA advises client, files returns, responds to notices
```

HishabAI owns the middle step entirely.

## 3. The One Metric That Matters

**Hours saved per CA per month.** Features saving 30+ min/month are MVP scope. Less than 5 min are Phase 2+.

## 4. Design Principles

1. **Bangladesh-first** — naming, error messages, dates, currency, regulatory logic
2. **CA is always in control** — Every AI output is a draft until CA approves
3. **Systems thinking** — Documents feed reconciliation, which feeds reports

## 5. Bangladesh Regulatory Context

See original PROJECT.md Parts 2.1–2.6 for full MushaK form system, BIN/TIN formats,
VAT rates, income tax framework, RJSC requirements, NBR notice types, and formatting rules.

Key facts: BIN = 9 digits, TIN = 12 digits, VAT = 15%, Fiscal year = July 1 – June 30,
Currency = BDT (৳), South Asian numbering (lakh/crore).

## 6. Scope Guard (Phase 2+)

Do NOT build in MVP: Direct NBR filing, e-signatures, payroll, mobile app, Tally integration,
custom AI training, WhatsApp, audit management, multi-currency, separate client portal app, SMS.
