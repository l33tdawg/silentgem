#!/usr/bin/env python3
"""
Test runner for context-aware follow-up improvements

This script runs the unit tests to verify that follow-up questions
are properly handled with conversation context.

Usage:
    python run_context_tests.py              # Run all tests
    python run_context_tests.py -v           # Verbose output
    python run_context_tests.py -k followup  # Run specific test pattern
"""

import sys
import subprocess
from pathlib import Path

def run_tests():
    """Run the context-aware follow-up tests"""
    
    # Ensure we're in the project root
    project_root = Path(__file__).parent
    test_file = project_root / "silentgem" / "tests" / "test_context_aware_followup.py"
    
    if not test_file.exists():
        print(f"❌ Test file not found: {test_file}")
        return 1
    
    print("🧪 Running Context-Aware Follow-up Tests")
    print("=" * 60)
    
    # Build pytest command
    cmd = [
        sys.executable, "-m", "pytest",
        str(test_file),
        "-v",  # Verbose
        "--tb=short",  # Short traceback format
        "--color=yes",  # Colored output
    ]
    
    # Add any additional arguments from command line
    if len(sys.argv) > 1:
        cmd.extend(sys.argv[1:])
    
    # Run the tests
    try:
        result = subprocess.run(cmd, cwd=str(project_root))
        return result.returncode
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
        return 130
    except Exception as e:
        print(f"\n❌ Error running tests: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(run_tests())

