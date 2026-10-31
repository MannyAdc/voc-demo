-- B14 on Databricks: a Product outside the label set in config/labels.toml (B24) fails the build on the landed
-- rows, so nothing is merged into the staged model, as `voc load` refuses the file before it writes.
-- The wrapper passes the label names as the `labels` variable. Added in the review of #58.
{{ config(enabled=(target.type == 'databricks' and var('month', '') != '')) }}
{% set labels = var('labels') %}

select complaint_id
from {{ ref('landed_complaints') }}
where product is null
{% if labels | length > 0 %}
   or product not in ({% for label in labels %}'{{ label | replace("'", "''") }}'{% if not loop.last %}, {% endif %}{% endfor %})
{% else %}
   or true
{% endif %}
