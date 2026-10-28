-- The staged complaints, incremental and keyed on complaint ID (T011 add-on 1).
-- A run adds only complaint IDs it has not seen. A row already built is never changed,
-- so late or corrected records are not picked up (a known gap, see the README).
{{ config(materialized='incremental', unique_key='complaint_id', incremental_strategy='delete+insert') }}

select *
from {{ source('voc', 'staged_complaints') }} as s
{% if is_incremental() %}
where not exists (select 1 from {{ this }} as t where t.complaint_id = s.complaint_id)
{% endif %}
