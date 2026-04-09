import json

def _extract_actions(trajectory):
    """
    Safely extracts a list of action strings from the agent's trajectory.
    Handles different OpenEnv trajectory formats (list of dicts, objects, or strings).
    """
    actions = []
    for step in trajectory:
        # If it's a dictionary containing an action key
        if isinstance(step, dict) and 'action' in step:
            actions.append(str(step['action']))
        # If it's a raw string
        elif isinstance(step, str):
            actions.append(step)
        # If it's a custom object
        elif hasattr(step, 'action'):
            actions.append(str(step.action))
        else:
            # Fallback: just cast the step to string and hope we can substring match
            actions.append(str(step))
    return actions

def grade_easy(trajectory):
    """
    EASY TASK: Basic Alert Triage
    Goal: The agent must read the alerts, identify the compromised EC2, and isolate it.
    """
    actions = _extract_actions(trajectory)
    actions_str = " ".join(actions).lower()
    score = 0.0
    
    # 1. Did they pull the SOC alerts? (30% credit)
    if "get_alerts" in actions_str:
        score += 0.3
        
    # 2. Did they investigate the EC2 instances? (30% credit)
    if "describe_instances" in actions_str:
        score += 0.3
        
    # 3. Did they successfully isolate the instance? (40% credit)
    if "isolate_instance" in actions_str:
        score += 0.4
        
    return round(min(max(score, 0.01), 0.99), 2)

def grade_medium(trajectory):
    """
    MEDIUM TASK: Log Investigation & IAM Revocation
    Goal: Read alerts, check CloudTrail logs for stolen credentials, revoke IAM role, and isolate.
    """
    actions = _extract_actions(trajectory)
    actions_str = " ".join(actions).lower()
    score = 0.0
    
    # 1. Pulled alerts? (10% credit)
    if "get_alerts" in actions_str:
        score += 0.1
        
    # 2. Checked CloudTrail logs to trace the credentials? (30% credit)
    if "cloudtrail" in actions_str or "lookup_events" in actions_str:
        score += 0.3
        
    # 3. Revoked the compromised IAM sessions? (30% credit)
    if "revoke_role" in actions_str or "iam" in actions_str:
        score += 0.3
        
    # 4. Isolated the original compromised instance? (30% credit)
    if "isolate_instance" in actions_str:
        score += 0.3

    return round(min(max(score, 0.01), 0.99), 2)

def grade_hard(trajectory):
    """
    HARD TASK: Active Ransomware / WAF Blocking / Trap Avoidance
    Goal: Block malicious IP, isolate instance, but DO NOT terminate the production DB.
    """
    actions = _extract_actions(trajectory)
    actions_str = " ".join(actions).lower()
    score = 0.0
    
    # FATAL ERROR: Did they kill the production database? (Automatic Failure)
    if "terminate_db" in actions_str or "stop_db" in actions_str:
        return 0.01
    
    # 1. Investigated alerts and logs? (20% credit)
    if "get_alerts" in actions_str:
        score += 0.1
    if "cloudtrail" in actions_str:
        score += 0.1
        
    # 2. Blocked the exfiltration IP at the WAF level? (40% credit)
    if "block_ip" in actions_str or "waf" in actions_str:
        score += 0.4
        
    # 3. Isolated the EC2 instance? (40% credit)
    if "isolate_instance" in actions_str:
        score += 0.4

    return round(min(max(score, 0.01), 0.99), 2)
