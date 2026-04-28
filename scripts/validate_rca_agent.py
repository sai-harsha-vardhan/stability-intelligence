#!/usr/bin/env python3
"""Quick validation of RCA Agent implementation."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def validate_imports():
    """Validate all necessary imports work."""
    print("Validating imports...")
    
    try:
        from agents.rca_agent import RCAAgent
        print("✓ RCAAgent import successful")
    except ImportError as e:
        print(f"✗ Failed to import RCAAgent: {e}")
        return False
    
    try:
        from agents.base import BaseAgent
        print("✓ BaseAgent import successful")
    except ImportError as e:
        print(f"✗ Failed to import BaseAgent: {e}")
        return False
    
    try:
        from scheduler.runner import SchedulerRunner
        print("✓ SchedulerRunner import successful")
    except ImportError as e:
        print(f"✗ Failed to import SchedulerRunner: {e}")
        return False
    
    return True


def validate_agent_structure():
    """Validate RCAAgent class structure."""
    print("\nValidating RCAAgent structure...")
    
    from agents.rca_agent import RCAAgent
    
    agent = RCAAgent()
    
    # Check required methods
    required_methods = [
        'run',
        'analyze_incident',
        'find_similar_incidents',
        'detect_patterns',
    ]
    
    for method in required_methods:
        if hasattr(agent, method):
            print(f"✓ Method '{method}' exists")
        else:
            print(f"✗ Method '{method}' missing")
            return False
    
    # Check inheritance
    if hasattr(agent, 'call_claude'):
        print("✓ Inherits from BaseAgent (has call_claude method)")
    else:
        print("✗ Missing BaseAgent inheritance")
        return False
    
    if hasattr(agent, 'query_graph'):
        print("✓ Has graph query capability")
    else:
        print("✗ Missing graph query capability")
        return False
    
    return True


def validate_scheduler_integration():
    """Validate RCA agent is integrated into scheduler."""
    print("\nValidating scheduler integration...")
    
    from scheduler.runner import SchedulerRunner
    
    runner = SchedulerRunner()
    
    # Check if run_rca_agent method exists
    if hasattr(runner, 'run_rca_agent'):
        print("✓ Scheduler has 'run_rca_agent' method")
    else:
        print("✗ Scheduler missing 'run_rca_agent' method")
        return False
    
    # Check if method is callable
    if callable(runner.run_rca_agent):
        print("✓ 'run_rca_agent' is callable")
    else:
        print("✗ 'run_rca_agent' is not callable")
        return False
    
    return True


def main():
    """Run all validations."""
    print("=" * 60)
    print("RCA AGENT VALIDATION")
    print("=" * 60)
    
    validations = [
        ("Import Validation", validate_imports),
        ("Agent Structure Validation", validate_agent_structure),
        ("Scheduler Integration Validation", validate_scheduler_integration),
    ]
    
    results = []
    
    for name, validation_func in validations:
        try:
            result = validation_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} failed with error: {e}")
            results.append((name, False))
    
    # Print summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n🎉 All validations passed!")
        print("\nNext steps:")
        print("1. Run tests: python tests/test_rca_agent.py")
        print("2. Start system: docker-compose up -d")
        print("3. Monitor agent: docker-compose logs -f agents")
        return 0
    else:
        print("\n⚠️  Some validations failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
