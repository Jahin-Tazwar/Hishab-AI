-- 0007_generate_compliance_events.sql
-- Generates compliance_events rows for a client based on their entity_type
-- and is_vat_registered status. Idempotent: skips (client, obligation, period_start)
-- combinations that already exist (uses ON CONFLICT DO NOTHING via the table's UNIQUE).

CREATE OR REPLACE FUNCTION generate_compliance_events(
  p_client_id uuid,
  p_from_date date,
  p_to_date   date
) RETURNS integer  -- count of events inserted
LANGUAGE plpgsql
SECURITY INVOKER  -- runs as the calling user; RLS still applies
AS $$
DECLARE
  v_client            clients%ROWTYPE;
  v_obligation        bd_obligation_definitions%ROWTYPE;
  v_period_start      date;
  v_period_end        date;
  v_due_date          date;
  v_inserted_count    integer := 0;
BEGIN
  -- Fetch the client row (RLS-filtered: caller must own this client)
  SELECT * INTO v_client FROM clients WHERE id = p_client_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Client % not found or not accessible', p_client_id;
  END IF;

  -- Loop over applicable obligations
  FOR v_obligation IN
    SELECT *
    FROM bd_obligation_definitions
    WHERE v_client.entity_type = ANY(applies_to)
      AND (NOT requires_vat_reg OR v_client.is_vat_registered)
  LOOP
    -- Generate periods + due dates based on cadence
    IF v_obligation.cadence = 'monthly' THEN
      v_period_start := date_trunc('month', p_from_date)::date;
      WHILE v_period_start <= p_to_date LOOP
        v_period_end := (v_period_start + interval '1 month - 1 day')::date;
        -- Due date depends on obligation_type
        v_due_date := CASE v_obligation.obligation_type
          WHEN 'vat_return'   THEN (v_period_end + interval '15 days')::date
          WHEN 'tds_return'   THEN (v_period_end + interval '20 days')::date
          WHEN 'tds_deposit'  THEN (v_period_end + interval '7 days')::date
          ELSE (v_period_end + interval '15 days')::date
        END;

        INSERT INTO compliance_events
          (tenant_id, client_id, obligation_type, period_start, period_end, due_date)
        VALUES
          (v_client.tenant_id, v_client.id, v_obligation.obligation_type,
           v_period_start, v_period_end, v_due_date)
        ON CONFLICT (client_id, obligation_type, period_start) DO NOTHING;

        IF FOUND THEN v_inserted_count := v_inserted_count + 1; END IF;

        v_period_start := (v_period_start + interval '1 month')::date;
      END LOOP;

    ELSIF v_obligation.cadence = 'annual' THEN
      -- BD fiscal year: July 1 — June 30
      -- Compute the FY start that falls within (or before) the range
      v_period_start := CASE
        WHEN extract(month FROM p_from_date) >= 7 THEN
          make_date(extract(year FROM p_from_date)::int, 7, 1)
        ELSE
          make_date(extract(year FROM p_from_date)::int - 1, 7, 1)
      END;

      WHILE v_period_start <= p_to_date LOOP
        v_period_end := (v_period_start + interval '1 year - 1 day')::date;

        v_due_date := CASE v_obligation.obligation_type
          -- Company IT return: 15 January after FY end (FY ends June 30)
          WHEN 'income_tax_company' THEN
            make_date(extract(year FROM v_period_end)::int + 1, 1, 15)
          -- Individual IT return: 30 November of FY end year
          WHEN 'income_tax_individual' THEN
            make_date(extract(year FROM v_period_end)::int, 11, 30)
          -- RJSC annual return: default 21 days after FY end (proxy for AGM)
          WHEN 'rjsc_annual' THEN
            (v_period_end + interval '21 days')::date
          ELSE
            (v_period_end + interval '60 days')::date
        END;

        INSERT INTO compliance_events
          (tenant_id, client_id, obligation_type, period_start, period_end, due_date)
        VALUES
          (v_client.tenant_id, v_client.id, v_obligation.obligation_type,
           v_period_start, v_period_end, v_due_date)
        ON CONFLICT (client_id, obligation_type, period_start) DO NOTHING;

        IF FOUND THEN v_inserted_count := v_inserted_count + 1; END IF;

        v_period_start := (v_period_start + interval '1 year')::date;
      END LOOP;
    END IF;
    -- 'quarterly' cadence not yet supported (no MVP obligations use it)
  END LOOP;

  RETURN v_inserted_count;
END;
$$;

GRANT EXECUTE ON FUNCTION generate_compliance_events(uuid, date, date) TO authenticated;
