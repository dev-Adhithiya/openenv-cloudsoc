"""
Unit Tests for inference.py
=============================
Tests LLM interaction, parsing, retry logic, context window, and output formatting.

Run: python test_inference.py [--verbose]
"""

import json
import unittest
from io import StringIO
import sys
from unittest.mock import Mock, patch, MagicMock

# Import functions to test
from inference import (
    parse_llm_response,
    create_fallback_action,
    ContextWindow,
    emit_start,
    emit_step,
    emit_end,
    call_llm,
    run_episode,
    MAX_TOKENS,
    MAX_CONTEXT_TURNS,
)


class TestLLMParsing(unittest.TestCase):
    """Test LLM response parsing with various formats"""
    
    def test_parse_clean_json(self):
        """Test parsing clean JSON response"""
        response = json.dumps({
            "thought": "Check alerts",
            "tool": "aws.soc.get_alerts",
            "args": {}
        })
        
        parsed, error = parse_llm_response(response)
        
        self.assertIsNotNone(parsed)
        self.assertIsNone(error)
        self.assertEqual(parsed["tool"], "aws.soc.get_alerts")
        self.assertEqual(parsed["thought"], "Check alerts")
    
    def test_parse_json_with_markdown_block(self):
        """Test parsing JSON inside markdown code block"""
        response = '''Here's my action:
```json
{
  "thought": "Query logs",
  "tool": "aws.cloudwatch.query_deep",
  "args": {"log_group": "/aws/ec2"}
}
```
Now I'll wait for results.'''
        
        parsed, error = parse_llm_response(response)
        
        self.assertIsNotNone(parsed)
        self.assertIsNone(error)
        self.assertEqual(parsed["tool"], "aws.cloudwatch.query_deep")
    
    def test_parse_json_embedded_in_text(self):
        """Test parsing JSON embedded in explanation text"""
        response = '''I need to check the alerts. My action is:
{
  "thought": "Get current alerts",
  "tool": "aws.soc.get_alerts",
  "args": {}
}
This will show me what's happening.'''
        
        parsed, error = parse_llm_response(response)
        
        self.assertIsNotNone(parsed)
        self.assertIsNone(error)
        self.assertEqual(parsed["tool"], "aws.soc.get_alerts")
    
    def test_parse_json_with_single_quotes(self):
        """Test parsing JSON with single quotes (malformed but recoverable)"""
        response = "{'thought': 'Check alerts', 'tool': 'aws.soc.get_alerts', 'args': {}}"
        
        parsed, error = parse_llm_response(response)
        
        self.assertIsNotNone(parsed)
        self.assertIsNone(error)
        self.assertEqual(parsed["tool"], "aws.soc.get_alerts")
    
    def test_parse_json_with_trailing_comma(self):
        """Test parsing JSON with trailing commas (malformed but recoverable)"""
        response = '''{
  "thought": "Check alerts",
  "tool": "aws.soc.get_alerts",
  "args": {},
}'''
        
        parsed, error = parse_llm_response(response)
        
        self.assertIsNotNone(parsed)
        self.assertIsNone(error)
        self.assertEqual(parsed["tool"], "aws.soc.get_alerts")
    
    def test_parse_missing_tool_field(self):
        """Test handling of JSON missing tool field"""
        response = json.dumps({
            "thought": "Something",
            "args": {}
        })
        
        parsed, error = parse_llm_response(response)
        
        self.assertIsNone(parsed)
        self.assertIsNotNone(error)
        self.assertIn("tool", error.lower())
    
    def test_parse_empty_response(self):
        """Test handling of empty response"""
        parsed, error = parse_llm_response("")
        
        self.assertIsNone(parsed)
        self.assertIsNotNone(error)
    
    def test_parse_completely_invalid_json(self):
        """Test handling of completely invalid JSON"""
        response = "this is not json at all gdfshjkl"
        
        parsed, error = parse_llm_response(response)
        
        self.assertIsNone(parsed)
        self.assertIsNotNone(error)
    
    def test_parse_adds_missing_args(self):
        """Test that missing args dict is added"""
        response = json.dumps({
            "thought": "Act",
            "tool": "aws.soc.get_alerts"
        })
        
        parsed, error = parse_llm_response(response)
        
        self.assertIsNotNone(parsed)
        self.assertIn("args", parsed)
        self.assertEqual(parsed["args"], {})
    
    def test_parse_adds_default_thought(self):
        """Test that missing thought is added"""
        response = json.dumps({
            "tool": "aws.soc.get_alerts",
            "args": {}
        })
        
        parsed, error = parse_llm_response(response)
        
        self.assertIsNotNone(parsed)
        self.assertIn("thought", parsed)


class TestFallbackAction(unittest.TestCase):
    """Test fallback action generation"""
    
    def test_fallback_action_structure(self):
        """Test that fallback action has required fields"""
        action = create_fallback_action(step=1)
        
        self.assertIn("tool", action)
        self.assertIn("args", action)
        self.assertIn("thought", action)
    
    def test_fallback_varies_by_step(self):
        """Test that fallback varies by step to avoid loops"""
        action1 = create_fallback_action(step=1)
        action2 = create_fallback_action(step=2)
        action3 = create_fallback_action(step=3)
        
        tools = [action1["tool"], action2["tool"], action3["tool"]]
        # Should not all be the same
        self.assertGreater(len(set(tools)), 1)
    
    def test_fallback_has_valid_tool(self):
        """Test that fallback action uses valid tools"""
        valid_tools = [
            "aws.soc.get_alerts",
            "aws.guardduty.get_findings",
            "aws.cloudtrail.lookup_events",
            "aws.ec2.describe",
            "aws.iam.describe_role",
        ]
        
        action = create_fallback_action(step=1)
        self.assertIn(action["tool"], valid_tools)


class TestContextWindow(unittest.TestCase):
    """Test context window sliding mechanism"""
    
    def test_context_window_init(self):
        """Test context window initialization"""
        context = ContextWindow(system_prompt="Test prompt", max_turns=3)
        
        self.assertEqual(context.system_prompt, "Test prompt")
        self.assertEqual(context.max_turns, 3)
        self.assertEqual(len(context.turns), 0)
    
    def test_context_window_add_turn(self):
        """Test adding turns to context"""
        context = ContextWindow(max_turns=3)
        
        context.add_turn(
            observation="Obs 1",
            action="Action 1",
            result="Result 1"
        )
        
        self.assertEqual(len(context.turns), 1)
        self.assertEqual(context.turns[0]["observation"], "Obs 1")
    
    def test_context_window_sliding(self):
        """Test that context window slides when exceeding max"""
        context = ContextWindow(max_turns=2)
        
        for i in range(5):
            context.add_turn(
                observation=f"Obs {i}",
                action=f"Action {i}",
                result=f"Result {i}"
            )
        
        # Should only keep last 2 turns
        self.assertEqual(len(context.turns), 2)
        self.assertEqual(context.turns[0]["observation"], "Obs 3")
        self.assertEqual(context.turns[1]["observation"], "Obs 4")
    
    def test_context_get_messages_format(self):
        """Test that get_messages returns proper OpenAI format"""
        context = ContextWindow(system_prompt="System", max_turns=2)
        context.add_turn(
            observation="Obs",
            action='{"tool": "test"}',
            result="Result"
        )
        
        messages = context.get_messages()
        
        # Should have system + user + assistant
        self.assertGreaterEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], "System")
    
    def test_context_clear(self):
        """Test clearing context"""
        context = ContextWindow()
        context.add_turn("O", "A", "R")
        
        context.clear()
        
        self.assertEqual(len(context.turns), 0)


class TestOutputFormatting(unittest.TestCase):
    """Test stdout output formatting for hackathon compliance"""
    
    def test_emit_start_format(self):
        """Test [START] line format"""
        output = StringIO()
        with patch('sys.stdout', output):
            emit_start(task_name="easy", env_name="cloudsoc", model_name="TestModel")
        
        result = output.getvalue()
        self.assertIn("[START]", result)
        self.assertIn("task=easy", result)
        self.assertIn("env=cloudsoc", result)
        self.assertIn("model=TestModel", result)
    
    def test_emit_step_format(self):
        """Test [STEP] line format"""
        output = StringIO()
        with patch('sys.stdout', output):
            emit_step(
                step=1,
                action='aws.soc.get_alerts({})',
                reward=0.05,
                done=False,
                error=None
            )
        
        result = output.getvalue()
        self.assertIn("[STEP]", result)
        self.assertIn("step=1", result)
        self.assertIn("reward=0.05", result)
        self.assertIn("done=false", result)
        self.assertIn("error=null", result)
    
    def test_emit_step_with_error(self):
        """Test [STEP] line with error"""
        output = StringIO()
        with patch('sys.stdout', output):
            emit_step(
                step=1,
                action='aws.invalid()',
                reward=-0.02,
                done=False,
                error="VALIDATION_ERROR"
            )
        
        result = output.getvalue()
        self.assertIn("error=VALIDATION_ERROR", result)
    
    def test_emit_end_format(self):
        """Test [END] line format"""
        output = StringIO()
        with patch('sys.stdout', output):
            emit_end(success=True, steps=5, score=0.75, rewards=[0.1, 0.2, 0.15, 0.3, 0.0])
        
        result = output.getvalue()
        self.assertIn("[END]", result)
        self.assertIn("success=true", result)
        self.assertIn("steps=5", result)
        # Score should be between 0.1 and 0.9
        self.assertIn("score=0.750", result)
        score_val = float(result.split('score=')[1].split()[0])
        self.assertGreaterEqual(score_val, 0.1)
        self.assertLessEqual(score_val, 0.9)
        self.assertIn("rewards=0.10,0.20,0.15,0.30,0.00", result)
    
    def test_emit_end_newlines(self):
        """Test that output lines have no embedded newlines"""
        output = StringIO()
        with patch('sys.stdout', output):
            emit_step(
                step=1,
                action='tool({"param": "value"})',
                reward=0.0,
                done=False,
                error=None
            )
        
        result = output.getvalue().strip()
        # Should be single line
        self.assertEqual(result.count('\n'), 0)


class TestCallLLMFallback(unittest.TestCase):
    """Test LLM calling with error handling"""
    
    @patch('inference.client')
    def test_call_llm_success(self, mock_client):
        """Test successful LLM call"""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"tool": "test", "args": {}}'
        mock_client.chat.completions.create.return_value = mock_response
        
        result = call_llm([{"role": "user", "content": "Test"}])
        
        self.assertIsNotNone(result)
        self.assertIn("tool", result)
    
    @patch('inference.client')
    def test_call_llm_timeout_fallback(self, mock_client):
        """Test that LLM timeout returns fallback"""
        mock_client.chat.completions.create.side_effect = TimeoutError("Timeout")
        
        result = call_llm([{"role": "user", "content": "Test"}])
        
        # Should return fallback action string
        self.assertIsNotNone(result)
        self.assertIsInstance(result, str)


class TestMaxConstraints(unittest.TestCase):
    """Test that 2vCPU/8GB constraints are respected"""
    
    def test_max_tokens_set(self):
        """Test that MAX_TOKENS is reasonable for 8GB RAM"""
        # Should be <= 512 for lightweight 3B model
        self.assertLessEqual(MAX_TOKENS, 512)
    
    def test_max_context_turns_set(self):
        """Test that MAX_CONTEXT_TURNS is reasonable for 8GB RAM"""
        # Should be <= 8 to control memory
        self.assertLessEqual(MAX_CONTEXT_TURNS, 8)


class TestEpisodeIntegration(unittest.TestCase):
    """Integration tests for episode execution"""
    
    @patch('inference.CloudSOCEnv')
    @patch('inference.call_llm')
    def test_episode_basic_flow(self, mock_call_llm, mock_env_class):
        """Test basic episode flow with mocked environment"""
        
        # Mock environment
        mock_env = MagicMock()
        mock_env_class.return_value = mock_env
        mock_env.reset.return_value = ("obs", {"action": "reset"})
        mock_env.max_steps = 5
        mock_env.get_system_prompt.return_value = "Test system prompt"
        
        # Mock steps
        mock_env.step.side_effect = [
            ("obs", 0.1, False, False, {"last_action_error": None}),
            ("obs", 0.05, True, False, {"last_action_error": None}),  # Done
        ]
        
        mock_env.get_state_for_next_task.return_value = None
        
        # Mock LLM response
        valid_action = json.dumps({
            "thought": "Test",
            "tool": "aws.soc.get_alerts",
            "args": {}
        })
        mock_call_llm.return_value = valid_action
        
        # Run episode
        output = StringIO()
        with patch('sys.stdout', output):
            success, steps, rewards, _ = run_episode(
                task="easy",
                seed=42,
                verbose=False
            )
        
        # Verify output format
        lines = output.getvalue().strip().split('\n')
        self.assertTrue(lines[0].startswith("[START]"))
        self.assertTrue(any(line.startswith("[STEP]") for line in lines))
        self.assertTrue(lines[-1].startswith("[END]"))
    
    @patch('inference.CloudSOCEnv')
    @patch('inference.call_llm')
    def test_episode_handles_parse_errors(self, mock_call_llm, mock_env_class):
        """Test that episode handles parsing errors gracefully"""
        
        mock_env = MagicMock()
        mock_env_class.return_value = mock_env
        mock_env.reset.return_value = ("obs", {})
        mock_env.max_steps = 3
        mock_env.get_system_prompt.return_value = "Test"
        
        # First call returns invalid JSON (triggers fallback), second succeeds
        mock_call_llm.side_effect = [
            "completely invalid json",
            json.dumps({"thought": "Act", "tool": "aws.soc.get_alerts", "args": {}}),
        ]
        
        mock_env.step.side_effect = [
            ("obs", -0.02, False, False, {"last_action_error": "PARSE_ERROR"}),
            ("obs", 0.1, True, False, {"last_action_error": None}),
        ]
        
        mock_env.get_state_for_next_task.return_value = None
        
        # Episode should complete without crashing
        output = StringIO()
        with patch('sys.stdout', output):
            success, steps, rewards, _ = run_episode(task="easy", verbose=False)
        
        # Should have run 2 steps
        self.assertEqual(steps, 2)


if __name__ == "__main__":
    import sys
    
    # Parse args
    verbose = "--verbose" in sys.argv
    if verbose:
        sys.argv.remove("--verbose")
    
    # Run tests
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2 if verbose else 1)
    result = runner.run(suite)
    
    sys.exit(0 if result.wasSuccessful() else 1)
