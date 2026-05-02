-- 0003_indexes.sql — performance indexes for common access paths

CREATE INDEX idx_clients_tenant_active     ON clients(tenant_id, deleted_at);
CREATE INDEX idx_clients_tenant_name       ON clients(tenant_id, name);

CREATE INDEX idx_obligations_client        ON compliance_obligations(client_id, is_active);

CREATE INDEX idx_events_tenant_due         ON compliance_events(tenant_id, due_date, status);
CREATE INDEX idx_events_client_status      ON compliance_events(client_id, status);

CREATE INDEX idx_documents_tenant          ON documents(tenant_id, client_id, deleted_at);

CREATE INDEX idx_recons_client_period      ON vat_reconciliations(client_id, period_start DESC);

CREATE INDEX idx_recon_items_recon         ON recon_line_items(reconciliation_id, match_status);
CREATE INDEX idx_recon_items_supplier_bin  ON recon_line_items(pr_supplier_bin);
