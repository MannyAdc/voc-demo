-- B17: no complaint ID from splits/test.csv is in a model that holds narratives or Products,
-- unless the `final` variable is on. Any row returned fails the build.
{% if final_flag_on() %}
select complaint_id from {{ ref('stg_complaints') }} where false
{% else %}
select complaint_id from {{ ref('stg_complaints') }} where complaint_id in {{ test_set_ids() }}
union all
select complaint_id from {{ ref('curated_complaints') }} where complaint_id in {{ test_set_ids() }}
{% endif %}
