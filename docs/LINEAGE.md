# dbt lineage

Written by `voc dbt lineage` from dbt's `manifest.json` (`dbt parse`). Do not edit it by hand.
It holds node names and edges only: no paths, no SQL and no descriptions.
It shows the local DuckDB target. The two seeds of the Databricks target (T021) are off there,
so they are not drawn.

1 sources, 0 seeds, 2 models, 6 data tests, 9 edges.

```mermaid
graph LR
  n1[("source: voc.staged_complaints")]
  n2["model: curated_complaints"]
  n3["model: stg_complaints"]
  n4{{"test: no_test_set_rows"}}
  n5{{"test: not_null_stg_complaints_complaint_id"}}
  n6{{"test: product_in_label_list"}}
  n7{{"test: source_not_null_voc_staged_complaints_complaint_id"}}
  n8{{"test: source_unique_voc_staged_complaints_complaint_id"}}
  n9{{"test: unique_stg_complaints_complaint_id"}}
  n2 --> n4
  n3 --> n2
  n3 --> n4
  n3 --> n5
  n3 --> n6
  n3 --> n9
  n1 --> n3
  n1 --> n7
  n1 --> n8
```
