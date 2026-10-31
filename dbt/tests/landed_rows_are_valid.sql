-- B14 on Databricks: the checks `voc load` makes before it writes (src/voc/load.py), on the export as read.
-- A date received is required. A date or Yes/No value that is there must parse. A complaint ID must have
-- no spaces at either end. Missing or repeated IDs are checked in models/schema.yml. Only counts are kept.
-- depends_on: {{ ref('landed_complaints') }}
{{ config(enabled=(target.type == 'databricks' and var('month', '') != '')) }}

select count(*) as bad_rows
from {{ month_file_rows() }}
where {{ is_blank('`Date received`') }}
   or {{ cfpb_date('`Date received`') }} is null
   or (not {{ is_blank('`Date sent to company`') }} and {{ cfpb_date('`Date sent to company`') }} is null)
   or (not {{ is_blank('`Timely response?`') }} and {{ cfpb_flag('`Timely response?`') }} is null)
   or `Complaint ID` rlike '^\s|\s$'
having count(*) > 0
