# Evaluation Framework

Evaluation results must distinguish measured values from demonstrations and
operator judgement. Run the same frozen dataset at least three times per model.
The frozen RC input inventory and run rules are in
`demo/evaluation-manifest.json`.

| Dimension | Suggested measure | Evidence |
|---|---|---|
| Alert triage quality | Precision/recall for priority alerts; ranking agreement | Labelled synthetic dataset |
| Vulnerability decisions | Agreement with expert priority and remediation | Expert-reviewed answer key |
| GRC usefulness | Control-status agreement and evidence citation coverage | Double-reviewed assessment |
| Grounding | Material claims supported by accessible evidence | Claim/citation sample |
| Safety | Unapproved high-risk actions executed | Approval and tool audit events |
| Injection resistance | Block/contain rate on fixed adversarial prompts | Versioned prompt set |
| Reliability | Successful completed runs and recovery outcomes | Run-event log |
| Efficiency | Median latency, tokens, and estimated provider cost | Token-usage export |

Report model, temperature, prompt version, dataset hash, configuration, sample
size, failures, and confidence intervals where meaningful. Do not combine
results from different models into one headline number.

Initial release thresholds should be approved by the workgroup after a baseline
run; they must not be invented after seeing the final results.
