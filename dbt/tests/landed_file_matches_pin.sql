-- B16 on Databricks: the uploaded export must be the pinned file, byte for byte. Its SHA-256 is worked out
-- in the warehouse and compared with config/data_files.toml, so the rows are the same bytes `voc load`
-- checked on the owner's machine. A missing file is an error, a different file returns a row.
-- dbt build skips every model below a failing test of its parent:
-- depends_on: {{ ref('landed_complaints') }}
{{ config(enabled=(target.type == 'databricks' and var('month', '') != '')) }}

select length as file_bytes
from read_files('{{ var("month_file") | replace("'", "''") }}', format => 'binaryFile')
where sha2(content, 256) != '{{ var("month_sha256") | replace("'", "''") }}'
