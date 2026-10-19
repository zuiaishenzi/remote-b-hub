"""Extended SolidWorks recipe agent. Run INSTEAD OF box_agent.py, not alongside."""
import agent
from box_agent import execute as previous_execute
from sw_recipe import execute_recipe

def execute(operation, params):
    if operation == "sw_recipe":
        return execute_recipe(params["recipe"])
    return previous_execute(operation, params)

agent.execute = execute
if __name__ == "__main__":
    agent.main()
