-- T021: the two DuckDB-only parts of the models, each with its Databricks form.
-- The DuckDB form is unchanged. The test list has its own branch in macros/test_set.sql.

-- The staged rows: the table `voc load` writes on DuckDB, the synthetic seed on Databricks, or on
-- Databricks with `--month`, the real export read from the volume (models/landed_complaints.sql).
{% macro staged_source() -%}
{%- if target.type == 'databricks' and var('month', '') -%}
{{ ref('landed_complaints') }}
{%- elif target.type == 'databricks' -%}
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

-- The real export on Databricks: the CFPB text of a date or a Yes/No flag, typed as `voc load` types it
-- (src/voc/load.py). Anything else is NULL, and dbt/tests/landed_rows_are_valid.sql fails on it.
{% macro cfpb_date(column) -%}
case
  when {{ column }} rlike '^\\d{4}-\\d{2}-\\d{2}$' then cast(try_to_timestamp({{ column }}, 'yyyy-MM-dd') as date)
  when {{ column }} rlike '^\\d{1,2}/\\d{1,2}/\\d{4}$' then cast(try_to_timestamp({{ column }}, 'M/d/yyyy') as date)
  when {{ column }} rlike '^\\d{1,2}/\\d{1,2}/\\d{2}$' then cast(try_to_timestamp({{ column }}, 'M/d/yy') as date)
end
{%- endmacro %}

{% macro cfpb_flag(column) -%}
case {{ column }} when 'Yes' then true when 'No' then false end
{%- endmacro %}

-- True when the text is missing or holds only white space.
{% macro is_blank(column) -%}
({{ column }} is null or not {{ column }} rlike '\\S')
{%- endmacro %}

-- The month's export in the volume, every column as text, read by its header names.
-- FAILFAST stops on a malformed row instead of reading it as NULLs.
{% macro month_file_rows() -%}
read_files('{{ var("month_file") | replace("'", "''") }}', format => 'csv', header => true, multiLine => true,
           escape => '"', mode => 'FAILFAST', inferColumnTypes => false, schemaEvolutionMode => 'none')
{%- endmacro %}
