-- The real monthly export on Databricks (owner decision, 31 October 2026), read from the volume with
-- every column as text and typed as `voc load` types it (src/voc/load.py), in the same column order.
-- Only `voc dbt build --target databricks --month <month>` turns it on. The data tests below it check
-- the file's SHA-256 against its pin, the row count, the typed values and the complaint IDs, and dbt
-- builds no staged model from it if one fails.
{{ config(materialized='table', enabled=(target.type == 'databricks' and var('month', '') != '')) }}

select
  {{ cfpb_date('`Date received`') }} as date_received,
  `Product` as product,
  `Sub-product` as sub_product,
  `Issue` as issue,
  `Sub-issue` as sub_issue,
  `Consumer complaint narrative` as narrative,
  `Company public response` as company_public_response,
  `Company` as company,
  `State` as state,
  `ZIP code` as zip_code,
  `Tags` as tags,
  `Submitted via` as submitted_via,
  {{ cfpb_date('`Date sent to company`') }} as date_sent_to_company,
  `Company response to consumer` as company_response,
  {{ cfpb_flag('`Timely response?`') }} as timely_response,
  `Complaint ID` as complaint_id,
  '{{ var('month') | replace("'", "''") }}' as source
from {{ month_file_rows() }}
-- B17, review of #58: the test rows are left out here too, as in every model (macros/test_set.sql).
where {{ leave_out_test_rows('`Complaint ID`') }}
