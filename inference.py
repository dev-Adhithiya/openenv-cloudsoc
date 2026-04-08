"""
OpenEnv-CloudSOC: LLM Evaluation Loop (inference.py)
=====================================================
Hackathon-compliant inference script for evaluating LLM agents on the
CloudSOC benchmark environment.

Implements:
- Memory Pressure Simulation (Mechanic #6): Sliding context window
- Chain-of-Thought Prompting (Mechanic #10): Structured JSON responses
- Multi-Task Shared State (Mechanic #11): Campaign continuity
- Hackathon stdout format: [START], [STEP], [END]
- Robust error handling and retry logic
- Adaptive temperature based on failures

Environment Variables:
- API_BASE_URL: LLM API endpoint (default: Hugging Face Inference API)
- MODEL_NAME: Model identifier (default: Qwen/Qwen2.5-3B-Instruct)
- HF_TOKEN: Hugging Face API token (optional, used for rate limit increase)
"""

import os
import sys
import json
import re
import time
import traceback
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from openai import OpenAI

# Import our environment
from cloud_soc_env import CloudSOCEnv, CloudState, SCENARIOS


# =============================================================================
# CONFIGURATION
# =============================================================================

# Environment variables with defaults
# Using Hugging Face Inference API for Qwen2.5-3B-Instruct
API_BASE_URL = os.getenv("API_BASE_URL", "https://api-inference.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-3B-Instruct")
HF_TOKEN = os.getenv("HF_TOKEN", "")

# Initialize OpenAI client (HF_TOKEN will be validated at runtime for actual API calls)
client = OpenAI(
    base_url=API_BASE_URL,
    api_key=HF_TOKEN or "placeholder"  # Allow Space to start, validate at runtime
)

# Memory pressure settings (Mechanic #6)
# Optimized for 2vCPU/8GB RAM - reduce context window
MAX_CONTEXT_TURNS = 4  # Keep only last N [Observation, Action] pairs (reduced for 8GB RAM)
MAX_RETRIES = 2  # Max retries for malformed LLM responses
RETRY_DELAY = 0.5  # Seconds between retries
MAX_TOKENS = 512  # Reduced from 1024 for 3B model on 8GB RAM


class AgentState(Enum):
    """Track agent's cognitive state for adaptive prompting"""
    EXPLORING = "exploring"
    INVESTIGATING = "investigating"
    CONTAINING = "containing"
    RECOVERING = "recovering"
    CLOSING = "closing"


# =============================================================================
# CONTEXT WINDOW MANAGER (Mechanic #6)
# =============================================================================

@dataclass
class ContextWindow:
    """
    Manages sliding context window for memory pressure simulation.
    
    Keeps system prompt + last N turns to force agent to rely on
    internal reasoning rather than brute-forcing through context.
    """
    
    system_prompt: str = ""
    turns: List[Dict[str, str]] = field(default_factory=list)
    max_turns: int = MAX_CONTEXT_TURNS
    
    def add_turn(self, observation: str, action: str, result: str):
        """Add a new turn to the context"""
        self.turns.append({
            "observation": observation,
            "action": action,
            "result": result
        })
        
        # Sliding window - remove oldest turns if over limit
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]
    
    def get_messages(self) -> List[Dict[str, str]]:
        """Convert context to OpenAI message format"""
        messages = [{"role": "system", "content": self.system_prompt}]
        
        for turn in self.turns:
            # User message: observation
            messages.append({
                "role": "user",
                "content": f"Observation:\n{turn['observation']}\n\nResult of last action:\n{turn['result']}"
            })
            
            # Assistant message: action taken
            messages.append({
                "role": "assistant",
                "content": turn['action']
            })
        
        return messages
    
    def get_current_prompt(self, current_observation: str, last_result: str = "") -> List[Dict[str, str]]:
        """Get messages for current turn"""
        messages = self.get_messages()
        
        # Add current observation as new user message
        user_content = f"Observation:\n{current_observation}"
        if last_result:
            user_content += f"\n\nResult of last action:\n{last_result}"
        
        messages.append({
            "role": "user",
            "content": user_content
        })
        
        return messages
    
    def clear(self):
        """Clear context history"""
        self.turns = []


# =============================================================================
# OUTPUT FORMATTING (Hackathon Compliance)
# =============================================================================

def emit_start(task_name: str, env_name: str = "cloudsoc", model_name: str = MODEL_NAME):
    """Emit [START] line"""
    print(f"[START] task={task_name} env={env_name} model={model_name}")
    sys.stdout.flush()


def emit_step(step: int, action: str, reward: float, done: bool, error: Optional[str]):
    """Emit [STEP] line"""
    done_str = "true" if done else "false"
    error_str = error if error else "null"
    # Escape action string for single-line output
    action_clean = action.replace('\n', ' ').replace('\r', '')[:100]
    print(f"[STEP] step={step} action={action_clean} reward={reward:.2f} done={done_str} error={error_str}")
    sys.stdout.flush()


def emit_end(success: bool, steps: int, rewards: List[float]):
    """Emit [END] line"""
    success_str = "true" if success else "false"
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(f"[END] success={success_str} steps={steps} rewards={rewards_str}")
    sys.stdout.flush()


# =============================================================================
# LLM INTERACTION
# =============================================================================

def call_llm(messages: List[Dict[str, str]], temperature: float = 0.5, retry_count: int = 0) -> str:
    """
    Call the LLM with given messages via Hugging Face Inference API.
    
    Optimized for Qwen2.5-3B-Instruct on 2vCPU/8GB RAM.
    Implements adaptive temperature: increases on retries for diversity.
    Returns the raw response content.
    """
    
    # Validate HF_TOKEN at runtime (required per hackathon guidelines)
    if not HF_TOKEN:
        error_msg = "HF_TOKEN environment variable is required for inference"
        sys.stderr.write(f"[ERROR] {error_msg}\n")
        sys.stderr.flush()
        return json.dumps({
            "thought": error_msg,
            "tool": "aws.soc.get_alerts",
            "args": {}
        })
    
    # Adaptive temperature: increase slightly on retries to get different outputs
    # Lower baseline temp (0.5) for 3B model to be more deterministic
    adaptive_temp = min(0.9, temperature + (retry_count * 0.15))
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=adaptive_temp,
            max_tokens=MAX_TOKENS,  # Optimized for 8GB RAM
            timeout=45.0  # Slightly longer timeout for smaller model
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)[:100]
        # Log error but still return valid JSON fallback
        sys.stderr.write(f"[LLM_ERROR] {error_type}: {error_msg}\n")
        sys.stderr.flush()
        return json.dumps({
            "thought": f"LLM API error ({error_type}): {error_msg}",
            "tool": "aws.soc.get_alerts",
            "args": {}
        })


def parse_llm_response(response: str) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Parse LLM response into tool call dict.
    
    Handles multiple response formats:
    - Clean JSON
    - Markdown code blocks
    - JSON embedded in text
    - Partial/malformed JSON with recovery
    
    Returns (parsed_dict, error_message)
    """
    
    if not response:
        return None, "Empty response from LLM"
    
    response = response.strip()
    
    # Strategy 1: Handle markdown code blocks
    if "```json" in response:
        match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if match:
            response = match.group(1).strip()
    elif "```" in response:
        match = re.search(r'```\s*(.*?)\s*```', response, re.DOTALL)
        if match:
            response = match.group(1).strip()
    
    # Strategy 2: Find JSON object with nested braces support
    # This handles cases where JSON is embedded in explanation text
    brace_count = 0
    json_start = -1
    json_end = -1
    
    for i, char in enumerate(response):
        if char == '{':
            if brace_count == 0:
                json_start = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and json_start != -1:
                json_end = i + 1
                break
    
    if json_start != -1 and json_end != -1:
        response = response[json_start:json_end]
    
    # Strategy 3: Try to parse
    try:
        parsed = json.loads(response)
        
        # Validate required fields
        if "tool" not in parsed:
            # Try to extract tool from response text
            tool_match = re.search(r'"tool"\s*:\s*"([^"]+)"', response)
            if tool_match:
                parsed["tool"] = tool_match.group(1)
            else:
                return None, "Missing 'tool' field in response"
        
        # Ensure args is a dict
        if "args" not in parsed:
            parsed["args"] = {}
        elif not isinstance(parsed["args"], dict):
            parsed["args"] = {}
        
        # Ensure thought exists
        if "thought" not in parsed:
            parsed["thought"] = "No reasoning provided"
        
        return parsed, None
        
    except json.JSONDecodeError as e:
        # Strategy 4: Try to recover partial JSON
        recovery_attempts = [
            response + '}',
            response + '"}',
            response + '"}}',
            re.sub(r',\s*}', '}', response),  # Remove trailing commas
            re.sub(r"'", '"', response),  # Replace single quotes
        ]
        
        for attempt in recovery_attempts:
            try:
                parsed = json.loads(attempt)
                if "tool" in parsed:
                    if "args" not in parsed:
                        parsed["args"] = {}
                    if "thought" not in parsed:
                        parsed["thought"] = "Recovered from partial response"
                    return parsed, None
            except:
                continue
        
        return None, f"JSON parse error: {str(e)}"


def create_fallback_action(step: int, last_error: Optional[str] = None) -> Dict:
    """
    Create a safe fallback action when parsing fails.
    
    Uses step count to vary fallback actions and avoid loops.
    """
    
    fallback_sequence = [
        {"tool": "aws.soc.get_alerts", "args": {}},
        {"tool": "aws.guardduty.get_findings", "args": {}},
        {"tool": "aws.cloudtrail.lookup_events", "args": {}},
        {"tool": "aws.ec2.describe", "args": {}},
        {"tool": "aws.iam.describe_role", "args": {}},
    ]
    
    action = fallback_sequence[step % len(fallback_sequence)]
    action["thought"] = f"Fallback action (parse failed): exploring with {action['tool']}"
    
    return action


# =============================================================================
# MAIN EVALUATION LOOP
# =============================================================================

def run_episode(
    task: str = "easy",
    seed: Optional[int] = None,
    initial_state: Optional[CloudState] = None,
    verbose: bool = False
) -> Tuple[bool, int, List[float], Optional[CloudState]]:
    """
    Run a single episode of the environment.
    
    Args:
        task: Difficulty level
        seed: Random seed for reproducibility
        initial_state: State from previous task (for campaigns)
        verbose: Print detailed output
    
    Returns:
        (success, steps, rewards, final_state)
    """
    
    # Create environment
    env = CloudSOCEnv(
        task=task,
        seed=seed,
        initial_state=initial_state,
        verbose=verbose
    )
    
    # Initialize context window (Mechanic #6)
    context = ContextWindow(
        system_prompt=env.get_system_prompt(),
        max_turns=MAX_CONTEXT_TURNS
    )
    
    # Reset environment
    obs, info = env.reset()
    
    # Emit start
    emit_start(task_name=task, env_name="cloudsoc", model_name=MODEL_NAME)
    
    # Episode tracking
    rewards: List[float] = []
    steps = 0
    done = False
    success = False
    last_result = "Episode started. Review the alerts and begin your investigation."
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    try:
        while not done and steps < env.max_steps:
            steps += 1
            
            # Update system prompt with current state (dynamic prompting)
            context.system_prompt = env.get_system_prompt()
            
            # Get LLM response with retry logic
            action_dict = None
            parse_error = None
            
            for retry in range(MAX_RETRIES):
                # Build prompt with sliding context
                messages = context.get_current_prompt(obs, last_result)
                
                # Call LLM with adaptive temperature
                llm_response = call_llm(messages, retry_count=retry)
                
                if verbose:
                    print(f"\n--- LLM Response (step {steps}, attempt {retry + 1}) ---")
                    print(llm_response[:500])
                
                # Parse response
                action_dict, parse_error = parse_llm_response(llm_response)
                
                if action_dict:
                    consecutive_errors = 0
                    break
                
                # Add error feedback for retry
                if retry < MAX_RETRIES - 1:
                    last_result = f"ERROR: {parse_error}. You MUST respond with valid JSON: {{\"thought\": \"...\", \"tool\": \"...\", \"args\": {{}}}}"
                    time.sleep(RETRY_DELAY)
            
            # Use fallback if all retries failed
            if not action_dict:
                action_dict = create_fallback_action(steps, parse_error)
                consecutive_errors += 1
                if verbose:
                    print(f"Using fallback action after {MAX_RETRIES} failed attempts")
            
            # Safety check: too many consecutive errors might indicate a stuck agent
            if consecutive_errors >= max_consecutive_errors:
                if verbose:
                    print(f"Too many consecutive errors ({consecutive_errors}), attempting incident close")
                # Try to close incident gracefully
                action_dict = {
                    "thought": "Multiple errors occurred, attempting to close incident with available information",
                    "tool": "aws.soc.close_incident",
                    "args": {"timeline": env.state.agent_timeline or ["Investigation incomplete due to errors"]}
                }
            
            # Convert to JSON string for environment
            action_str = json.dumps(action_dict)
            
            # Execute step
            obs, reward, terminated, truncated, info = env.step(action_str)
            
            # Track results
            rewards.append(reward)
            done = terminated or truncated
            
            # Get action summary for output
            tool_name = action_dict.get('tool', 'unknown')
            args_str = json.dumps(action_dict.get('args', {}))
            if len(args_str) > 50:
                args_str = args_str[:47] + "..."
            action_summary = f"{tool_name}({args_str})"
            
            # Emit step
            emit_step(
                step=steps,
                action=action_summary,
                reward=reward,
                done=done,
                error=info.get("last_action_error")
            )
            
            # Update context window
            context.add_turn(
                observation=obs,
                action=action_str,
                result=json.dumps({"reward": round(reward, 4), "error": info.get("last_action_error")})
            )
            
            # Prepare result for next iteration
            error_msg = info.get("last_action_error")
            if error_msg:
                last_result = f"ERROR: {error_msg}\nReward: {reward:.4f}\nReconsider your approach."
            else:
                last_result = f"SUCCESS\nReward: {reward:.4f}\nContinue with the investigation."
            
            # Check for explicit success (incident closed successfully)
            if terminated and not info.get("last_action_error"):
                final_scores = env.calculate_final_score()
                success = final_scores.get("weighted_total", 0) >= 0.4
        
        # Determine final success status
        if not success:
            # Check if we discovered enough flags
            required = set(env.scenario["required_flags"])
            discovered = set(info.get("discovered_flags", []))
            success = len(discovered.intersection(required)) >= len(required) * 0.6
    
    except KeyboardInterrupt:
        if verbose:
            print("\nInterrupted by user")
        success = False
    
    except Exception as e:
        if verbose:
            traceback.print_exc()
        # Emit error step
        emit_step(
            step=steps,
            action="error",
            reward=-1.0,
            done=True,
            error=str(e)[:100]
        )
        rewards.append(-1.0)
        success = False
    
    finally:
        # Always emit end
        emit_end(success=success, steps=steps, rewards=rewards)
        
        # Get final state for campaign continuity
        final_state = env.get_state_for_next_task()
        
        env.close()
    
    return success, steps, rewards, final_state


def run_campaign(
    seed: Optional[int] = None,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Run full multi-task campaign (Mechanic #11).
    
    Runs easy -> medium -> hard with shared state.
    """
    
    results = {
        "tasks": {},
        "overall_success": False,
        "total_steps": 0,
        "total_rewards": []
    }
    
    current_state = None
    tasks_passed = 0
    
    for task in ["easy", "medium", "hard"]:
        if verbose:
            print(f"\n{'='*50}")
            print(f"Starting Task: {task.upper()}")
            print(f"{'='*50}\n")
        
        success, steps, rewards, final_state = run_episode(
            task=task,
            seed=seed,
            initial_state=current_state,
            verbose=verbose
        )
        
        results["tasks"][task] = {
            "success": success,
            "steps": steps,
            "total_reward": sum(rewards)
        }
        
        results["total_steps"] += steps
        results["total_rewards"].extend(rewards)
        
        if success:
            tasks_passed += 1
            current_state = final_state  # Pass state to next task
        else:
            # Campaign fails if any task fails
            break
    
    results["overall_success"] = tasks_passed == 3
    results["tasks_passed"] = tasks_passed
    
    return results


def run_single_task(
    task: str = "easy",
    seed: Optional[int] = None,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Run a single task evaluation.
    
    This is the main entry point for hackathon evaluation.
    """
    
    success, steps, rewards, _ = run_episode(
        task=task,
        seed=seed,
        verbose=verbose
    )
    
    return {
        "task": task,
        "success": success,
        "steps": steps,
        "total_reward": sum(rewards),
        "rewards": rewards
    }


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """Main entry point for inference script"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description="OpenEnv-CloudSOC Inference")
    parser.add_argument(
        "--task", 
        type=str, 
        default="easy",
        choices=["easy", "medium", "hard", "campaign"],
        help="Task difficulty or 'campaign' for full run"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    args = parser.parse_args()
    
    if args.task == "campaign":
        results = run_campaign(seed=args.seed, verbose=args.verbose)
        if args.verbose:
            print(f"\n=== Campaign Results ===")
            print(json.dumps(results, indent=2))
    else:
        results = run_single_task(
            task=args.task,
            seed=args.seed,
            verbose=args.verbose
        )
        if args.verbose:
            print(f"\n=== Task Results ===")
            print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
