# Wireframes

Approved by the owner on 30 October 2026, with [USER.md](USER.md). One wireframe per screen, before it is built. The tasks are numbered as in USER.md. Every ID, label and line of complaint text in the wireframes is made up (SYN- IDs).

## Screen 1. Overview (task 1)

The page that exists today, with the verdict first. Each product row opens screen 2.

```
+------------------------------------------------------------------+
| Complaint labels: the AI against a word-based model              |
| July 2026. Every label quotes its evidence. A script checks it.  |
+------------------------------------------------------------------+
| WHAT IS BEING LABELLED                                           |
| The product each complaint is about: one of 11 (list shown).     |
| The AI's label: picked by an LLM, with a quoted sentence.        |
| The word-based model's suggestion: TF-IDF, the comparison.       |
| The consumer's own choice: picked when filing, the answer key.   |
+------------------------------------------------------------------+
| VERDICT ON THE FROZEN TEST SET                                   |
| The AI beats the word-based model: +2.4 points (+0.5 to +4.1)    |
| [figures table]                 [interval chart]                 |
|                                                                  |
| PER PRODUCT                     how often the label is right     |
| Product            Complaints   AI      Word-based               |
| Debt collection        452     0.833    0.863     [open >]       |
| Checking or savings    416     0.822    0.780     [open >]       |
| ...                                                              |
+------------------------------------------------------------------+
| QUARANTINE: 45 complaints wait for a person   [review them >]    |
|   reviewed 0 of 45                                               |
+------------------------------------------------------------------+
| Development figures (tuning only)   Speed   Safety   Scale       |
+------------------------------------------------------------------+
```

## Screen 2. Complaints in one product (task 2)

Opened from a product row. The list holds IDs and labels only, so it loads fast.

```
+------------------------------------------------------------------+
| < Overview     Debt collection: 452 test complaints              |
| Show: (o) all  ( ) the AI was right  ( ) the AI was wrong        |
+------------------------------------------------------------------+
| Complaint   The AI's label        Consumer's choice  Quote check |
| SYN-101     Debt collection       Debt collection    found       |
| SYN-102     Credit reporting      Debt collection    found       |
| SYN-103     (quarantined)         Debt collection    not found   |
| ...                                        [< prev]  1-25  [next >]|
+------------------------------------------------------------------+
```

## Screen 3. One complaint (tasks 2 and 3)

Opened from screen 2 or from the quarantine list. The text is shown only on the analyst's machine.

```
+------------------------------------------------------------------+
| < Back     Complaint SYN-102                                     |
| The AI's label: Credit reporting    Quote check: found           |
| Word-based model's suggestion: Debt collection                   |
| Consumer's own choice: Debt collection  (from the list, task 2)  |
|   On a quarantined complaint this line reads:                    |
|   "The consumer's own choice is hidden while you decide, so the  |
|    decision is yours. It is used to score the decisions later."  |
+------------------------------------------------------------------+
| COMPLAINT TEXT                                                   |
| ... I disputed the account with the bureau and                   |
| [[the collector kept reporting a debt I do not owe]] even ...    |
|   ^ the quoted sentence, highlighted                             |
| (On a public copy of the app: "The text is shown only on the     |
|  analyst's own machine.")                                        |
+------------------------------------------------------------------+
| YOUR DECISION (quarantined complaints only)                      |
| Label:  [ Debt collection          v ]  one of the 11 products   |
| Reason: ( ) The AI's label is right (its quote failed the check) |
|         ( ) The word-based model's suggestion is right           |
|         ( ) Another product fits better                          |
|         ( ) It fits no product clearly (the label is left empty) |
| [ Save decision ]     Saved decisions are shown on screen 1.     |
+------------------------------------------------------------------+
```

## States on every screen

- Loading: "Loading..." where the data will appear, never an empty table.
- Empty: "No complaints here" with what the filter was.
- Error: "The results could not be loaded" with what to try, never a raw error.
