# Wireframes

Approved by the owner on 30 October 2026, with [USER.md](USER.md). One wireframe per screen, before it is built. The tasks are numbered as in USER.md. The figures on screen 1 are the real test-set figures. Every ID, label and line of complaint text on screens 2 and 3 is made up (SYN- IDs). Changed the same day after review: screens 2 and 3 use the development set.

## Screen 1. Overview (task 1)

The verdict first (pull request #44), then a box for the review, with a link to each product's development complaints.

```
+------------------------------------------------------------------+
| Complaint labels: the AI against a word-based model              |
| July 2026. Every label quotes its evidence. A script checks it.  |
+------------------------------------------------------------------+
| WHAT IS BEING LABELLED                                           |
| The product each complaint is about: one of 11 (list shown).     |
| The AI's label: picked by an AI model, with a quoted sentence.   |
| The word-based model's suggestion: a simple model, the rival.    |
| The consumer's own choice: picked when filing, the answer key.   |
+------------------------------------------------------------------+
| VERDICT ON THE TEST SET, SCORED ONCE                             |
| The AI beats the word-based model: +2.4 points of re-weighted    |
| strict accuracy, 95% interval +0.5 to +4.1                       |
| [figures table]                 [interval chart]                 |
|                                                                  |
| PER PRODUCT     F1: how good the label is, 1.0 is perfect        |
| Product            Complaints   AI      Word-based               |
| Debt collection        452     0.833    0.863                    |
| Checking or savings    416     0.822    0.780                    |
| ...                                                              |
+------------------------------------------------------------------+
| REVIEW (development set, 370 complaints)                         |
| 9 complaints wait for a person. Reviewed 0 of 9. [review them >] |
| Browse by product: [Debt collection] [Credit card] [...]         |
+------------------------------------------------------------------+
| Development figures, used while building   Speed  Safety  Scale  |
+------------------------------------------------------------------+
```

## Screen 2. Complaints in one product (task 2)

Opened from a product link. The list holds IDs and labels only, so it loads fast. A quarantined complaint that has not been reviewed is held back, so where it is listed cannot give away the consumer's choice.

```
+------------------------------------------------------------------+
| < Overview    Debt collection: development complaints            |
| Show: (o) all  ( ) the AI was right  ( ) the AI was wrong        |
| 2 quarantined complaints are held back until they are reviewed.  |
+------------------------------------------------------------------+
| Complaint   The AI's label        Consumer's choice  Quote check |
| SYN-101     Debt collection       Debt collection    found       |
| SYN-102     Credit reporting      Debt collection    found       |
| SYN-103     (reviewed)            Debt collection    not found   |
| ...                                     [< prev]  1-25  [next >] |
+------------------------------------------------------------------+
```

## Screen 3. One complaint (tasks 2 and 3)

Opened from screen 2 or from the review list. The text is shown only when the owner starts the app with `--with-text` on their own machine.

```
+------------------------------------------------------------------+
| < Back     Complaint SYN-102                                     |
| The AI's label: Credit reporting    Quote check: found           |
| Word-based model's suggestion: Debt collection                   |
| Consumer's own choice: Debt collection                           |
|   On a quarantined complaint not yet reviewed, this line reads:  |
|   "The consumer's own choice is hidden while you decide, so the  |
|    decision is yours. It is used to score the decisions later."  |
+------------------------------------------------------------------+
| COMPLAINT TEXT                                                   |
| ... I disputed the account with the bureau and                   |
| [[the collector kept reporting a debt I do not owe]] even ...    |
|   ^ the quoted sentence, highlighted (made-up example text)      |
| (Without --with-text: "The text is shown only on the analyst's   |
|  own machine.")                                                  |
+------------------------------------------------------------------+
| YOUR DECISION (quarantined complaints only)                      |
| Product: [ Debt collection         v ]  one of 11, or none       |
| Reason: ( ) The AI's label is right (its quote failed the check) |
|         ( ) The word-based model's suggestion is right           |
|         ( ) Another product fits better                          |
|         ( ) It fits no product clearly (product left empty)      |
| [ Save decision ]     Saved decisions are shown on screen 1.     |
+------------------------------------------------------------------+
```

## States on every screen

- Loading: "Loading..." where the data will appear, never an empty table.
- Empty: "No complaints here" with what the filter was.
- Error: "The results could not be loaded" with what to try, never a raw error.

# Version 2: tabs for the analyst's tasks (approved by the owner on 30 October 2026)

After the first screens were built, the owner judged that they read like a results report, not a tool for the analyst. Version 2 keeps every screen above and its rules. It changes the layout. The figures below are the real test-set figures. Every complaint is made up (SYN- IDs).

## The top bar, on every screen

```
+--------------------------------------------------------------------------+
| Complaint labels: LLM against TF-IDF                                      |
| ... An LLM (?) labels each complaint ... scored against TF-IDF (?) ...    |
| [Overview] [Browse] [Review (9)] [How we measured]                        |
+--------------------------------------------------------------------------+
```

The title keeps the technical names (owner decision). Each (?) opens a short note in place.

## Tab 1, Overview (task 1)

```
| +-------------+ +-----------------+ +--------------+ +----------------+ |
| | 1,909       | | 80.3%           | | 9            | | $0.2373        | |
| | complaints  | | of all test     | | wait for a   | | LLM cost per   | |
| | in the test | | complaints right| | person       | | 1,000          | |
| +-------------+ +-----------------+ +--------------+ +----------------+ |
| VERDICT: The LLM beats TF-IDF: +2.4 points, 95% interval +0.5 to +4.1   |
| COMPLAINTS BY PRODUCT                          F1 (?): LLM / TF-IDF      |
| Debt collection      ##################  452   0.833 / 0.863 !          |
| Credit reporting     ###                  64   0.500 / 0.697 !          |
| Prepaid card         #                    28   too few to judge         |
| ! = TF-IDF does better here: check before you report                    |
| > All test figures, as a table                                          |
| > What is being labelled (the 11 products, the 3 answers, a glossary)   |
```

## Tabs 2 and 3, Browse and Review (tasks 2 and 3)

The list on the left, and the open complaint beside it, as screens 2 and 3 above.

```
| Product [Debt collection v]  Filter (o) all ( ) right ( ) wrong         |
| +----------------------------+  +-----------------------------------+  |
| | SYN-101  Debt collection   |  | Complaint SYN-102                 |  |
| | SYN-102  Credit reporting  |  | facts, the text with the quote,   |  |
| +----------------------------+  | and the decision form if waiting  |  |
|                                 +-----------------------------------+  |
```

## Tab 4, How we measured

The development figures (tuning figures), the interval chart, precision against coverage, who was right, Speed, Safety, Scale and the prompt versions. Everything technical for a reviewer, off the analyst's screens.

## Keyboard, contrast and width

- Every link, button, field, select and summary has a visible focus ring.
- Text contrast is at least 4.5 to 1 in both light and dark mode, measured on the page.
- Below 900 px wide, the tiles go two by two, each bar stacks under its name, and the complaint opens below its list.
