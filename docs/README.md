# Documentation index

| Page | Read it to |
|---|---|
| [hands-on-guide.md](hands-on-guide.md) | Run the harness end to end and read the results, step by step |
| [architecture.md](architecture.md) | Understand how a run flows from the command line to a signed bundle |
| [controls.md](controls.md) | See what each control measures, its decision rules and how to edit a control file |
| [adapters-and-targets.md](adapters-and-targets.md) | Connect a real deployment, or understand the two synthetic targets |
| [evidence-bundle.md](evidence-bundle.md) | Verify a bundle independently, and know what signing does not prove |
| [cli-reference.md](cli-reference.md) | Look up commands, flags, exit codes and the Inspect entry point |
| [../CHANGELOG.md](../CHANGELOG.md) | See what changed in each release |

Start with the hands-on guide if you are an auditor. Start with architecture if you are a developer.

## Scope in one paragraph

ctl-stop-harness tests whether a stop mechanism for an agentic AI system works, and records
evidence an independent reviewer can check. It implements three controls: cessation
(CTL-STOP-003), latency (CTL-STOP-004) and failure resilience (CTL-STOP-005). Both bundled targets
are synthetic. A PASS is evidence relevant to a control. It is not a finding of compliance with any
regulation or standard, and no result from this repository says anything about a real deployment.

## Conventions used in these pages

- **Verdict**: one of `PASS`, `FAIL`, `INCONCLUSIVE`. Insufficient evidence is never a `PASS`.
- **T_stop**: seconds from the accepted stop command to the last consequential action initiated.
- **Consequential action**: an action with real-world effect. In the bundled targets, releasing a payment.
- **Adapter**: the code that connects the harness to one deployment's stop mechanism and telemetry.
- **Target**: an adapter plus the system behind it.
