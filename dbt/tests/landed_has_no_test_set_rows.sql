-- B17 on Databricks: no complaint ID from splits/test.csv is in the landed model, which holds narratives and
-- Products, unless the `final` variable is on. Any row returned fails the build. Added in the review of #58.
{{ config(enabled=(target.type == 'databricks' and var('month', '') != '')) }}
{% if final_flag_on() %}
select complaint_id from {{ ref('landed_complaints') }} where false
{% else %}
select complaint_id from {{ ref('landed_complaints') }} where complaint_id in {{ test_set_ids() }}
{% endif %}
