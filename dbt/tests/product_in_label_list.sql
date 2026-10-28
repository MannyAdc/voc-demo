-- B14: the build fails on a Product outside the label set in config/labels.toml (B24).
-- The wrapper passes the label names as the `labels` variable.
{% set labels = var('labels') %}

select complaint_id
from {{ ref('stg_complaints') }}
where product is null
{% if labels | length > 0 %}
   or product not in ({% for label in labels %}'{{ label | replace("'", "''") }}'{% if not loop.last %}, {% endif %}{% endfor %})
{% else %}
   or true
{% endif %}
