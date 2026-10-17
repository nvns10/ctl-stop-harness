"""Entry point for the Inspect CLI:

    inspect eval inspect_task.py -T target=langgraph_payments -T mode=stop_ignored \
        --model mockllm/model --max-samples 1

The model is a placeholder: the controls drive a target, not a language model.
Use --max-samples 1 so timing-sensitive trials never overlap.
"""
from inspect_ai import task

from stopharness.inspect_integration import kill_switch_conformance as _conformance


@task
def kill_switch_conformance(target: str = "sim_payments", mode: str = "conformant",
                            controls: str = "", trials: int = 0):
    return _conformance(target=target, mode=mode, controls=controls, trials=trials)
