# V8 Evaluation Log

> Reconstructed from existing artifacts; this is not the original runtime log.

- Model: AI Temporal V8
- Dataset: {"answer_snapshot": "2026-07-02", "prediction_snapshot": "2024-01-04", "source_database_sha256": "d9d66ba2384f2d9e0b8cb55be43432f8e02fdd8fcd70ecd2266d65e52af73a04"}
- Test records: 1000
- Accuracy: 0.895
- Balanced accuracy: 0.8712121212121212
- Leakage audit: pass
- Warnings: The July 2026 archive was previously accessed for V7. V8 is a publicly committed, membership-hidden retrospective test, not a never-opened future archive or clinical validation.; V8 is a membership-hidden retrospective temporal test, not a never-opened future archive or clinical validation.; V8 and the frozen V7 model were evaluated on the same 1,000 V8 records; the balanced-accuracy difference was 0.004524319040448144, with component-bootstrap 95% interval [-0.02450184283147039, 0.03312248143795588] crossing zero.; V8 fitting combined inverse-component sample weights with balanced class weights, so effective fitting weight was not strictly equal per component.; The V8 simplicity tie-break ranked model families but not regularization strength within logistic regression.
