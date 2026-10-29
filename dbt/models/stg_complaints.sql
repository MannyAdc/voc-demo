-- The staged complaints, incremental and keyed on complaint ID (T011 add-on 1).
-- A run adds only complaint IDs it has not seen. A row already built is never changed,
-- so late or corrected records are not picked up. A new or removed column in the staged
-- table fails the build (`on_schema_change='fail'`). Both gaps are in the README.
-- B17: the test rows are left out unless the `final` variable is on (macros/test_set.sql).
-- The post-hook deletes test rows that an earlier run with the flag on left in the table.
{{ config(materialized='incremental', unique_key='complaint_id', incremental_strategy='delete+insert',
          on_schema_change='fail', post_hook="{{ remove_test_rows() }}") }}

select *
from {{ source('voc', 'staged_complaints') }} as s
where {{ leave_out_test_rows('s.complaint_id') }}
{% if is_incremental() %}
  and not exists (select 1 from {{ this }} as t where t.complaint_id = s.complaint_id)
{% endif %}
