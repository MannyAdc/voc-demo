-- The complaints with a narrative: the pool that samples are drawn from (T012).
-- B17: the test rows are left out unless the `final` variable is on (macros/test_set.sql).
{{ config(materialized='view') }}

select complaint_id, source, date_received, product, sub_product, narrative
from {{ ref('stg_complaints') }}
where narrative is not null and regexp_matches(narrative, '\S')
  and {{ leave_out_test_rows('complaint_id') }}
