"""Bounded phase context reconstructed from durable facts, not entire history."""
import json


def render(state, phase, *, max_chars=16000):
    values = {"phase": phase, "task": state.get("item"), "requirements": state.get("item_detail", "")[:5000],
              "branch": state.get("branch"), "base_sha": state.get("base_sha"),
              "verification_scope": state.get("verification_guidance", "")[-5000:],
              "change": state.get("slug"), "implementation": state.get("implementation_summary", "")[:2000],
              "checks": [{"check": r.get("check"), "status": r.get("status"), "report": r.get("report"),
                           "gate": r.get("gate")} for r in state.get("final_check_report", {}).get("checks", [])],
              "next_action": phase, "checkpoint": state.get("execution_checkpoint_id"),
              "review": state.get("internal_review_report"), "repair_round": state.get("final_repair_round", 0),
              "integration_inventory": state.get('integration_inventory'),
              "validation_overrides": state.get('validation_overrides', [])}
    return "Durable task handoff (facts):\n" + json.dumps(values, ensure_ascii=False)[:max_chars]
