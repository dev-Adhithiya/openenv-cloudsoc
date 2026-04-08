"""
OpenEnv-CloudSOC: Cloud Security Operations Center Benchmark Environment
=========================================================================
A Gymnasium-compatible environment for evaluating LLM agents on cloud security
incident response. Implements Zero-DB architecture with in-memory state management.

Hardware Target: 2 vCPU / 8 GB RAM Docker container
Architecture: Thin Client, Deep State (no external databases)

Key Features:
- Realistic AWS cloud simulation with deceptive elements
- Progressive reward shaping through forensic kill-chain
- Strict causal dependencies for proper IR procedure
- Adversarial traps to test agent judgment
- Multi-task campaign with state persistence
- Comprehensive audit trail and analytics
"""

import random
import json
import hashlib
import copy
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union, Set
from enum import Enum
from dataclasses import dataclass, field
from pydantic import BaseModel, Field, validator
from collections import defaultdict
import gymnasium as gym
from gymnasium import spaces


# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

# Reward constants for fine-tuned scoring
REWARDS = {
    "FLAG_DISCOVERY": 0.02,
    "CRITICAL_ACTION": 0.10,
    "CONTAINMENT_ACTION": 0.05,
    "PARSE_ERROR": -0.02,
    "PRECONDITION_FAIL": -0.05,
    "EVIDENCE_DESTRUCTION": -1.0,
    "QUERY_BASIC": -0.01,
    "QUERY_DEEP": -0.05,
    "INVALID_TOOL": -0.01,
    "TIMELINE_BONUS_MAX": 0.5,
}

# Malicious IPs for realistic simulation
MALICIOUS_IPS = [
    "185.220.101.42",  # TOR exit node
    "45.155.205.233",  # Known C2
    "194.26.192.64",   # Bulletproof hosting
]

# Benign IPs for noise
BENIGN_IPS = [
    "10.0.0.1", "10.0.1.50", "10.0.5.20", "172.16.0.100",
    "192.168.1.10", "10.0.0.254", "172.31.0.1"
]


# =============================================================================
# PYDANTIC MODELS FOR TOOL ABSTRACTION (Mechanic #7)
# =============================================================================

class ToolArgs(BaseModel):
    """Base class for tool arguments"""
    class Config:
        extra = "forbid"


class CloudWatchQueryArgs(ToolArgs):
    log_group: str = Field(..., description="CloudWatch log group to query")
    start_time: Optional[str] = Field(None, description="ISO timestamp for query start")
    end_time: Optional[str] = Field(None, description="ISO timestamp for query end")
    filter_pattern: Optional[str] = Field(None, description="CloudWatch filter pattern")


class EC2ActionArgs(ToolArgs):
    instance_id: str = Field(..., pattern=r"^i-[a-f0-9]+$")


class IAMRoleArgs(ToolArgs):
    role_name: str = Field(..., min_length=1, max_length=64)


class IAMDetachArgs(ToolArgs):
    role_name: str
    instance_id: Optional[str] = None


class S3BucketArgs(ToolArgs):
    bucket_name: str = Field(..., pattern=r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")


class CredentialRotateArgs(ToolArgs):
    resource_type: str = Field(..., description="Type: 'rds', 'iam', 's3'")
    resource_id: str


class SnapshotArgs(ToolArgs):
    instance_id: str = Field(..., pattern=r"^i-[a-f0-9]+$")
    snapshot_type: str = Field(default="forensic", description="'forensic' or 'backup'")


class IncidentCloseArgs(ToolArgs):
    incident_id: str
    timeline: List[str] = Field(..., min_items=1, description="Ordered list of incident events")
    root_cause: Optional[str] = None
    remediation_summary: Optional[str] = None


class SecurityGroupArgs(ToolArgs):
    security_group_id: str = Field(..., pattern=r"^sg-[a-f0-9]+$")
    action: str = Field(..., description="'isolate' or 'restore'")


class InvestigateArgs(ToolArgs):
    target_type: str = Field(..., description="'ip', 'user', 'role', 'instance'")
    target_id: str


class ToolCall(BaseModel):
    """Strict tool call schema that agents must use"""
    thought: str = Field(..., description="1-sentence internal reasoning", max_length=500)
    tool: str = Field(..., description="Tool name to invoke")
    args: Dict[str, Any] = Field(default_factory=dict)

    @validator('tool')
    def validate_tool_name(cls, v):
        valid_tools = {
            'aws.cloudwatch.query_basic', 'aws.cloudwatch.query_deep',
            'aws.ec2.isolate', 'aws.ec2.terminate', 'aws.ec2.describe',
            'aws.ec2.snapshot', 'aws.iam.detach_role', 'aws.iam.revoke_credentials',
            'aws.iam.describe_role', 'aws.iam.list_policies',
            'aws.s3.get_bucket_policy', 'aws.s3.block_public_access',
            'aws.s3.list_objects', 'aws.rds.rotate_credentials',
            'aws.security_group.modify', 'aws.investigate',
            'aws.soc.close_incident', 'aws.soc.get_alerts',
            'aws.guardduty.get_findings', 'aws.cloudtrail.lookup_events',
            'aws.config.get_compliance', 'aws.ssm.run_command',
            'aws.lambda.list_functions', 'aws.sts.get_caller_identity'
        }
        if v not in valid_tools:
            raise ValueError(f"Unknown tool: {v}. Valid tools: {sorted(valid_tools)}")
        return v
    
    @validator('thought')
    def validate_thought(cls, v):
        if not v or len(v.strip()) < 5:
            raise ValueError("Thought must contain meaningful reasoning (min 5 chars)")
        return v.strip()


# =============================================================================
# STATE MODELS (In-Memory Cloud State)
# =============================================================================

class InstanceState(Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    ISOLATED = "isolated"
    TERMINATED = "terminated"


class IncidentPhase(Enum):
    INVESTIGATION = "investigation"
    CONTAINMENT = "containment"
    ERADICATION = "eradication"
    RECOVERY = "recovery"
    CLOSED = "closed"


@dataclass
class EC2Instance:
    instance_id: str
    state: InstanceState = InstanceState.RUNNING
    attached_roles: List[str] = field(default_factory=list)
    security_groups: List[str] = field(default_factory=list)
    is_compromised: bool = False
    has_forensic_snapshot: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IAMRole:
    role_name: str
    policies: List[str] = field(default_factory=list)
    is_compromised: bool = False
    is_detached: bool = False
    credentials_rotated: bool = False
    has_backdoor: bool = False


@dataclass
class S3Bucket:
    bucket_name: str
    is_public: bool = False
    contains_credentials: bool = False
    leaked_keys: List[str] = field(default_factory=list)
    public_access_blocked: bool = False


@dataclass
class LogEntry:
    timestamp: str
    source: str
    message: str
    severity: str  # INFO, WARN, ERROR, CRITICAL
    is_attack_indicator: bool = False
    is_noise: bool = False
    is_red_herring: bool = False


@dataclass 
class Alert:
    alert_id: str
    title: str
    severity: str
    source: str
    timestamp: str
    details: Dict[str, Any] = field(default_factory=dict)
    is_true_positive: bool = True


@dataclass
class CloudState:
    """Complete in-memory cloud infrastructure state"""
    instances: Dict[str, EC2Instance] = field(default_factory=dict)
    roles: Dict[str, IAMRole] = field(default_factory=dict)
    buckets: Dict[str, S3Bucket] = field(default_factory=dict)
    security_groups: Dict[str, Dict] = field(default_factory=dict)
    logs: List[LogEntry] = field(default_factory=list)
    alerts: List[Alert] = field(default_factory=list)
    credentials: Dict[str, Dict] = field(default_factory=dict)
    
    # Investigation state
    discovered_flags: set = field(default_factory=set)
    completed_actions: List[str] = field(default_factory=list)
    incident_phase: IncidentPhase = IncidentPhase.INVESTIGATION
    
    # Timeline tracking for grading
    agent_timeline: List[str] = field(default_factory=list)
    ground_truth_timeline: List[str] = field(default_factory=list)
    
    # Enhanced tracking
    evidence_collected: Dict[str, Any] = field(default_factory=dict)
    mitre_techniques: Set[str] = field(default_factory=set)
    ioc_indicators: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Serialize state for debugging/checkpointing"""
        return {
            "instances": {k: self._inst_to_dict(v) for k, v in self.instances.items()},
            "roles": {k: self._role_to_dict(v) for k, v in self.roles.items()},
            "buckets": {k: self._bucket_to_dict(v) for k, v in self.buckets.items()},
            "discovered_flags": list(self.discovered_flags),
            "completed_actions": self.completed_actions,
            "phase": self.incident_phase.value,
            "evidence_collected": self.evidence_collected,
        }
    
    def _inst_to_dict(self, inst: EC2Instance) -> Dict:
        return {
            "instance_id": inst.instance_id, "state": inst.state.value,
            "is_compromised": inst.is_compromised, "has_snapshot": inst.has_forensic_snapshot
        }
    
    def _role_to_dict(self, role: IAMRole) -> Dict:
        return {
            "role_name": role.role_name, "is_compromised": role.is_compromised,
            "is_detached": role.is_detached, "has_backdoor": role.has_backdoor
        }
    
    def _bucket_to_dict(self, bucket: S3Bucket) -> Dict:
        return {
            "bucket_name": bucket.bucket_name, "is_public": bucket.is_public,
            "public_access_blocked": bucket.public_access_blocked
        }


# =============================================================================
# SCENARIO DEFINITIONS (Multi-Task Campaign - Mechanic #11)
# =============================================================================

SCENARIOS = {
    "easy": {
        "name": "Leaky S3 Bucket Discovery",
        "description": "Identify and secure a publicly exposed S3 bucket containing sensitive data",
        "difficulty_multiplier": 1.0,
        "max_steps": 15,
        "ground_truth_timeline": [
            "Public S3 bucket detected",
            "Credentials discovered in bucket",
            "Public access blocked"
        ],
        "required_flags": {"s3_public_identified", "credentials_found", "public_access_blocked"},
        "phase_weights": {"investigation": 0.5, "containment": 0.3, "eradication": 0.1, "recovery": 0.1},
        "mitre_techniques": ["T1530"],  # Data from Cloud Storage Object
        "hints": [
            "Start by reviewing SOC alerts",
            "Check S3 bucket policies for public access",
            "Look for sensitive files in public buckets"
        ]
    },
    "medium": {
        "name": "Credential Compromise Response",
        "description": "Leaked credentials from S3 were used; trace and revoke all compromised access",
        "difficulty_multiplier": 1.5,
        "max_steps": 25,
        "ground_truth_timeline": [
            "Leaked credentials identified",
            "Compromised IAM role discovered",
            "Role detached from resources",
            "Credentials rotated"
        ],
        "required_flags": {"leaked_creds_identified", "compromised_role_found", "role_detached", "credentials_rotated"},
        "phase_weights": {"investigation": 0.3, "containment": 0.4, "eradication": 0.2, "recovery": 0.1},
        "mitre_techniques": ["T1078", "T1552"],  # Valid Accounts, Credentials in Files
        "hints": [
            "Trace credential usage in CloudTrail",
            "Identify which roles were compromised",
            "Detach roles before rotating credentials"
        ]
    },
    "hard": {
        "name": "Full Incident Response - Ransomware",
        "description": "Compromised credentials led to IAM backdoor and ransomware deployment. Full IR required.",
        "difficulty_multiplier": 2.0,
        "max_steps": 40,
        "ground_truth_timeline": [
            "Ransomware indicators detected",
            "Backdoor IAM role identified",
            "Forensic snapshot taken",
            "Compromised instance isolated",
            "Backdoor role removed",
            "All credentials rotated",
            "Systems verified clean"
        ],
        "required_flags": {
            "ransomware_detected", "backdoor_identified", "forensic_snapshot_taken",
            "instance_isolated", "backdoor_removed", "all_creds_rotated", "systems_verified"
        },
        "phase_weights": {"investigation": 0.25, "containment": 0.25, "eradication": 0.3, "recovery": 0.2},
        "mitre_techniques": ["T1486", "T1098", "T1078"],  # Data Encrypted, Account Manipulation
        "hints": [
            "Preserve evidence with snapshots before isolation",
            "Look for recently created IAM roles with admin access",
            "Check for encryption activity on instances"
        ]
    }
}


# =============================================================================
# MAIN ENVIRONMENT CLASS
# =============================================================================

class CloudSOCEnv(gym.Env):
    """
    OpenEnv-CloudSOC Gymnasium Environment
    
    Implements all 12 required mechanics for LLM agent evaluation on
    cloud security incident response tasks.
    """
    
    metadata = {"render_modes": ["human", "json"]}
    
    def __init__(
        self,
        task: str = "easy",
        seed: Optional[int] = None,
        render_mode: str = "json",
        initial_state: Optional[CloudState] = None,
        verbose: bool = False
    ):
        """
        Initialize the CloudSOC environment.
        
        Args:
            task: Difficulty level ("easy", "medium", "hard")
            seed: Random seed for deterministic behavior (Mechanic #9)
            render_mode: Output format ("human" or "json")
            initial_state: Pre-existing state for multi-task campaigns (Mechanic #11)
            verbose: Enable detailed logging
        """
        super().__init__()
        
        self.task = task
        self.seed_value = seed
        self.render_mode = render_mode
        self.verbose = verbose
        self.scenario = SCENARIOS[task]
        
        # Deterministic seeding (Mechanic #9)
        if seed is not None:
            random.seed(seed)
            self._deterministic = True
        else:
            self._deterministic = False
        
        # Initialize or inherit state (Mechanic #11)
        if initial_state is not None:
            self.state = initial_state
            self._inherited_state = True
        else:
            self.state = CloudState()
            self._inherited_state = False
        
        # Environment tracking
        self.current_step = 0
        self.max_steps = self.scenario["max_steps"]
        self.total_reward = 0.0
        self.rewards_history: List[float] = []
        self.action_history: List[Dict] = []
        self.done = False
        self.last_action_error: Optional[str] = None
        
        # Phase scoring (Mechanic #8)
        self.phase_scores = {
            "investigation": 0.0,
            "containment": 0.0,
            "eradication": 0.0,
            "recovery": 0.0
        }
        
        # Tool usage analytics
        self.tool_usage: Dict[str, int] = {}
        self.query_costs = 0.0
        
        # Gymnasium spaces (simplified for LLM)
        self.action_space = spaces.Text(max_length=2048)
        self.observation_space = spaces.Text(max_length=8192)
        
        # Generate initial scenario
        self._generate_scenario()
    
    def _generate_scenario(self):
        """Generate the cloud environment state based on task difficulty"""
        
        if self._inherited_state and self.task != "easy":
            # Inherit and extend state for campaign continuity
            self._extend_scenario_state()
        else:
            # Fresh state generation
            self._generate_fresh_state()
        
        # Generate logs with noise (Mechanic #1)
        self._generate_logs()
        
        # Generate alerts
        self._generate_alerts()
    
    def _generate_fresh_state(self):
        """Generate brand new cloud state"""
        
        # Generate instance IDs deterministically if seeded
        instance_suffix = f"{random.randint(0, 0xffffffff):08x}"
        sg_suffix = f"{random.randint(0, 0xffffffff):08x}"
        
        # Create EC2 instances
        compromised_instance = EC2Instance(
            instance_id=f"i-{instance_suffix}",
            state=InstanceState.RUNNING,
            attached_roles=["WebServerRole"],
            security_groups=[f"sg-{sg_suffix}"],
            is_compromised=self.task in ["medium", "hard"],
            metadata={"name": "web-server-prod", "environment": "production"}
        )
        self.state.instances[compromised_instance.instance_id] = compromised_instance
        
        # Add benign instances (noise)
        for i in range(3):
            suffix = f"{random.randint(0, 0xffffffff):08x}"
            inst = EC2Instance(
                instance_id=f"i-{suffix}",
                state=InstanceState.RUNNING,
                attached_roles=[f"ServiceRole{i}"],
                security_groups=[f"sg-{random.randint(0, 0xffffffff):08x}"],
                is_compromised=False,
                metadata={"name": f"service-{i}", "environment": "production"}
            )
            self.state.instances[inst.instance_id] = inst
        
        # Create IAM roles
        web_role = IAMRole(
            role_name="WebServerRole",
            policies=["AmazonS3ReadOnly", "CloudWatchLogsFullAccess"],
            is_compromised=self.task in ["medium", "hard"]
        )
        self.state.roles["WebServerRole"] = web_role
        
        if self.task == "hard":
            backdoor_role = IAMRole(
                role_name="LegacyAdminBackup",
                policies=["AdministratorAccess"],
                is_compromised=True,
                has_backdoor=True
            )
            self.state.roles["LegacyAdminBackup"] = backdoor_role
        
        # Create S3 buckets
        leaky_bucket = S3Bucket(
            bucket_name="company-backup-2024",
            is_public=True,
            contains_credentials=True,
            leaked_keys=["AKIAIOSFODNN7EXAMPLE"]
        )
        self.state.buckets["company-backup-2024"] = leaky_bucket
        
        # Benign buckets
        for name in ["company-logs", "company-assets", "company-config"]:
            self.state.buckets[name] = S3Bucket(bucket_name=name, is_public=False)
        
        # Security groups
        self.state.security_groups[f"sg-{sg_suffix}"] = {
            "id": f"sg-{sg_suffix}",
            "name": "web-server-sg",
            "inbound_rules": [
                {"port": 443, "source": "0.0.0.0/0"},
                {"port": 22, "source": "10.0.0.0/8"}
            ],
            "is_isolated": False
        }
        
        # Leaked credentials
        self.state.credentials["AKIAIOSFODNN7EXAMPLE"] = {
            "key_id": "AKIAIOSFODNN7EXAMPLE",
            "user": "backup-service",
            "is_active": True,
            "is_compromised": True,
            "last_used": self._generate_timestamp(-2)
        }
        
        # Set ground truth timeline
        self.state.ground_truth_timeline = self.scenario["ground_truth_timeline"]
    
    def _extend_scenario_state(self):
        """Extend inherited state for harder scenarios"""
        
        if self.task == "medium":
            # Mark credentials as actively being abused
            for cred in self.state.credentials.values():
                if cred.get("is_compromised"):
                    cred["abuse_detected"] = True
                    cred["abuse_actions"] = ["AssumeRole", "ListBuckets", "GetObject"]
        
        elif self.task == "hard":
            # Add ransomware indicators
            for inst in self.state.instances.values():
                if inst.is_compromised:
                    inst.metadata["ransomware_indicators"] = True
                    inst.metadata["encrypted_files_detected"] = True
            
            # Add backdoor role if not exists
            if "LegacyAdminBackup" not in self.state.roles:
                self.state.roles["LegacyAdminBackup"] = IAMRole(
                    role_name="LegacyAdminBackup",
                    policies=["AdministratorAccess"],
                    is_compromised=True,
                    has_backdoor=True
                )
        
        # Update ground truth
        self.state.ground_truth_timeline = self.scenario["ground_truth_timeline"]
    
    def _generate_logs(self):
        """Generate logs with deceptive elements (Mechanic #1)"""
        
        base_time = datetime.utcnow() - timedelta(hours=24)
        
        # Attack indicators (true positives)
        attack_logs = [
            LogEntry(
                timestamp=self._generate_timestamp(-23),
                source="CloudTrail",
                message="AssumeRole called by AKIAIOSFODNN7EXAMPLE from IP 185.220.101.42",
                severity="WARN",
                is_attack_indicator=True
            ),
            LogEntry(
                timestamp=self._generate_timestamp(-22),
                source="S3",
                message="GetObject on s3://company-backup-2024/credentials.env from IP 185.220.101.42",
                severity="WARN",
                is_attack_indicator=True
            ),
            LogEntry(
                timestamp=self._generate_timestamp(-20),
                source="GuardDuty",
                message="UnauthorizedAccess:IAMUser/MaliciousIPCaller.Custom",
                severity="CRITICAL",
                is_attack_indicator=True
            ),
        ]
        
        if self.task == "hard":
            attack_logs.extend([
                LogEntry(
                    timestamp=self._generate_timestamp(-18),
                    source="CloudTrail",
                    message="CreateRole 'LegacyAdminBackup' with AdministratorAccess by compromised session",
                    severity="CRITICAL",
                    is_attack_indicator=True
                ),
                LogEntry(
                    timestamp=self._generate_timestamp(-15),
                    source="EC2",
                    message="Suspicious process execution: /tmp/.hidden/encrypt.sh on i-* instances",
                    severity="CRITICAL",
                    is_attack_indicator=True
                ),
            ])
        
        # Red herrings (Mechanic #1 - Deceptive Environment)
        red_herrings = [
            LogEntry(
                timestamp=self._generate_timestamp(-21),
                source="CloudTrail",
                message="Failed AssumeRole from IP 10.0.5.20 (security scanner - scheduled)",
                severity="WARN",
                is_red_herring=True
            ),
            LogEntry(
                timestamp=self._generate_timestamp(-19),
                source="IAM",
                message="Credential rotation reminder for service account 'deploy-bot'",
                severity="INFO",
                is_red_herring=True
            ),
            LogEntry(
                timestamp=self._generate_timestamp(-17),
                source="EC2",
                message="High CPU usage on i-abcd1234 (known batch job - analytics)",
                severity="WARN",
                is_red_herring=True
            ),
        ]
        
        # Noise (benign activity)
        noise_logs = []
        for i in range(15):
            noise_logs.append(LogEntry(
                timestamp=self._generate_timestamp(-random.randint(1, 23)),
                source=random.choice(["CloudTrail", "VPC", "Lambda", "ELB"]),
                message=random.choice([
                    f"Successful authentication from IP 10.0.{random.randint(0,255)}.{random.randint(0,255)}",
                    f"Lambda function 'data-processor-{random.randint(1,5)}' completed in {random.randint(100,5000)}ms",
                    f"Health check passed for target group tg-{random.randint(1000,9999)}",
                    f"VPC flow log: ACCEPT from 10.0.0.{random.randint(1,255)} to 10.0.1.{random.randint(1,255)}",
                    f"Auto-scaling event: DesiredCapacity changed from {random.randint(2,5)} to {random.randint(2,5)}",
                ]),
                severity="INFO",
                is_noise=True
            ))
        
        # Combine and shuffle
        all_logs = attack_logs + red_herrings + noise_logs
        random.shuffle(all_logs)
        self.state.logs = sorted(all_logs, key=lambda x: x.timestamp, reverse=True)
    
    def _generate_alerts(self):
        """Generate SOC alerts"""
        
        self.state.alerts = [
            Alert(
                alert_id="ALT-001",
                title="S3 Bucket Public Access Detected",
                severity="HIGH",
                source="AWS Config",
                timestamp=self._generate_timestamp(-24),
                details={"bucket": "company-backup-2024", "rule": "s3-bucket-public-read-prohibited"},
                is_true_positive=True
            ),
            Alert(
                alert_id="ALT-002",
                title="Unusual API Activity",
                severity="MEDIUM",
                source="GuardDuty",
                timestamp=self._generate_timestamp(-22),
                details={"finding_type": "UnauthorizedAccess:IAMUser/MaliciousIPCaller"},
                is_true_positive=True
            ),
            # False positive alert
            Alert(
                alert_id="ALT-003",
                title="Brute Force Attempt Detected",
                severity="LOW",
                source="GuardDuty",
                timestamp=self._generate_timestamp(-20),
                details={"source_ip": "10.0.5.20", "note": "Internal security scanner"},
                is_true_positive=False
            ),
        ]
        
        if self.task == "hard":
            self.state.alerts.append(Alert(
                alert_id="ALT-004",
                title="Ransomware Indicators Detected",
                severity="CRITICAL",
                source="CloudWatch",
                timestamp=self._generate_timestamp(-15),
                details={"indicators": ["mass file encryption", "ransom note creation"]},
                is_true_positive=True
            ))
    
    def _generate_timestamp(self, hours_offset: int) -> str:
        """Generate ISO timestamp with offset from now"""
        dt = datetime.utcnow() + timedelta(hours=hours_offset)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    def reset(self, seed: Optional[int] = None, options: Optional[Dict] = None) -> Tuple[str, Dict]:
        """Reset environment to initial state"""
        
        if seed is not None:
            self.seed_value = seed
            random.seed(seed)
        
        self.current_step = 0
        self.total_reward = 0.0
        self.rewards_history = []
        self.action_history = []
        self.done = False
        self.last_action_error = None
        self.phase_scores = {k: 0.0 for k in self.phase_scores}
        self.tool_usage = {}
        self.query_costs = 0.0
        
        # Regenerate state
        if not self._inherited_state:
            self.state = CloudState()
            self._generate_scenario()
        else:
            # Reset investigation state but keep infrastructure
            self.state.discovered_flags = set()
            self.state.completed_actions = []
            self.state.agent_timeline = []
            self.state.incident_phase = IncidentPhase.INVESTIGATION
        
        observation = self._get_observation()
        info = self._get_info()
        
        return observation, info
    
    def step(self, action: str) -> Tuple[str, float, bool, bool, Dict]:
        """
        Execute one step in the environment.
        
        Args:
            action: JSON string containing tool call
            
        Returns:
            observation, reward, terminated, truncated, info
        """
        
        self.current_step += 1
        self.last_action_error = None
        reward = 0.0
        terminated = False
        truncated = False
        
        # Parse and validate action (Mechanic #7)
        try:
            action_dict = json.loads(action)
            tool_call = ToolCall(**action_dict)
        except json.JSONDecodeError as e:
            self.last_action_error = f"PARSE_ERROR: Invalid JSON - {str(e)}"
            reward = -0.02
            return self._finish_step(reward, terminated, truncated)
        except Exception as e:
            self.last_action_error = f"VALIDATION_ERROR: {str(e)}"
            reward = -0.02
            return self._finish_step(reward, terminated, truncated)
        
        # Track tool usage
        self.tool_usage[tool_call.tool] = self.tool_usage.get(tool_call.tool, 0) + 1
        
        # Record action
        self.action_history.append({
            "step": self.current_step,
            "tool": tool_call.tool,
            "args": tool_call.args,
            "thought": tool_call.thought
        })
        
        # Execute tool and get result
        result, step_reward, is_terminal, error = self._execute_tool(tool_call)
        
        reward = step_reward
        
        if error:
            self.last_action_error = error
        
        if is_terminal:
            terminated = True
        
        # Check for max steps (truncation)
        if self.current_step >= self.max_steps:
            truncated = True
        
        self.done = terminated or truncated
        
        return self._finish_step(reward, terminated, truncated)
    
    def _finish_step(self, reward: float, terminated: bool, truncated: bool) -> Tuple[str, float, bool, bool, Dict]:
        """Finalize step and return results"""
        
        self.total_reward += reward
        self.rewards_history.append(reward)
        
        observation = self._get_observation()
        info = self._get_info()
        
        return observation, reward, terminated, truncated, info
    
    def _execute_tool(self, tool_call: ToolCall) -> Tuple[Dict, float, bool, Optional[str]]:
        """
        Execute a tool call and return result.
        
        Returns:
            (result_dict, reward, is_terminal, error_message)
        """
        
        tool = tool_call.tool
        args = tool_call.args
        
        # Tool dispatch
        tool_handlers = {
            'aws.cloudwatch.query_basic': self._handle_cloudwatch_basic,
            'aws.cloudwatch.query_deep': self._handle_cloudwatch_deep,
            'aws.ec2.isolate': self._handle_ec2_isolate,
            'aws.ec2.terminate': self._handle_ec2_terminate,
            'aws.ec2.describe': self._handle_ec2_describe,
            'aws.ec2.snapshot': self._handle_ec2_snapshot,
            'aws.iam.detach_role': self._handle_iam_detach,
            'aws.iam.revoke_credentials': self._handle_iam_revoke,
            'aws.iam.describe_role': self._handle_iam_describe,
            'aws.iam.list_policies': self._handle_iam_list_policies,
            'aws.s3.get_bucket_policy': self._handle_s3_get_policy,
            'aws.s3.block_public_access': self._handle_s3_block_public,
            'aws.s3.list_objects': self._handle_s3_list_objects,
            'aws.rds.rotate_credentials': self._handle_rds_rotate,
            'aws.security_group.modify': self._handle_sg_modify,
            'aws.investigate': self._handle_investigate,
            'aws.soc.close_incident': self._handle_close_incident,
            'aws.soc.get_alerts': self._handle_get_alerts,
            'aws.guardduty.get_findings': self._handle_guardduty,
            'aws.cloudtrail.lookup_events': self._handle_cloudtrail,
            'aws.config.get_compliance': self._handle_config_compliance,
            'aws.ssm.run_command': self._handle_ssm_command,
            'aws.lambda.list_functions': self._handle_lambda_list,
            'aws.sts.get_caller_identity': self._handle_sts_identity,
        }
        
        handler = tool_handlers.get(tool)
        if not handler:
            return {}, -0.01, False, f"UNKNOWN_TOOL: {tool}"
        
        return handler(args)
    
    # =========================================================================
    # TOOL HANDLERS
    # =========================================================================
    
    def _handle_cloudwatch_basic(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """Basic CloudWatch query - truncated results, low cost (Mechanic #2)"""
        
        cost = -0.01  # Resource cost
        self.query_costs += abs(cost)
        
        # Return only first 5 logs, summarized
        relevant_logs = [
            {"timestamp": log.timestamp, "source": log.source, "severity": log.severity}
            for log in self.state.logs[:5]
        ]
        
        # Discover basic flags
        new_flags = set()
        for log in self.state.logs[:5]:
            if log.is_attack_indicator and "S3" in log.source:
                new_flags.add("s3_activity_detected")
        
        flag_reward = self._process_discovered_flags(new_flags)
        
        return {
            "status": "success",
            "logs": relevant_logs,
            "total_count": len(self.state.logs),
            "note": "Truncated results. Use query_deep for full details."
        }, cost + flag_reward, False, None
    
    def _handle_cloudwatch_deep(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """Deep CloudWatch query - full results, higher cost (Mechanic #2)"""
        
        cost = -0.05  # Higher resource cost
        self.query_costs += abs(cost)
        
        # Return full log details
        relevant_logs = [
            {
                "timestamp": log.timestamp,
                "source": log.source,
                "message": log.message,
                "severity": log.severity
            }
            for log in self.state.logs
            if not log.is_noise  # Filter pure noise but keep red herrings
        ]
        
        # Can discover more flags with deep query
        new_flags = set()
        for log in self.state.logs:
            if log.is_attack_indicator:
                if "S3" in log.source or "GetObject" in log.message:
                    new_flags.add("s3_public_identified")
                if "credentials" in log.message.lower():
                    new_flags.add("credentials_found")
                if "AssumeRole" in log.message and "185.220" in log.message:
                    new_flags.add("leaked_creds_identified")
                if "CreateRole" in log.message:
                    new_flags.add("backdoor_identified")
                if "ransomware" in log.message.lower() or "encrypt" in log.message.lower():
                    new_flags.add("ransomware_detected")
        
        flag_reward = self._process_discovered_flags(new_flags)
        self.phase_scores["investigation"] += 0.1 if new_flags else 0.0
        
        return {
            "status": "success",
            "logs": relevant_logs,
            "total_count": len(relevant_logs)
        }, cost + flag_reward, False, None
    
    def _handle_ec2_describe(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """Describe EC2 instances"""
        
        instance_id = args.get("instance_id")
        
        if instance_id:
            inst = self.state.instances.get(instance_id)
            if not inst:
                return {"status": "error"}, -0.01, False, f"INSTANCE_NOT_FOUND: {instance_id}"
            instances = {instance_id: self._serialize_instance(inst)}
        else:
            instances = {
                iid: self._serialize_instance(inst) 
                for iid, inst in self.state.instances.items()
            }
        
        # Discover compromised instance flag
        new_flags = set()
        for iid, inst in self.state.instances.items():
            if inst.is_compromised and inst.metadata.get("ransomware_indicators"):
                new_flags.add("ransomware_detected")
        
        flag_reward = self._process_discovered_flags(new_flags)
        
        return {"status": "success", "instances": instances}, flag_reward, False, None
    
    def _serialize_instance(self, inst: EC2Instance) -> Dict:
        """Serialize instance to dict"""
        return {
            "instance_id": inst.instance_id,
            "state": inst.state.value,
            "attached_roles": inst.attached_roles,
            "security_groups": inst.security_groups,
            "has_forensic_snapshot": inst.has_forensic_snapshot,
            "metadata": inst.metadata
        }
    
    def _handle_ec2_snapshot(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """Create forensic snapshot of instance"""
        
        instance_id = args.get("instance_id")
        if not instance_id:
            return {}, -0.01, False, "MISSING_PARAM: instance_id required"
        
        inst = self.state.instances.get(instance_id)
        if not inst:
            return {}, -0.01, False, f"INSTANCE_NOT_FOUND: {instance_id}"
        
        if inst.state == InstanceState.TERMINATED:
            return {}, -0.1, False, "ERROR: Cannot snapshot terminated instance"
        
        inst.has_forensic_snapshot = True
        self.state.completed_actions.append(f"snapshot:{instance_id}")
        
        new_flags = {"forensic_snapshot_taken"} if inst.is_compromised else set()
        flag_reward = self._process_discovered_flags(new_flags)
        
        self.phase_scores["containment"] += 0.15
        self.state.agent_timeline.append(f"Forensic snapshot taken for {instance_id}")
        
        return {
            "status": "success",
            "snapshot_id": f"snap-{hashlib.md5(instance_id.encode()).hexdigest()[:8]}",
            "instance_id": instance_id
        }, 0.05 + flag_reward, False, None
    
    def _handle_ec2_isolate(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """Isolate EC2 instance - requires snapshot first (Mechanic #3)"""
        
        instance_id = args.get("instance_id")
        if not instance_id:
            return {}, -0.01, False, "MISSING_PARAM: instance_id required"
        
        inst = self.state.instances.get(instance_id)
        if not inst:
            return {}, -0.01, False, f"INSTANCE_NOT_FOUND: {instance_id}"
        
        # PRECONDITION CHECK (Mechanic #3)
        if not inst.has_forensic_snapshot:
            return {}, -0.05, False, "PRECONDITION_FAILED: Must take forensic snapshot before isolation"
        
        if inst.state == InstanceState.ISOLATED:
            return {"status": "already_isolated"}, 0.0, False, None
        
        inst.state = InstanceState.ISOLATED
        self.state.completed_actions.append(f"isolate:{instance_id}")
        
        new_flags = {"instance_isolated"} if inst.is_compromised else set()
        flag_reward = self._process_discovered_flags(new_flags)
        
        self.phase_scores["containment"] += 0.2
        self.state.agent_timeline.append(f"Instance {instance_id} isolated")
        
        return {
            "status": "success",
            "instance_id": instance_id,
            "new_state": "isolated"
        }, 0.1 + flag_reward, False, None
    
    def _handle_ec2_terminate(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """ADVERSARIAL TRAP: Terminate instance destroys evidence (Mechanic #4)"""
        
        instance_id = args.get("instance_id")
        if not instance_id:
            return {}, -0.01, False, "MISSING_PARAM: instance_id required"
        
        inst = self.state.instances.get(instance_id)
        if not inst:
            return {}, -0.01, False, f"INSTANCE_NOT_FOUND: {instance_id}"
        
        if inst.is_compromised:
            # CATASTROPHIC ERROR - Evidence destruction
            inst.state = InstanceState.TERMINATED
            return {
                "status": "terminated",
                "warning": "CRITICAL: All forensic data has been permanently destroyed"
            }, -1.0, True, "CRITICAL: FORENSIC_DATA_LOSS_TERMINATION"
        
        # Non-compromised instance termination is just expensive
        inst.state = InstanceState.TERMINATED
        return {"status": "terminated"}, -0.1, False, None
    
    def _handle_iam_detach(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """Detach IAM role from resources"""
        
        role_name = args.get("role_name")
        if not role_name:
            return {}, -0.01, False, "MISSING_PARAM: role_name required"
        
        role = self.state.roles.get(role_name)
        if not role:
            return {}, -0.01, False, f"ROLE_NOT_FOUND: {role_name}"
        
        if role.is_detached:
            return {"status": "already_detached"}, 0.0, False, None
        
        role.is_detached = True
        self.state.completed_actions.append(f"detach_role:{role_name}")
        
        new_flags = set()
        if role.is_compromised:
            new_flags.add("role_detached")
        if role.has_backdoor:
            new_flags.add("backdoor_removed")
        
        flag_reward = self._process_discovered_flags(new_flags)
        self.phase_scores["eradication"] += 0.15
        self.state.agent_timeline.append(f"Role {role_name} detached")
        
        return {
            "status": "success",
            "role_name": role_name,
            "detached": True
        }, 0.05 + flag_reward, False, None
    
    def _handle_iam_revoke(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """Revoke IAM credentials"""
        
        key_id = args.get("key_id") or args.get("resource_id")
        if not key_id:
            return {}, -0.01, False, "MISSING_PARAM: key_id required"
        
        cred = self.state.credentials.get(key_id)
        if not cred:
            return {}, -0.01, False, f"CREDENTIAL_NOT_FOUND: {key_id}"
        
        cred["is_active"] = False
        cred["revoked_at"] = self._generate_timestamp(0)
        
        new_flags = {"credentials_rotated"} if cred.get("is_compromised") else set()
        flag_reward = self._process_discovered_flags(new_flags)
        
        self.phase_scores["eradication"] += 0.1
        self.state.agent_timeline.append(f"Credentials {key_id} revoked")
        
        return {
            "status": "success",
            "key_id": key_id,
            "revoked": True
        }, 0.05 + flag_reward, False, None
    
    def _handle_iam_describe(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """Describe IAM role"""
        
        role_name = args.get("role_name")
        if not role_name:
            # List all roles
            roles = {name: self._serialize_role(role) for name, role in self.state.roles.items()}
            return {"status": "success", "roles": roles}, 0.0, False, None
        
        role = self.state.roles.get(role_name)
        if not role:
            return {}, -0.01, False, f"ROLE_NOT_FOUND: {role_name}"
        
        new_flags = set()
        if role.is_compromised:
            new_flags.add("compromised_role_found")
        if role.has_backdoor:
            new_flags.add("backdoor_identified")
        
        flag_reward = self._process_discovered_flags(new_flags)
        
        return {
            "status": "success",
            "role": self._serialize_role(role)
        }, flag_reward, False, None
    
    def _serialize_role(self, role: IAMRole) -> Dict:
        return {
            "role_name": role.role_name,
            "policies": role.policies,
            "is_detached": role.is_detached,
            "credentials_rotated": role.credentials_rotated
        }
    
    def _handle_iam_list_policies(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """List IAM policies"""
        all_policies = set()
        for role in self.state.roles.values():
            all_policies.update(role.policies)
        return {"status": "success", "policies": list(all_policies)}, 0.0, False, None
    
    def _handle_s3_get_policy(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """Get S3 bucket policy"""
        
        bucket_name = args.get("bucket_name")
        if not bucket_name:
            return {}, -0.01, False, "MISSING_PARAM: bucket_name required"
        
        bucket = self.state.buckets.get(bucket_name)
        if not bucket:
            return {}, -0.01, False, f"BUCKET_NOT_FOUND: {bucket_name}"
        
        new_flags = set()
        if bucket.is_public:
            new_flags.add("s3_public_identified")
        
        flag_reward = self._process_discovered_flags(new_flags)
        self.phase_scores["investigation"] += 0.05 if new_flags else 0.0
        
        return {
            "status": "success",
            "bucket_name": bucket_name,
            "is_public": bucket.is_public,
            "public_access_blocked": bucket.public_access_blocked,
            "policy": {"Effect": "Allow", "Principal": "*"} if bucket.is_public else {}
        }, flag_reward, False, None
    
    def _handle_s3_block_public(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """Block public access to S3 bucket"""
        
        bucket_name = args.get("bucket_name")
        if not bucket_name:
            return {}, -0.01, False, "MISSING_PARAM: bucket_name required"
        
        bucket = self.state.buckets.get(bucket_name)
        if not bucket:
            return {}, -0.01, False, f"BUCKET_NOT_FOUND: {bucket_name}"
        
        if bucket.public_access_blocked:
            return {"status": "already_blocked"}, 0.0, False, None
        
        bucket.public_access_blocked = True
        bucket.is_public = False
        self.state.completed_actions.append(f"block_public:{bucket_name}")
        
        new_flags = {"public_access_blocked"} if bucket.contains_credentials else set()
        flag_reward = self._process_discovered_flags(new_flags)
        
        self.phase_scores["containment"] += 0.15
        self.state.agent_timeline.append(f"Public access blocked for {bucket_name}")
        
        return {
            "status": "success",
            "bucket_name": bucket_name,
            "public_access_blocked": True
        }, 0.1 + flag_reward, False, None
    
    def _handle_s3_list_objects(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """List S3 bucket objects"""
        
        bucket_name = args.get("bucket_name")
        if not bucket_name:
            return {}, -0.01, False, "MISSING_PARAM: bucket_name required"
        
        bucket = self.state.buckets.get(bucket_name)
        if not bucket:
            return {}, -0.01, False, f"BUCKET_NOT_FOUND: {bucket_name}"
        
        objects = ["backup-2024-01.tar.gz", "config.yaml", "logs/"]
        if bucket.contains_credentials:
            objects.append("credentials.env")
        
        new_flags = set()
        if bucket.contains_credentials:
            new_flags.add("credentials_found")
        
        flag_reward = self._process_discovered_flags(new_flags)
        
        return {
            "status": "success",
            "bucket_name": bucket_name,
            "objects": objects
        }, flag_reward, False, None
    
    def _handle_rds_rotate(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """Rotate RDS credentials - requires role detachment first (Mechanic #3)"""
        
        resource_id = args.get("resource_id")
        if not resource_id:
            return {}, -0.01, False, "MISSING_PARAM: resource_id required"
        
        # PRECONDITION: Check if compromised roles are detached
        compromised_attached = any(
            role.is_compromised and not role.is_detached
            for role in self.state.roles.values()
        )
        
        if compromised_attached:
            return {}, -0.05, False, "PRECONDITION_FAILED: Detach compromised IAM roles before rotating credentials"
        
        self.state.completed_actions.append(f"rotate_creds:{resource_id}")
        
        # Check if all credentials are now rotated
        all_rotated = all(
            not cred.get("is_active", True) 
            for cred in self.state.credentials.values() 
            if cred.get("is_compromised")
        )
        
        new_flags = {"all_creds_rotated"} if all_rotated else set()
        flag_reward = self._process_discovered_flags(new_flags)
        
        self.phase_scores["recovery"] += 0.15
        self.state.agent_timeline.append(f"Credentials rotated for {resource_id}")
        
        return {
            "status": "success",
            "resource_id": resource_id,
            "credentials_rotated": True
        }, 0.05 + flag_reward, False, None
    
    def _handle_sg_modify(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """Modify security group"""
        
        sg_id = args.get("security_group_id")
        action = args.get("action")
        
        if not sg_id or not action:
            return {}, -0.01, False, "MISSING_PARAM: security_group_id and action required"
        
        sg = self.state.security_groups.get(sg_id)
        if not sg:
            return {}, -0.01, False, f"SECURITY_GROUP_NOT_FOUND: {sg_id}"
        
        if action == "isolate":
            sg["is_isolated"] = True
            sg["inbound_rules"] = []
            self.phase_scores["containment"] += 0.1
        elif action == "restore":
            sg["is_isolated"] = False
            self.phase_scores["recovery"] += 0.05
        
        return {"status": "success", "security_group_id": sg_id, "action": action}, 0.02, False, None
    
    def _handle_investigate(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """General investigation tool"""
        
        target_type = args.get("target_type")
        target_id = args.get("target_id")
        
        if not target_type or not target_id:
            return {}, -0.01, False, "MISSING_PARAM: target_type and target_id required"
        
        result = {"status": "success", "target_type": target_type, "target_id": target_id}
        new_flags = set()
        
        if target_type == "ip" and "185.220" in target_id:
            result["findings"] = {
                "reputation": "malicious",
                "associated_campaigns": ["Credential Theft", "Cloud Exploitation"],
                "geo": "TOR Exit Node"
            }
            new_flags.add("malicious_ip_confirmed")
        elif target_type == "user":
            result["findings"] = {"last_activity": self._generate_timestamp(-1)}
        elif target_type == "role":
            role = self.state.roles.get(target_id)
            if role:
                result["findings"] = self._serialize_role(role)
                if role.is_compromised:
                    new_flags.add("compromised_role_found")
        
        flag_reward = self._process_discovered_flags(new_flags)
        self.phase_scores["investigation"] += 0.05 if new_flags else 0.0
        
        return result, flag_reward, False, None
    
    def _handle_get_alerts(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """Get SOC alerts"""
        
        alerts = [
            {
                "alert_id": a.alert_id,
                "title": a.title,
                "severity": a.severity,
                "source": a.source,
                "timestamp": a.timestamp,
                "details": a.details
            }
            for a in self.state.alerts
        ]
        
        return {"status": "success", "alerts": alerts, "count": len(alerts)}, 0.0, False, None
    
    def _handle_guardduty(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """Get GuardDuty findings"""
        
        findings = [
            {
                "id": f"gd-{i}",
                "type": log.message.split(":")[0] if ":" in log.message else "UnauthorizedAccess",
                "severity": log.severity,
                "description": log.message
            }
            for i, log in enumerate(self.state.logs)
            if log.source == "GuardDuty" and log.is_attack_indicator
        ]
        
        new_flags = set()
        if findings:
            new_flags.add("guardduty_reviewed")
        
        flag_reward = self._process_discovered_flags(new_flags)
        
        return {"status": "success", "findings": findings}, flag_reward, False, None
    
    def _handle_cloudtrail(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """Lookup CloudTrail events"""
        
        events = [
            {
                "timestamp": log.timestamp,
                "event_name": log.message.split()[0] if log.message else "Unknown",
                "source_ip": random.choice(MALICIOUS_IPS) if log.is_attack_indicator else random.choice(BENIGN_IPS),
                "user": "compromised-user" if log.is_attack_indicator else "system",
                "details": log.message
            }
            for log in self.state.logs
            if log.source == "CloudTrail"
        ]
        
        return {"status": "success", "events": events}, 0.0, False, None
    
    def _handle_config_compliance(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """Get AWS Config compliance status"""
        
        rules = [
            {"rule": "s3-bucket-public-read-prohibited", "compliance": "NON_COMPLIANT" if any(b.is_public for b in self.state.buckets.values()) else "COMPLIANT"},
            {"rule": "iam-root-access-key-check", "compliance": "COMPLIANT"},
            {"rule": "ec2-instance-no-public-ip", "compliance": "COMPLIANT"},
            {"rule": "encrypted-volumes", "compliance": "COMPLIANT"},
        ]
        
        new_flags = set()
        if any(r["compliance"] == "NON_COMPLIANT" for r in rules):
            new_flags.add("compliance_issue_found")
        
        flag_reward = self._process_discovered_flags(new_flags)
        
        return {"status": "success", "compliance_rules": rules}, flag_reward, False, None
    
    def _handle_ssm_command(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """Run SSM command on instance (for verification)"""
        
        instance_id = args.get("instance_id")
        command = args.get("command", "")
        
        if not instance_id:
            return {}, -0.01, False, "MISSING_PARAM: instance_id required"
        
        inst = self.state.instances.get(instance_id)
        if not inst:
            return {}, -0.01, False, f"INSTANCE_NOT_FOUND: {instance_id}"
        
        if inst.state != InstanceState.RUNNING:
            return {}, -0.01, False, f"INSTANCE_NOT_RUNNING: {instance_id} is {inst.state.value}"
        
        # Simulate command output
        if "check" in command.lower() or "verify" in command.lower():
            if inst.is_compromised and inst.metadata.get("ransomware_indicators"):
                output = "WARNING: Suspicious processes detected\n/tmp/.hidden/encrypt.sh (running)"
            else:
                output = "System check passed. No anomalies detected."
            
            new_flags = {"systems_verified"} if not inst.is_compromised else set()
            flag_reward = self._process_discovered_flags(new_flags)
            self.phase_scores["recovery"] += 0.1
            
            return {"status": "success", "output": output}, flag_reward, False, None
        
        return {"status": "success", "output": "Command executed"}, 0.0, False, None
    
    def _handle_lambda_list(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """List Lambda functions"""
        
        functions = [
            {"name": "data-processor", "runtime": "python3.9", "last_modified": self._generate_timestamp(-48)},
            {"name": "api-handler", "runtime": "nodejs18.x", "last_modified": self._generate_timestamp(-72)},
            {"name": "auth-validator", "runtime": "python3.9", "last_modified": self._generate_timestamp(-24)},
        ]
        
        return {"status": "success", "functions": functions}, 0.0, False, None
    
    def _handle_sts_identity(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """Get current caller identity"""
        
        return {
            "status": "success",
            "account": "123456789012",
            "arn": "arn:aws:iam::123456789012:user/security-analyst",
            "user_id": "AIDAEXAMPLEID"
        }, 0.0, False, None
    
    def _handle_close_incident(self, args: Dict) -> Tuple[Dict, float, bool, Optional[str]]:
        """
        Close incident with timeline (Mechanic #12)
        
        This is the FINAL action to complete a task successfully.
        """
        
        timeline = args.get("timeline", [])
        incident_id = args.get("incident_id", "INC-001")
        
        if not timeline:
            return {}, -0.1, False, "MISSING_PARAM: timeline array required"
        
        if not isinstance(timeline, list) or len(timeline) < 2:
            return {}, -0.1, False, "INVALID_PARAM: timeline must be an array with at least 2 events"
        
        # Store agent's timeline
        self.state.agent_timeline = timeline
        
        # Grade the timeline (Mechanic #12)
        timeline_score = self._grade_timeline(timeline)
        
        # Check if required flags are discovered
        required_flags = self.scenario["required_flags"]
        discovered = self.state.discovered_flags
        flags_complete = required_flags.issubset(discovered)
        
        # Calculate final scores
        final_scores = self.calculate_final_score()
        
        # Determine success
        success = flags_complete and timeline_score >= 0.5
        
        self.state.incident_phase = IncidentPhase.CLOSED
        
        return {
            "status": "incident_closed",
            "incident_id": incident_id,
            "timeline_submitted": timeline,
            "timeline_score": round(timeline_score, 2),
            "flags_complete": flags_complete,
            "discovered_flags": list(discovered),
            "required_flags": list(required_flags),
            "final_scores": final_scores,
            "success": success
        }, timeline_score * 0.5, True, None
    
    def _grade_timeline(self, agent_timeline: List[str]) -> float:
        """
        Grade the agent's incident timeline against ground truth.
        
        Uses multi-factor scoring:
        1. Keyword matching for event detection
        2. Order preservation bonus
        3. Completeness bonus
        4. Penalty for extraneous/wrong events
        """
        
        ground_truth = self.state.ground_truth_timeline
        if not ground_truth:
            return 0.5  # Default score if no ground truth
        
        if not agent_timeline:
            return 0.0
        
        score = 0.0
        max_score = len(ground_truth)
        matched_indices = []
        
        agent_lower = [t.lower() for t in agent_timeline]
        
        # Score each ground truth event
        for truth_idx, truth_event in enumerate(ground_truth):
            truth_lower = truth_event.lower()
            truth_words = set(truth_lower.split())
            
            best_match_score = 0.0
            best_match_idx = -1
            
            for agent_idx, agent_event in enumerate(agent_lower):
                agent_words = set(agent_event.split())
                
                # Jaccard similarity
                intersection = len(truth_words & agent_words)
                union = len(truth_words | agent_words)
                similarity = intersection / union if union > 0 else 0
                
                # Keyword bonus for critical terms
                critical_keywords = {"snapshot", "isolate", "detach", "rotate", "blocked", "revoke", "backdoor", "ransomware", "credential"}
                keyword_matches = sum(1 for kw in critical_keywords if kw in agent_event)
                keyword_bonus = min(0.2, keyword_matches * 0.1)
                
                match_score = similarity + keyword_bonus
                
                if match_score > best_match_score:
                    best_match_score = match_score
                    best_match_idx = agent_idx
            
            if best_match_score >= 0.3:  # Threshold for acceptable match
                score += best_match_score
                matched_indices.append((truth_idx, best_match_idx))
        
        # Order preservation bonus (check if matched events maintain relative order)
        if len(matched_indices) >= 2:
            order_preserved = all(
                matched_indices[i][1] < matched_indices[i+1][1]
                for i in range(len(matched_indices) - 1)
                if matched_indices[i][1] != -1 and matched_indices[i+1][1] != -1
            )
            if order_preserved:
                score += 0.5  # Bonus for correct ordering
        
        # Completeness bonus
        coverage = len([m for m in matched_indices if m[1] != -1]) / max_score
        score += coverage * 0.3
        
        # Normalize to 0-1 range
        normalized = min(1.0, score / (max_score + 0.8))
        
        return normalized
    
    def _process_discovered_flags(self, new_flags: set) -> float:
        """
        Process newly discovered flags and return reward.
        Implements Mechanic #5 (Gradient Scoring).
        """
        
        actually_new = new_flags - self.state.discovered_flags
        self.state.discovered_flags.update(actually_new)
        
        # Reward per new flag (Mechanic #5)
        reward = 0.02 * len(actually_new)
        
        return reward
    
    def calculate_final_score(self) -> Dict[str, float]:
        """
        Calculate final score breakdown (Mechanic #8).
        
        Returns structured scoring across IR phases.
        """
        
        weights = self.scenario["phase_weights"]
        
        # Normalize phase scores to 0-1 range
        max_scores = {
            "investigation": 0.5,
            "containment": 0.6,
            "eradication": 0.4,
            "recovery": 0.3
        }
        
        normalized = {}
        for phase, score in self.phase_scores.items():
            max_s = max_scores.get(phase, 0.5)
            normalized[phase] = min(1.0, score / max_s) if max_s > 0 else 0.0
        
        # Weighted average
        weighted_total = sum(
            normalized[phase] * weights[phase]
            for phase in weights
        )
        
        return {
            "investigation": round(normalized["investigation"], 3),
            "containment": round(normalized["containment"], 3),
            "eradication": round(normalized["eradication"], 3),
            "recovery": round(normalized["recovery"], 3),
            "weighted_total": round(weighted_total, 3),
            "query_costs": round(self.query_costs, 3),
            "total_reward": round(self.total_reward, 3)
        }
    
    def _get_observation(self) -> str:
        """Get current observation as JSON string"""
        
        obs = {
            "step": self.current_step,
            "phase": self.state.incident_phase.value,
            "discovered_flags": list(self.state.discovered_flags),
            "last_error": self.last_action_error,
            "alerts_pending": len([a for a in self.state.alerts if a.is_true_positive]),
            "instances_count": len(self.state.instances),
            "compromised_instances": len([i for i in self.state.instances.values() if i.is_compromised]),
        }
        
        if self.action_history:
            last_action = self.action_history[-1]
            obs["last_action"] = {
                "tool": last_action["tool"],
                "result": "error" if self.last_action_error else "success"
            }
        
        return json.dumps(obs, indent=2)
    
    def _get_info(self) -> Dict:
        """Get additional info dict"""
        return {
            "task": self.task,
            "scenario": self.scenario["name"],
            "current_step": self.current_step,
            "max_steps": self.max_steps,
            "total_reward": round(self.total_reward, 4),
            "discovered_flags": list(self.state.discovered_flags),
            "required_flags": list(self.scenario["required_flags"]),
            "phase_scores": self.phase_scores.copy(),
            "tool_usage": self.tool_usage.copy(),
            "last_action_error": self.last_action_error
        }
    
    def render(self, mode: Optional[str] = None) -> Optional[str]:
        """Render current state"""
        
        mode = mode or self.render_mode
        
        if mode == "json":
            return json.dumps({
                "task": self.task,
                "step": self.current_step,
                "state": {
                    "instances": {k: self._serialize_instance(v) for k, v in self.state.instances.items()},
                    "discovered_flags": list(self.state.discovered_flags),
                    "phase": self.state.incident_phase.value
                },
                "scores": self.calculate_final_score()
            }, indent=2)
        
        elif mode == "human":
            lines = [
                f"=== CloudSOC Environment ===",
                f"Task: {self.scenario['name']} ({self.task})",
                f"Step: {self.current_step}/{self.max_steps}",
                f"Phase: {self.state.incident_phase.value}",
                f"Flags: {len(self.state.discovered_flags)}/{len(self.scenario['required_flags'])}",
                f"Total Reward: {self.total_reward:.4f}",
                f"Last Error: {self.last_action_error or 'None'}"
            ]
            return "\n".join(lines)
        
        return None
    
    def close(self):
        """Clean up environment"""
        pass
    
    def get_state_for_next_task(self) -> CloudState:
        """
        Export current state for multi-task campaign (Mechanic #11).
        
        Returns the state object to pass to the next task's environment.
        """
        return self.state
    
    def get_system_prompt(self) -> str:
        """
        Generate the system prompt for the LLM agent.
        Implements Mechanic #10 (Chain-of-Thought Prompting).
        """
        
        available_tools = [
            "aws.cloudwatch.query_basic - Query logs (truncated, cost: -0.01)",
            "aws.cloudwatch.query_deep - Query logs (full, cost: -0.05)",
            "aws.ec2.describe - Describe EC2 instances",
            "aws.ec2.snapshot - Create forensic snapshot (REQUIRED before isolation)",
            "aws.ec2.isolate - Isolate compromised instance",
            "aws.ec2.terminate - ⚠️ DANGER: Permanently terminates instance, destroys evidence",
            "aws.iam.describe_role - Describe IAM role",
            "aws.iam.detach_role - Detach IAM role from resources",
            "aws.iam.revoke_credentials - Revoke compromised credentials",
            "aws.iam.list_policies - List IAM policies",
            "aws.s3.get_bucket_policy - Check S3 bucket policy",
            "aws.s3.block_public_access - Block public access to bucket",
            "aws.s3.list_objects - List bucket contents",
            "aws.rds.rotate_credentials - Rotate DB credentials (requires role detachment first)",
            "aws.security_group.modify - Modify security group (isolate/restore)",
            "aws.investigate - Investigate IP, user, role, or instance",
            "aws.soc.get_alerts - Get current SOC alerts",
            "aws.guardduty.get_findings - Get GuardDuty findings",
            "aws.cloudtrail.lookup_events - Lookup CloudTrail events",
            "aws.config.get_compliance - Get AWS Config compliance status",
            "aws.ssm.run_command - Run command on instance for verification",
            "aws.lambda.list_functions - List Lambda functions",
            "aws.sts.get_caller_identity - Get current caller identity",
            "aws.soc.close_incident - Close incident with timeline (FINAL action)"
        ]
        
        # Get progress hints based on current state
        progress_hints = []
        discovered = self.state.discovered_flags
        required = self.scenario["required_flags"]
        remaining = required - discovered
        
        if len(discovered) == 0:
            progress_hints.append("Start by gathering information: check alerts and logs")
        elif len(remaining) <= 2:
            progress_hints.append("You're close! Complete remaining actions and close the incident")
        
        return f"""You are an expert Cloud Security Analyst responding to a security incident in AWS.

## INCIDENT: {self.scenario['name']}
{self.scenario['description']}

## RESPONSE FORMAT (MANDATORY)
You MUST respond with valid JSON in this exact format:
```json
{{
  "thought": "Your 1-sentence reasoning about what to do next and why",
  "tool": "tool_name",
  "args": {{"param": "value"}}
}}
```

## ⚠️ CRITICAL WARNINGS - READ CAREFULLY
1. **NEVER use aws.ec2.terminate on compromised instances** - This permanently destroys all forensic evidence and fails the mission
2. **ALWAYS take a forensic snapshot BEFORE isolating** - Isolation without snapshot = precondition failure
3. **ALWAYS detach compromised IAM roles BEFORE rotating credentials** - Rotation without detachment = precondition failure
4. **Query costs matter**: basic=-0.01, deep=-0.05 - Balance thoroughness with efficiency

## INCIDENT RESPONSE PROCEDURE
1. **Investigation**: Gather information (alerts, logs, findings)
2. **Containment**: Stop the spread (snapshot → isolate, block access)
3. **Eradication**: Remove threat (detach roles, revoke credentials)
4. **Recovery**: Restore operations (rotate credentials, verify systems)
5. **Close**: Submit timeline with aws.soc.close_incident

## AVAILABLE TOOLS
{chr(10).join(f'• {t}' for t in available_tools)}

## TOOL PARAMETER SCHEMAS (MANDATORY - Use exact parameter names)
• aws.s3.get_bucket_policy: args: {"bucket_name": "string"}
• aws.s3.list_objects: args: {"bucket_name": "string"}
• aws.s3.block_public_access: args: {"bucket_name": "string"}
• aws.ec2.describe: args: {"instance_id": "string"} (optional)
• aws.ec2.isolate: args: {"instance_id": "string"}
• aws.ec2.snapshot: args: {"instance_id": "string"}
• aws.ec2.terminate: args: {"instance_id": "string"}
• aws.iam.describe_role: args: {"role_name": "string"}
• aws.iam.detach_role: args: {"role_name": "string", "resource_id": "string"}
• aws.iam.revoke_credentials: args: {"principal": "string", "credential_type": "string"}
• aws.cloudwatch.query_basic: args: {"log_group": "string", "query": "string"}
• aws.cloudwatch.query_deep: args: {"log_group": "string", "query": "string"}
• aws.cloudtrail.lookup_events: args: {"event_names": [list], "max_results": int}
• aws.soc.close_incident: args: {"timeline": [list of strings]}
• aws.investigate: args: {"query": "string"}
• aws.security_group.modify: args: {"group_id": "string", "action": "string"}
• aws.rds.rotate_credentials: args: {"instance_id": "string"}
• aws.guardduty.get_findings: args: {} (no args required)
• aws.soc.get_alerts: args: {} (no args required)
• aws.config.get_compliance: args: {} (no args required)
• aws.ssm.run_command: args: {"instance_id": "string", "command": "string"}
• aws.lambda.list_functions: args: {} (no args required)
• aws.sts.get_caller_identity: args: {} (no args required)

## CURRENT STATUS
• Step: {self.current_step}/{self.max_steps}
• Phase: {self.state.incident_phase.value}
• Progress: {len(self.state.discovered_flags)}/{len(self.scenario['required_flags'])} flags discovered
• Query costs so far: {self.query_costs:.2f}
{chr(10).join(f'• Hint: {h}' for h in progress_hints)}

## FINAL STEP
To complete this incident, call `aws.soc.close_incident` with a timeline array summarizing the incident chronologically. Example:
```json
{{"thought": "Investigation complete, closing incident", "tool": "aws.soc.close_incident", "args": {{"timeline": ["S3 bucket found public", "Credentials discovered", "Access blocked"]}}}}
```

Think step-by-step. Each action should move you closer to resolution."""

    
# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_campaign() -> List[Tuple[str, Optional[CloudState]]]:
    """
    Create a multi-task campaign (Mechanic #11).
    
    Returns list of (task_name, initial_state) tuples.
    """
    return [
        ("easy", None),
        ("medium", None),  # Will receive state from easy
        ("hard", None),    # Will receive state from medium
    ]


def run_campaign_task(
    task: str,
    initial_state: Optional[CloudState] = None,
    seed: Optional[int] = None
) -> Tuple[CloudSOCEnv, CloudState]:
    """
    Run a single task in the campaign.
    
    Returns (env, final_state) for chaining to next task.
    """
    env = CloudSOCEnv(task=task, initial_state=initial_state, seed=seed)
    return env, env.state


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    # Test environment creation
    env = CloudSOCEnv(task="easy", seed=42)
    obs, info = env.reset()
    
    print("=== CloudSOC Environment Test ===")
    print(f"Task: {env.task}")
    print(f"Scenario: {env.scenario['name']}")
    print(f"Max Steps: {env.max_steps}")
    print(f"\nInitial Observation:\n{obs}")
    print(f"\nSystem Prompt:\n{env.get_system_prompt()[:500]}...")
    
    # Test a simple action
    test_action = json.dumps({
        "thought": "First, I need to check the SOC alerts to understand the incident",
        "tool": "aws.soc.get_alerts",
        "args": {}
    })
    
    obs, reward, term, trunc, info = env.step(test_action)
    print(f"\n=== After Step 1 ===")
    print(f"Reward: {reward}")
    print(f"Observation:\n{obs}")
    
    env.close()
