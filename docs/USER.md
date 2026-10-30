# Who the dashboard is for

Approved by the owner on 30 October 2026, with the wireframes in [WIREFRAMES.md](WIREFRAMES.md), before any of these screens was built. Changed the same day after review: the browsing and review screens use the development set, not the test set (owner decision, see "Which complaints the screens use").

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

The screens give three answers for the same complaint. Each one is named the same way everywhere:

- **The AI's label.** An AI model reads the complaint, picks one of the 11 products and copies the sentence that shows why. A script checks that the sentence is really in the complaint. If the check passes, the label is accepted. If it fails, the complaint goes to quarantine with the reason, and it has no label until a person decides. (Technical name: an LLM.)
- **The word-based model's suggestion.** A simple model that learned which words go with each product from 7,024 other complaints. It suggests a product for every complaint. It is the comparison the AI must beat. (Technical name: TF-IDF.)
- **The consumer's own choice.** When consumers file a complaint, they pick the product themselves. The CFPB records it. Here it is the answer key: it scores the AI, the word-based model and the analyst's decisions. It is never shown to the AI. (Technical name: the recorded product.)

Counting complaints by product is the first step of Voice of the Customer: it shows where customers are unhappy. The same pattern would work for sales calls: label each call by issue, quote the evidence, and send failures to a person.

## The user

A Voice of the Customer analyst at a financial-services company.

- They read customer complaints every day and report what customers complain about.
- They are not technical. They do not read code, run commands or know what TF-IDF is.
- They need to trust a label before they report it. A wrong label in a report is worse than a missing one.
- They work on their own laptop, inside the company network.

## Their three tasks

1. **See where complaints are, and how far the labels can be trusted.**
   How many complaints each product has, and how good the AI's label is for each product. Where it is weak, they see it before they report it. The measure per product is the F1 score: a balance of how often the AI's label is right when it names that product, and how many of that product's complaints it finds. 1.0 is perfect. This is the verdict card and the per-product table, from the single scored test run (pull request #44).

2. **Read the evidence behind a label.**
   Pick a product, see its complaints, open one, and read the sentence the AI quoted, highlighted in the complaint's own text. So they can check the label in a few seconds, without searching the text.

3. **Review the quarantined complaints.**
   For each complaint the quote check did not accept, see why, the AI's proposed label (if it gave one) and the word-based model's suggestion, and read the complaint. Then choose one of the 11 products, or none, with one of these reasons:
   - The AI's label is right (its quote just failed the check).
   - The word-based model's suggestion is right.
   - Another product fits better.
   - It fits no product clearly (then the product is left empty).

   The decision is stored and shown in the dashboard. This is the human-in-the-loop step: no quarantined label is used until a person decides.

   **The consumer's own choice is hidden while a person decides, on purpose.** Consumers do pick the product themselves, and the CFPB records it. But a person who sees it tends to copy it. Hiding it keeps the analyst's decision their own. It also lets us score the analyst's decisions against the consumer's choice, the same way the AI is scored. The screen says this in one line, so no one wonders where it went.

   So that the hiding works, a quarantined complaint that has not been reviewed is not listed under any product in task 2, because the product it is listed under would give the consumer's choice away. The list says how many are held back for review. Once a person has decided, the complaint and its consumer's choice appear in the list.

## Which complaints the screens use

- **The verdict and the per-product figures (task 1)** come from the single scored run of the frozen test set: 1,909 complaints.
- **Browsing and review (tasks 2 and 3)** use the development set: 370 complaints, 9 of them quarantined. The test set stays sealed. Its complaint text and its consumer's choices are read only by the one scored run (rule B17), and human review never touches the test set results (rule B20). Owner decision, 30 October 2026.
- The analyst's decisions are stored apart, in `results/reviews/`, and never change any scored result (B20).

## What they need from every screen

- Plain words. "The AI's label", "the word-based model's suggestion" and "the consumer's own choice", with the technical name (LLM, TF-IDF, recorded product) in small print.
- A short "What is being labelled" box on the first screen, with the 11 products and the three names above.
- Clear empty, loading and error states. "No complaints in this product" is not the same as "the data did not load".
- Keyboard use for every action, readable contrast, and a label on every control.
- No number without saying what it counts.

## Limits, stated on screen

- One month of data (July 2026), so there is no trend over time.
- The recorded product was chosen by the consumer, and the consumer may have picked the wrong product. So the AI can be right and still be scored wrong.
- Complaint text is shown only when the owner starts the app on their own machine with the flag `--with-text`, with the local data. Without it, and on any public copy, the screens show IDs, labels and reasons only. The coding agent never passes that flag and never opens a page served with it.
- These screens need the specs to change: spec 002 today says the app writes nothing and shows no complaint text. The screens' pull request changes it, with the owner's decision.
