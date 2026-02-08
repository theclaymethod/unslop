# Fact Preservation Rules

Certain content must survive transformation unchanged. This reference defines what to protect.

---

## Absolute Preservation (Never Modify)

These elements must appear in the output exactly as they appear in the input.

### Numbers & Quantities
- Specific figures: `$47.3M`, `23%`, `1,500 users`
- Dates: `Q3 2024`, `March 15, 2024`, `2024-03-15`
- Times: `9:00 AM PST`, `14:30 UTC`
- Measurements: `5.2kg`, `100ms`, `2TB`
- Ranges: `$50-75K`, `3-5 years`, `10-15%`
- Counts: `3 engineers`, `5 steps`, `47 countries`

### Proper Nouns
- Company names: `Acme Corp`, `OpenAI`, `Google`
- Product names: `GPT-4`, `iPhone 15`, `TensorFlow`
- Person names: `John Smith`, `Dr. Chen`
- Place names: `San Francisco`, `Building 43`
- Brand terms: `React`, `Kubernetes`, `AWS Lambda`

### Technical Terms
- API endpoints: `/api/v2/users`
- Code references: `handleSubmit()`, `UserContext`
- Config values: `max_retries: 3`, `timeout: 30s`
- Version numbers: `v2.1.0`, `Node 20.x`
- File paths: `/src/components/Button.tsx`

### Quoted Material
- Direct quotes: `"We're just getting started" - CEO`
- Cited text: anything in quotation marks attributed to a source
- Code snippets: preserve exactly, including whitespace

### URLs & References
- Links: `https://example.com/page`
- DOIs: `10.1234/journal.2024.001`
- ISBNs: `978-0-123456-78-9`
- Citations: `[1]`, `(Smith et al., 2024)`

---

## Semantic Preservation (Keep Meaning)

These can be rephrased but meaning must stay identical.

### Causal Claims
- Original: "A caused B"
- OK: "B resulted from A"
- NOT OK: "A influenced B" (weaker claim)

### Comparisons
- Original: "X is 3x faster than Y"
- OK: "X outperforms Y by 3x"
- NOT OK: "X is faster than Y" (lost quantifier)

### Conditional Statements
- Original: "If A, then B"
- OK: "B happens when A"
- NOT OK: "A and B" (lost conditionality)

### Negations
- Original: "X does not support Y"
- OK: "X lacks Y support"
- NOT OK: "X partially supports Y" (opposite meaning)

### Scope Qualifiers
- Original: "Most users (73%) prefer X"
- OK: "73% of users prefer X"
- NOT OK: "Users prefer X" (lost scope)

---

## Constraint Extraction

Before transforming, extract these as must-preserve spans:

```python
CONSTRAINT_PATTERNS = {
    # Numbers with context
    "currency": r"\$[\d,]+\.?\d*[KMB]?",
    "percentage": r"\d+\.?\d*%",
    "date_iso": r"\d{4}-\d{2}-\d{2}",
    "date_natural": r"(Q[1-4]\s+\d{4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})",
    "time": r"\d{1,2}:\d{2}\s*(?:AM|PM|UTC|PST|EST)?",
    "measurement": r"\d+\.?\d*\s*(?:ms|s|min|hr|KB|MB|GB|TB|kg|lb|m|km|mi)",

    # Identifiers
    "url": r"https?://[^\s]+",
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "code_ref": r"`[^`]+`",
    "quote": r'"[^"]{10,}"',

    # Proper nouns (NER-detected)
    "org": "ORGANIZATION entities",
    "person": "PERSON entities",
    "product": "PRODUCT entities",
    "location": "GPE/LOC entities"
}
```

---

## Verification Process

After transformation:

1. **Extract all constraints from original**
2. **Check each constraint exists in output**
3. **Flag any missing or altered constraints**

### Pass Criteria
- All absolute preservation items present and unchanged
- All semantic preservation items equivalent in meaning
- No fact inversions or significant alterations

### Fail Examples
| Original | Output | Problem |
|----------|--------|---------|
| "$47.3M revenue" | "$47M revenue" | Precision lost |
| "23% increase" | "significant increase" | Number removed |
| "John Smith, CEO" | "the CEO" | Name removed |
| "https://example.com" | "[link]" | URL removed |
| "Q3 2024" | "recently" | Date removed |
| "does not support" | "partially supports" | Meaning inverted |

---

## Special Cases

### Approximations in Original
If original uses approximate language, preserve the approximation:
- "about 50%" → OK to keep as "about 50%" or "roughly 50%"
- NOT OK to change to "50%" (implies false precision)

### Ranges
Preserve both bounds:
- "$50-75K" must keep both $50K and $75K
- "3-5 years" must keep both bounds

### Lists of Items
All items must survive:
- "Teams in SF, NYC, and London" → all three cities required
- Can reorder, but can't drop any

### Attributed Quotes
Quote text and attribution both required:
- `"We're excited" - Jane Doe, CEO`
- Both the quote and "Jane Doe, CEO" must survive

---

## Quick Reference

| Type | Example | Modifiable? |
|------|---------|-------------|
| Currency | $47.3M | NO - exact |
| Percentage | 23% | NO - exact |
| Date | Q3 2024 | NO - exact |
| Person | John Smith | NO - exact |
| Company | Acme Corp | NO - exact |
| URL | https://... | NO - exact |
| Code | `function()` | NO - exact |
| Quote | "..." | NO - exact |
| Causal | A caused B | YES - preserve meaning |
| Comparison | 3x faster | YES - preserve numbers |
