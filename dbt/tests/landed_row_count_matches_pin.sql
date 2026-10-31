-- B16 on Databricks: the rows read from the export match the count `voc profile` found locally, where a
-- count is pinned in config/data_files.toml. A different count means the file was read differently.
-- Changed in the review of #58: the landed model leaves out the test rows, so the file itself is counted.
-- depends_on: {{ ref('landed_complaints') }}
{{ config(enabled=(target.type == 'databricks' and var('month', '') != '' and var('month_rows', 0) > 0)) }}

select count(*) as rows_read
from {{ month_file_rows() }}
having count(*) != {{ var('month_rows') | int }}
