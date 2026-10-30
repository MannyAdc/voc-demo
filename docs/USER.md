# Who the dashboard is for

Approved by the owner on 30 October 2026, with the wireframes in [WIREFRAMES.md](WIREFRAMES.md), before any of these screens was built.

## What is being labelled

Each complaint is a consumer's own description of a problem with a financial product. The label is **the product the complaint is about**: one of 11 categories, the CFPB's own list (`config/labels.toml`):

- Checking or savings account
- Credit card
- Credit reporting or other personal consumer reports
- Debt collection
- Debt or credit management
- Money transfer, virtual currency, or money service
- Mortgage
- Payday loan, title loan, personal loan, or advance loan
- Prepaid card
- Student loan
- Vehicle loan or lease

Three products appear on the screens. Each one is named the same way everywhere:

- **The AI's label.** An LLM reads the complaint, picks one of the 11 products and copies the sentence that shows why. A script checks that the sentence is really in the complaint. If the check passes, the label is accepted. If it fails, the complaint goes to quarantine with the reason, and it has no label until a person decides.
- **The word-based model's suggestion.** A simple model (TF-IDF) that learned which words go with each product from 7,024 other complaints. It suggests a product for every complaint. It is the comparison the AI must beat.
- **The consumer's own choice.** When consumers file a complaint, they pick the product themselves. The CFPB records it. Here it is the answer key: it scores the AI, the word-based model and the analyst's decisions. It is never shown to the AI.

Counting complaints by product is the first step of Voice of the Customer: it shows where customers are unhappy. The same pattern would work for sales calls: label each call by issue, quote the evidence, and send failures to a person.

## The user

A Voice of the Customer analyst at a financial-services company.

- They read customer complaints every day and report what customers complain about.
- They are not technical. They do not read code, run commands or know what TF-IDF is.
- They need to trust a label before they report it. A wrong label in a report is worse than a missing one.
- They work on their own laptop, inside the company network.

## Their three tasks

1. **See where complaints are, and how far the labels can be trusted.**
   Which products get the most complaints, and how often the AI's label is right for each product. Where it is weak, they see it before they report it. Today this is the verdict card and the per-product table.

2. **Read the evidence behind a label.**
   Pick a product, see its complaints, open one, and read the sentence the AI quoted, highlighted in the complaint's own text. So they can check the label in a few seconds, without searching the text.

3. **Review the quarantined complaints.**
   For each complaint the quote check did not accept, see why, the AI's proposed label (if it gave one) and the word-based model's suggestion, and read the complaint. Then choose one of the 11 products, with one of these reasons:
   - The AI's label is right (its quote just failed the check).
   - The word-based model's suggestion is right.
   - Another product fits better.
   - It fits no product clearly.

   The decision is stored and shown in the dashboard. This is the human-in-the-loop step: no quarantined label is used until a person decides.

   **The consumer's own choice is hidden on this screen, on purpose.** Consumers do pick the product themselves, and the CFPB records it. But a person who sees it tends to copy it. Hiding it keeps the analyst's decision their own. It also lets us score the analyst's decisions against the consumer's choice, the same way the AI is scored. The screen says this in one line, so no one wonders where it went. The consumer's choice is shown on the complaint list (task 2), where it is needed to see where the AI was right or wrong.

## What they need from every screen

- Plain words. "The AI's label", "the word-based model's suggestion" and "the consumer's own choice", with the technical name (LLM, TF-IDF, recorded product) in small print.
- A short "What is being labelled" box on the first screen, with the 11 products and the three names above.
- Clear empty, loading and error states. "No complaints in this product" is not the same as "the data did not load".
- Keyboard use for every action, readable contrast, and a label on every control.
- No number without saying what it counts.

## Limits, stated on screen

- One month of data (July 2026), so there is no trend over time. August has a narrative in only 1 complaint.
- The recorded product was chosen by the consumer, so some "wrong" labels are the consumer's choice.
- Complaint text is shown only when the app runs on the analyst's own machine, with the local data. A public copy of the app shows IDs, labels and reasons only.
