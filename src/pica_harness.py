"""Group PICA specs using the existing --provider contract."""
from check_plan import Check


LITELLM_SPECS = {"configuracion-modelo-esfuerzo.spec.ts", "litellm-model-selection.spec.ts"}


def grouped(specs, preparation=None):
    groups = {"claude": [], "litellm": []}
    for spec in specs:
        name = spec.rsplit("/", 1)[-1]
        groups["litellm" if name in LITELLM_SPECS else "claude"].append(name)
    return [Check("pica:" + provider, ["./run.sh", "--provider", provider, *files], cwd="e2e",
                  resources=["pica:harness"], preparation=preparation, reporter="playwright")
            for provider, files in groups.items() if files]
