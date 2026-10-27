# voc-demo

Status: planning done, no code yet (28 October 2026).

A Voice of the Customer pipeline on the public US CFPB Consumer Complaint Database. An LLM labels each complaint by Product and quotes the sentence that supports the label. A script checks that the quote really appears in the text. A label that fails a check goes to quarantine with a reason. It is never dropped and never counted as correct.

## About the data

- Source: the CFPB Consumer Complaint Database. Raw data is not stored in this repo.
- The CFPB says: "This database is not a statistical sample of consumers' experiences in the marketplace". Results here describe this data only.
- The CFPB also says: "All complaint data we publish is freely available for anyone to use, analyze, and build on." Both quotes are from the [CFPB complaint database page](https://www.consumerfinance.gov/data-research/consumer-complaints/), read 28 October 2026.
- The Product and Issue fields are set by the consumer, not by the CFPB ("The type of product the consumer identified in the complaint", [CFPB field reference](https://cfpb.github.io/api/ccdb/fields.html)). So the recorded labels are noisy, and some measured "errors" will be label noise.

## Where to start

- What it must do: [specs/001-core-labelling-pipeline/spec.md](specs/001-core-labelling-pipeline/spec.md)
- How we work: [CLAUDE.md](CLAUDE.md)
- What happened and when: [BUILD_LOG.md](BUILD_LOG.md)
