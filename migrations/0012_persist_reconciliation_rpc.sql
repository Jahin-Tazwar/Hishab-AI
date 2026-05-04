-- 0012_persist_reconciliation_rpc.sql
-- Atomic write of one vat_reconciliations row + N recon_line_items rows.
-- SECURITY DEFINER so the backend (service-role) can call it without bypassing the audit
-- trigger semantics — actor user_id flows through `run_by` per migration 0010.

CREATE OR REPLACE FUNCTION public.persist_reconciliation(
  p_tenant_id              uuid,
  p_client_id              uuid,
  p_period_start           date,
  p_period_end             date,
  p_run_by                 uuid,
  p_pr_doc_id              uuid,
  p_sf_doc_id              uuid,
  p_total_invoices         integer,
  p_matched_exact          integer,
  p_matched_fuzzy          integer,
  p_partial_match          integer,
  p_no_match               integer,
  p_total_vat_claimed_bdt  numeric,
  p_safe_itc_bdt           numeric,
  p_at_risk_itc_bdt        numeric,
  p_line_items             jsonb           -- array of objects matching recon_line_items columns
)
RETURNS uuid                                -- the new reconciliation id
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_recon_id uuid;
BEGIN
  IF p_tenant_id IS NULL OR p_client_id IS NULL OR p_run_by IS NULL THEN
    RAISE EXCEPTION 'tenant_id, client_id, run_by are required' USING ERRCODE = '22023';
  END IF;

  INSERT INTO public.vat_reconciliations (
    tenant_id, client_id, period_start, period_end,
    status, total_invoices,
    matched_exact, matched_fuzzy, partial_match, no_match,
    total_vat_claimed_bdt, safe_itc_bdt, at_risk_itc_bdt,
    purchase_register_doc_id, supplier_data_doc_id,
    run_by, started_at, completed_at
  )
  VALUES (
    p_tenant_id, p_client_id, p_period_start, p_period_end,
    'completed', p_total_invoices,
    p_matched_exact, p_matched_fuzzy, p_partial_match, p_no_match,
    p_total_vat_claimed_bdt, p_safe_itc_bdt, p_at_risk_itc_bdt,
    p_pr_doc_id, p_sf_doc_id,
    p_run_by, now(), now()
  )
  RETURNING id INTO v_recon_id;

  -- Bulk insert line items from JSONB
  INSERT INTO public.recon_line_items (
    tenant_id, reconciliation_id,
    pr_invoice_no, pr_supplier_bin, pr_supplier_name, pr_invoice_date,
    pr_taxable_amount_bdt, pr_vat_amount_bdt,
    sf_invoice_no, sf_invoice_date, sf_taxable_amount_bdt, sf_vat_amount_bdt,
    match_status, match_score, discrepancy_flags
  )
  SELECT
    p_tenant_id, v_recon_id,
    item->>'pr_invoice_no',
    item->>'pr_supplier_bin',
    item->>'pr_supplier_name',
    (item->>'pr_invoice_date')::date,
    (item->>'pr_taxable_amount_bdt')::numeric,
    (item->>'pr_vat_amount_bdt')::numeric,
    item->>'sf_invoice_no',
    NULLIF(item->>'sf_invoice_date','')::date,
    NULLIF(item->>'sf_taxable_amount_bdt','')::numeric,
    NULLIF(item->>'sf_vat_amount_bdt','')::numeric,
    item->>'match_status',
    (item->>'match_score')::numeric,
    item->'discrepancy_flags'
  FROM jsonb_array_elements(p_line_items) AS item;

  RETURN v_recon_id;
END;
$$;

REVOKE ALL ON FUNCTION public.persist_reconciliation(
  uuid,uuid,date,date,uuid,uuid,uuid,integer,integer,integer,integer,integer,
  numeric,numeric,numeric,jsonb
) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.persist_reconciliation(
  uuid,uuid,date,date,uuid,uuid,uuid,integer,integer,integer,integer,integer,
  numeric,numeric,numeric,jsonb
) TO service_role;
