-- T021: the two DuckDB-only parts of the models, each with its Databricks form.
-- The DuckDB form is unchanged. The test list has its own branch in macros/test_set.sql.

-- The staged rows: the table `voc load` writes on DuckDB, the synthetic seed on Databricks.
{% macro staged_source() -%}
{%- if target.type == 'databricks' -%}
{{ ref('staged_complaints') }}
{%- else -%}
{{ source('voc', 'staged_complaints') }}
{%- endif -%}
{%- endmacro %}

-- True when the text holds a character that is not white space.
{% macro has_text(column) -%}
{%- if target.type == 'databricks' -%}
{{ column }} rlike '\\S'
{%- else -%}
regexp_matches({{ column }}, '\S')
{%- endif -%}
{%- endmacro %}
