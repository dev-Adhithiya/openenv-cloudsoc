#!/usr/bin/env python
"""
Quick validation of stdout format compliance
Run: python validate_format.py <output_file>
"""

import sys
import re
import json

def validate_format(lines):
    """Validate [START], [STEP], [END] format"""
    
    errors = []
    
    # Must have exactly one [START]
    start_lines = [l for l in lines if l.startswith("[START]")]
    if len(start_lines) != 1:
        errors.append(f"Expected 1 [START] line, found {len(start_lines)}")
    else:
        start = start_lines[0]
        # Validate format: [START] task=X env=Y model=Z
        if not re.match(r'^\[START\]\s+task=\S+\s+env=\S+\s+model=\S+', start):
            errors.append(f"[START] format invalid: {start}")
    
    # Must have at least one [STEP]
    step_lines = [l for l in lines if l.startswith("[STEP]")]
    if len(step_lines) == 0:
        errors.append("No [STEP] lines found")
    else:
        # Validate each [STEP]
        for step_line in step_lines:
            # Format: [STEP] step=N action=... reward=X.XX done=true|false error=...|null
            if not re.match(r'^\[STEP\]\s+step=\d+\s+', step_line):
                errors.append(f"Invalid [STEP] format: {step_line[:80]}")
            
            # Check required fields
            if 'step=' not in step_line:
                errors.append(f"[STEP] missing step field: {step_line[:80]}")
            if 'action=' not in step_line:
                errors.append(f"[STEP] missing action field: {step_line[:80]}")
            if 'reward=' not in step_line:
                errors.append(f"[STEP] missing reward field: {step_line[:80]}")
            if 'done=' not in step_line:
                errors.append(f"[STEP] missing done field: {step_line[:80]}")
            if 'error=' not in step_line:
                errors.append(f"[STEP] missing error field: {step_line[:80]}")
            
            # Check done is boolean
            if 'done=true' not in step_line and 'done=false' not in step_line:
                errors.append(f"[STEP] done must be true|false: {step_line[:80]}")
    
    # Must have exactly one [END]
    end_lines = [l for l in lines if l.startswith("[END]")]
    if len(end_lines) != 1:
        errors.append(f"Expected 1 [END] line, found {len(end_lines)}")
    else:
        end = end_lines[0]
        # Format: [END] success=true|false steps=N score=X.XXX rewards=...
        if not re.match(r'^\[END\]\s+success=', end):
            errors.append(f"[END] format invalid: {end}")
        
        # Check required fields
        required_fields = ['success=', 'steps=', 'score=', 'rewards=']
        for field in required_fields:
            if field not in end:
                errors.append(f"[END] missing {field} field")
        
        # Check success is boolean
        if 'success=true' not in end and 'success=false' not in end:
            errors.append(f"[END] success must be true|false: {end}")
        
        # Check score is float
        score_match = re.search(r'score=([\d.]+)', end)
        if not score_match:
            errors.append(f"[END] invalid score format: {end}")
        else:
            try:
                score = float(score_match.group(1))
                if not (0.1 <= score <= 0.9):
                    errors.append(f"[END] score must be between 0.1 and 0.9, got {score}")
            except ValueError:
                errors.append(f"[END] score not a valid float: {score_match.group(1)}")
        
        # Check rewards format (comma-separated floats)
        rewards_match = re.search(r'rewards=([\d.,]+)', end)
        if not rewards_match:
            errors.append(f"[END] invalid rewards format: {end}")
    
    # Check single-line format (no embedded newlines in fields)
    for line in lines:
        if line.startswith("["):
            # Action field might have spaces but shouldn't have newlines
            if '\n' in line.split('error=')[-1]:
                errors.append(f"Line contains embedded newlines: {line[:80]}")
    
    return errors


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            lines = f.read().strip().split('\n')
    else:
        lines = sys.stdin.read().strip().split('\n')
    
    errors = validate_format(lines)
    
    if errors:
        print("❌ Format validation FAILED:")
        for i, error in enumerate(errors, 1):
            print(f"  {i}. {error}")
        sys.exit(1)
    else:
        print("✓ Format validation PASSED")
        print(f"  {len([l for l in lines if l.startswith('[START]')])} [START] lines")
        print(f"  {len([l for l in lines if l.startswith('[STEP]')])} [STEP] lines")
        print(f"  {len([l for l in lines if l.startswith('[END]')])} [END] lines")
        sys.exit(0)
