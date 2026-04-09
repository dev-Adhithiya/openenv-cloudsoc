"""
OpenEnv-CloudSOC Environment Package
====================================
Contains task graders for the CloudSOC benchmark.
"""

from .graders import (
    grade_easy,
    grade_medium,
    grade_hard,
)

__all__ = [
    "grade_easy",
    "grade_medium",
    "grade_hard",
]
