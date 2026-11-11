# Evaluation Results: data/sanity

| Clip | Backend | GT Notes | Est Notes | Onset-only (P/R/F1) | Onset+Offset (P/R/F1) | RT Factor | Peak RSS | Device | Version |
|------|---------|----------|-----------|---------------------|----------------------|-----------|----------|--------|---------|
| scarlatti_k525 | basic_pitch | 882 | FAILED | FAILED | FAILED | - | - | - | - |
| | | | | Error: Backend basic_pitch did not create output file tmp/basic_pitch_scarlatti_k525.json | | | | | |
| scarlatti_k525 | naive | 882 | 220 | 0.686/0.171/0.274 | 0.036/0.009/0.015 | 0.03x | 1900.0 MB |  |  |
| **mean** | naive | 882 | 220 | 0.686/0.171/0.274 | 0.036/0.009/0.015 | 0.03x | 1900.0 MB | | |