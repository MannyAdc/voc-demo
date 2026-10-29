-- B17: the dbt models leave out the test rows unless the `final` variable is a real true.
-- The variable is false in dbt_project.yml, and `voc dbt` always passes it as false.
-- The test IDs come from the committed list, splits/test.csv, next to the dbt project folder.
-- The path is built from the project folder dbt was given, so it does not depend on the folder
-- a reader of the view runs in. A missing list fails the build, because DuckDB cannot open the file.

{% macro final_flag_on() %}
  {{ return(var('final', false) is sameas true) }}
{% endmacro %}

{% macro test_list_path() -%}
{%- set project = invocation_args_dict.get('project_dir') or '.' -%}
{{ (project | replace('\\', '/')) ~ '/../splits/test.csv' }}
{%- endmacro %}

{% macro test_set_ids() -%}
(select complaint_id from read_csv('{{ test_list_path() | replace("'", "''") }}', header = true,
    columns = {'complaint_id': 'VARCHAR', 'content_hash': 'VARCHAR'}))
{%- endmacro %}

{% macro leave_out_test_rows(column) -%}
{%- if final_flag_on() -%} true {%- else -%} {{ column }} not in {{ test_set_ids() }} {%- endif -%}
{%- endmacro %}

-- A post-hook on the incremental model: test rows built by an earlier run with the flag on are deleted.
{% macro remove_test_rows() -%}
{%- if final_flag_on() -%}
delete from {{ this }} where false
{%- else -%}
delete from {{ this }} where complaint_id in {{ test_set_ids() }}
{%- endif -%}
{%- endmacro %}
