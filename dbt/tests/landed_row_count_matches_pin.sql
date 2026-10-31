-- B16 on Databricks: the rows read from the export match the count `voc profile` found locally, where a
-- count is pinned in config/data_files.toml. A different count means the file was read differently.
{{ config(enabled=(target.type == 'databricks' and var('month', '') != '' and var('month_rows', 0) > 0)) }}

select count(*) as rows_read
from {{ ref('landed_complaints') }}
having count(*) != {{ var('month_rows') | int }}
