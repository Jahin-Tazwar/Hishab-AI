-- 0008_seed_obligations.sql — seed bd_obligation_definitions

INSERT INTO bd_obligation_definitions
  (obligation_type, display_name, applies_to, requires_vat_reg, cadence, due_rule, law_reference, penalty_note)
VALUES
  ('vat_return',
   'VAT Return (Mushak 9.1)',
   ARRAY['company','partnership'],
   true,
   'monthly',
   '15th of the month following the period',
   'VAT Act 2012, Section 64',
   'BDT 250 per day late'),

  ('tds_return',
   'TDS Return',
   ARRAY['company','partnership','individual'],
   false,
   'monthly',
   '20th of the month following the period',
   'ITO 1984, Section 75A',
   'BDT 5,000 per month default'),

  ('tds_deposit',
   'TDS Challan Deposit',
   ARRAY['company','partnership','individual'],
   false,
   'monthly',
   '7th of the month following the period',
   'ITO 1984, Section 58',
   '2% per month interest on delayed amount'),

  ('income_tax_company',
   'Company Income Tax Return',
   ARRAY['company'],
   false,
   'annual',
   '15th January following June 30 fiscal year end',
   'ITO 1984, Section 75',
   '1% per month of tax payable'),

  ('income_tax_individual',
   'Individual Income Tax Return',
   ARRAY['individual'],
   false,
   'annual',
   '30 November annually',
   'ITO 1984, Section 75',
   '1% per month of tax payable'),

  ('rjsc_annual',
   'RJSC Annual Return',
   ARRAY['company'],
   false,
   'annual',
   '21 days after AGM (proxy: 21 days after FY end)',
   'Companies Act 1994, Section 190',
   'BDT 500 per day default')
ON CONFLICT (obligation_type) DO NOTHING;
