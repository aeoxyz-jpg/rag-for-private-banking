# Routing accuracy — pillar F (router) validation

Classifier: `deepseek-v4-flash:cloud`. `router.classify()` over the hand-labeled routing gold (incl. Q4/Q7 and deliberate E↔B boundary cases). **Accuracy: 100%** (n=28).

## Confusion matrix (rows = expected, cols = predicted)

| expected \\ predicted | sql | metric | vector | kb | c360 | hybrid |
|---|---|---|---|---|---|---|
| sql | 10 | 0 | 0 | 0 | 0 | 0 |
| metric | 0 | 7 | 0 | 0 | 0 | 0 |
| vector | 0 | 0 | 3 | 0 | 0 | 0 |
| kb | 0 | 0 | 0 | 3 | 0 | 0 |
| c360 | 0 | 0 | 0 | 0 | 3 | 0 |
| hybrid | 0 | 0 | 0 | 0 | 0 | 2 |

## Per-route precision / recall

| route | support | precision | recall |
|---|--:|--:|--:|
| sql | 10 | 1.0 | 1.0 |
| metric | 7 | 1.0 | 1.0 |
| vector | 3 | 1.0 | 1.0 |
| kb | 3 | 1.0 | 1.0 |
| c360 | 3 | 1.0 | 1.0 |
| hybrid | 2 | 1.0 | 1.0 |