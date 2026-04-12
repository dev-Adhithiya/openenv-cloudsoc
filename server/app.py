from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, Optional
import json
import sys
import os

# Ensure cloud_soc_env can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cloud_soc_env import CloudSOCEnv, Observation, Action, Reward

app = FastAPI(title="OpenEnv CloudSOC Benchmark",
              description="OpenEnv spec compliant REST bindings for CloudSOC environment")

env = CloudSOCEnv(task="easy")

class StepResponse(BaseModel):
    observation: Observation
    reward: Reward
    done: bool
    info: Dict[str, Any]

class ResetResponse(BaseModel):
    observation: Observation
    info: Dict[str, Any]

@app.get("/")
def ping():
    """Automated ping to the Space URL — must return 200"""
    return {"status": "ok", "environment": "openenv-cloudsoc"}

@app.post("/reset", response_model=ResetResponse)
def reset():
    """Reset the environment to initial state"""
    obs_str, info = env.reset()
    try:
        obs_dict = json.loads(obs_str)
    except Exception:
        obs_dict = {}
        
    # Pack raw observation string and metadata into typed model
    observation = Observation(
        state_description=obs_str,
        metadata=obs_dict
    )
    return ResetResponse(observation=observation, info=info)

@app.post("/step", response_model=StepResponse)
def step(action: Action):
    """Step the environment forward by executing an action"""
    action_dict = {
        "thought": "Executed from API",
        "tool": action.tool,
        "args": action.args
    }
    action_str = json.dumps(action_dict)
    
    obs_str, reward_val, done, trunc, info = env.step(action_str)
    try:
        obs_dict = json.loads(obs_str)
    except Exception:
        obs_dict = {}
    
    observation = Observation(
        state_description=obs_str,
        metadata=obs_dict
    )
    
    # Scale total rewards to ensure final constraints
    reward = Reward(
        value=reward_val,
        reason=info.get("last_action_error") or "Progress"
    )
    
    return StepResponse(
        observation=observation,
        reward=reward,
        done=done,
        info=info
    )

@app.get("/state")
def state():
    """Returns current state of the environment"""
    return {"state": env.state.to_dict()}

def main():
    """Main entry point for running the server"""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)

if __name__ == "__main__":
    main()
