# Agentic Context Evaluation

Deterministic runs: 1890 (errors: 0).

Each task is a real commit evaluated at its parent state. File hits is the
recall of the changed files among the packed files; region containment is
the fraction of changed line ranges the packed selection surfaces verbatim.
Means carry a seeded 95% bootstrap confidence interval.

## Overall

- File hits: 97.8% [97.3%, 98.3%]
- Region containment: 37.1% [35.5%, 38.8%]
- Input tokens: 18,189 [17,506, 18,831]

## Breakdowns

### By repository

| Group | File hits (95% CI) | Region containment (95% CI) | Input tokens (95% CI) | n |
|---|---|---|---|---|
| click | 99.5% [99.0%, 99.9%] | 32.2% [29.7%, 35.1%] | 13,463 [13,023, 13,906] | 630 |
| httpx | 100.0% [100.0%, 100.0%] | 43.0% [39.8%, 46.2%] | 10,012 [9,675, 10,357] | 630 |
| redcon | 93.9% [92.5%, 95.3%] | 36.1% [33.6%, 38.6%] | 31,092 [29,725, 32,453] | 630 |

### By budget

| Group | File hits (95% CI) | Region containment (95% CI) | Input tokens (95% CI) | n |
|---|---|---|---|---|
| 12000 | 95.4% [94.0%, 96.6%] | 35.8% [33.1%, 38.8%] | 10,219 [10,046, 10,395] | 630 |
| 30000 | 98.5% [97.8%, 99.1%] | 37.3% [34.6%, 40.3%] | 17,939 [17,267, 18,626] | 630 |
| 60000 | 99.6% [99.2%, 99.9%] | 38.2% [35.6%, 41.3%] | 26,410 [24,853, 27,990] | 630 |

### By phrasing

| Group | File hits (95% CI) | Region containment (95% CI) | Input tokens (95% CI) | n |
|---|---|---|---|---|
| medium | 97.7% [96.7%, 98.5%] | 36.3% [33.5%, 39.2%] | 18,373 [17,232, 19,583] | 630 |
| precise | 97.5% [96.5%, 98.4%] | 44.6% [41.8%, 47.6%] | 19,058 [17,913, 20,260] | 630 |
| vague | 98.3% [97.5%, 99.1%] | 30.5% [27.8%, 33.3%] | 17,136 [16,146, 18,203] | 630 |

### Phrasing distinguishability

The medium phrasing only differs from precise when the subject names a file or symbol to strip, so a precise-vs-medium gap can come only from the distinguishable subset below. Read the by-phrasing means with this in mind.

- Tasks where medium differs from precise: 66/210 (31.4%).
- Tasks where all three phrasings are distinct: 66/210.

| Repository | Medium differs from precise | Tasks |
|---|---|---|
| click | 34 | 70 |
| httpx | 25 | 70 |
| redcon | 7 | 70 |

### Caveats

- The vague phrasing is derived from the change itself: its template names
  the directory the commit touched. Its file-hits figure is therefore an
  upper bound. A genuinely vague request that names no area would be harder,
  so the vague rows measure area-informed prompts, not robustness to vague
  wording as such.
- The medium phrasing is identical to precise for 144/210 tasks
  (it only differs when the subject names a file or symbol to strip), so the
  precise-vs-medium comparison rests on the distinguishable subset counted
  above, not on the full corpus.

## Risk calibration

A calibrated risk should show lower coverage at higher risk.

| Risk | File hits | Region containment | n |
|---|---|---|---|
| high | 93.5% | 38.7% | 636 |
| medium | 100.0% | 36.3% | 1254 |

## Budget curve

| Budget | File hits (95% CI) | Region containment (95% CI) |
|---|---|---|
| 12,000 | 95.4% [94.0%, 96.6%] | 35.8% [33.1%, 38.8%] |
| 30,000 | 98.5% [97.8%, 99.1%] | 37.3% [34.6%, 40.3%] |
| 60,000 | 99.6% [99.2%, 99.9%] | 38.2% [35.6%, 41.3%] |
