"""Opt-in extended B agent; never run alongside the original polling agent."""
import os
from pathlib import Path
import agent
from solidworks_box import create_box

_original = agent.execute

def execute(operation, params):
    if operation == "create_box":
        return create_box(
            params["name"], params["length_mm"], params["width_mm"], params["height_mm"],
            Path(os.environ.get("REMOTE_B_OUTPUT_DIR", r"D:\codex\output")),
            Path(os.environ.get("REMOTE_B_PART_TEMPLATE",
                r"C:\ProgramData\SolidWorks\SOLIDWORKS 2023\templates\gb_part.prtdot"))
        )
    return _original(operation, params)

agent.execute = execute

if __name__ == "__main__":
    agent.main()
