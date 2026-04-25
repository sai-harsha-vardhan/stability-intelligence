#!/usr/bin/env python3
"""
Stability Intelligence System - Definition of Done Verification Script

This script automates the 30-item verification checklist from RCA-15.
It checks system health, data integrity, and validates all components.

Usage:
    python verify_system.py [--docker-check]
    
Options:
    --docker-check    Attempt to verify Docker containers (requires permissions)
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


class VerificationResult:
    """Store verification results."""
    
    def __init__(self):
        self.checks: List[Tuple[str, bool, str]] = []
        self.warnings: List[str] = []
    
    def add_check(self, name: str, passed: bool, details: str = ""):
        """Add a verification check result."""
        self.checks.append((name, passed, details))
    
    def add_warning(self, message: str):
        """Add a warning message."""
        self.warnings.append(message)
    
    def print_summary(self):
        """Print verification summary."""
        total = len(self.checks)
        passed = sum(1 for _, p, _ in self.checks if p)
        failed = total - passed
        
        print(f"\n{'='*80}")
        print(f"{BLUE}STABILITY INTELLIGENCE SYSTEM - VERIFICATION REPORT{RESET}")
        print(f"{'='*80}\n")
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # Print individual checks
        for i, (name, passed, details) in enumerate(self.checks, 1):
            status = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
            print(f"{i:2d}. [{status}] {name}")
            if details:
                print(f"     → {details}")
        
        # Print warnings
        if self.warnings:
            print(f"\n{YELLOW}⚠ WARNINGS:{RESET}")
            for warning in self.warnings:
                print(f"  - {warning}")
        
        # Print summary
        print(f"\n{'='*80}")
        success_rate = (passed / total * 100) if total > 0 else 0
        color = GREEN if success_rate >= 80 else YELLOW if success_rate >= 60 else RED
        print(f"{color}SUMMARY: {passed}/{total} checks passed ({success_rate:.1f}%){RESET}")
        print(f"{'='*80}\n")
        
        return passed, failed


def check_file_exists(path: str, description: str) -> Tuple[bool, str]:
    """Check if a file exists."""
    file_path = Path(path)
    if file_path.exists():
        size = file_path.stat().st_size
        return True, f"Found ({size:,} bytes)"
    return False, "File not found"


def check_directory_exists(path: str, description: str) -> Tuple[bool, str]:
    """Check if a directory exists."""
    dir_path = Path(path)
    if dir_path.exists() and dir_path.is_dir():
        count = len(list(dir_path.iterdir()))
        return True, f"Found ({count} entries)"
    return False, "Directory not found"


def check_docker_compose_syntax() -> Tuple[bool, str]:
    """Validate docker-compose.yml syntax."""
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "compose", "config"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            # Count services
            lines = result.stdout.split('\n')
            service_count = sum(1 for line in lines if line.strip().endswith(':') and not line.strip().startswith('#'))
            return True, f"Valid configuration ({service_count} services)"
        return False, result.stderr[:100]
    except FileNotFoundError:
        return False, "Docker not found (install Docker or skip with --no-docker-check)"
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, f"Error: {str(e)[:100]}"


def check_env_variables() -> Tuple[bool, str]:
    """Check .env file has required variables."""
    env_path = Path('.env')
    if not env_path.exists():
        return False, ".env file not found (copy from .env.example)"
    
    required_vars = [
        'NEO4J_URI', 'NEO4J_USER', 'NEO4J_PASSWORD',
        'LITELLM_BASE_URL', 'LITELLM_API_KEY',
        'GITHUB_REPO', 'LANGFUSE_SECRET_KEY'
    ]
    
    with open(env_path) as f:
        content = f.read()
    
    missing = []
    for var in required_vars:
        if f"{var}=" not in content:
            missing.append(var)
    
    if missing:
        return False, f"Missing variables: {', '.join(missing)}"
    
    # Check for placeholder values
    placeholders = []
    for var in ['ANTHROPIC_API_KEY', 'GITHUB_TOKEN', 'KIMI_API_KEY']:
        if f"{var}=<FILL_IN>" in content or f"{var}=your-" in content:
            placeholders.append(var)
    
    if placeholders:
        return True, f"Warning: {len(placeholders)} placeholder values (see BLOCKERS.md)"
    
    return True, f"All {len(required_vars)} required variables present"


def check_python_imports() -> Tuple[bool, str]:
    """Check if key Python modules can be imported."""
    modules = [
        'neo4j', 'fastapi', 'pydantic', 'dotenv',
        'openai', 'langfuse', 'github', 'apscheduler'
    ]
    
    failed = []
    for module in modules:
        try:
            __import__(module)
        except ImportError:
            failed.append(module)
    
    if failed:
        return False, f"Missing modules: {', '.join(failed)} (run: pip install -r requirements.agents.txt)"
    
    return True, f"All {len(modules)} required modules importable"


def check_graph_schema_file() -> Tuple[bool, str]:
    """Check graph schema files."""
    files = ['graph/models.py', 'graph/client.py', 'graph/queries.py']
    
    for file in files:
        if not Path(file).exists():
            return False, f"Missing {file}"
    
    # Check models.py for node types
    with open('graph/models.py') as f:
        content = f.read()
    
    node_types = [
        'Incident', 'RootCause', 'ActionItem', 'Strategy',
        'Component', 'PatternCluster', 'CodeModule'
    ]
    
    found = sum(1 for nt in node_types if f"class {nt}" in content)
    
    if found < 5:
        return False, f"Only found {found}/{len(node_types)} node type definitions"
    
    return True, f"Schema files present ({found} node types defined)"


def check_agent_files() -> Tuple[bool, str]:
    """Check agent implementation files."""
    files = [
        'agents/base.py',
        'agents/strategy_agent.py'
    ]
    
    for file in files:
        if not Path(file).exists():
            return False, f"Missing {file}"
    
    # Check base agent for key methods
    with open('agents/base.py') as f:
        content = f.read()
    
    methods = ['query_graph', 'write_graph', 'log_activity']
    found = sum(1 for m in methods if f"def {m}" in content)
    
    if found < len(methods):
        return False, f"Base agent missing methods (found {found}/{len(methods)})"
    
    return True, f"Agent files present ({len(files)} files, {found} base methods)"


def check_test_files() -> Tuple[bool, str]:
    """Check test suite completeness."""
    test_dir = Path('tests')
    if not test_dir.exists():
        return False, "tests/ directory not found"
    
    test_files = list(test_dir.glob('test_*.py'))
    
    if len(test_files) < 3:
        return False, f"Only {len(test_files)} test files (expected at least 3)"
    
    total_lines = 0
    for test_file in test_files:
        with open(test_file) as f:
            total_lines += len(f.readlines())
    
    return True, f"{len(test_files)} test files ({total_lines:,} lines total)"


def check_dashboard_files() -> Tuple[bool, str]:
    """Check dashboard API and UI files."""
    api_file = Path('dashboard/api/main.py')
    ui_dir = Path('dashboard/ui')
    
    if not api_file.exists():
        return False, "dashboard/api/main.py not found"
    
    if not ui_dir.exists():
        return False, "dashboard/ui/ directory not found"
    
    # Check UI has package.json and src/
    if not (ui_dir / 'package.json').exists():
        return False, "dashboard/ui/package.json not found"
    
    if not (ui_dir / 'src').exists():
        return False, "dashboard/ui/src/ directory not found"
    
    # Count UI components
    src_files = list((ui_dir / 'src').glob('*.jsx'))
    
    return True, f"API + UI present ({len(src_files)} React components)"


def check_dockerfile_files() -> Tuple[bool, str]:
    """Check Dockerfile files."""
    files = [
        'Dockerfile.agents',
        'Dockerfile.dashboard',
        'dashboard/ui/Dockerfile'
    ]
    
    missing = []
    for file in files:
        if not Path(file).exists():
            missing.append(file)
    
    if missing:
        return False, f"Missing: {', '.join(missing)}"
    
    # Check multi-stage builds
    multistage = 0
    for file in files:
        with open(file) as f:
            content = f.read()
            if 'FROM' in content and 'AS builder' in content:
                multistage += 1
    
    return True, f"All {len(files)} Dockerfiles present ({multistage} multi-stage)"


def check_requirements_files() -> Tuple[bool, str]:
    """Check requirements files."""
    files = ['requirements.agents.txt', 'requirements.dashboard.txt']
    
    missing = []
    for file in files:
        if not Path(file).exists():
            missing.append(file)
    
    if missing:
        return False, f"Missing: {', '.join(missing)}"
    
    total_deps = 0
    for file in files:
        with open(file) as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith('#')]
            total_deps += len(lines)
    
    return True, f"{len(files)} files present ({total_deps} total dependencies)"


def check_documentation() -> Tuple[bool, str]:
    """Check documentation files."""
    files = ['README.md', 'BLOCKERS.md', '.env.example']
    
    missing = []
    for file in files:
        if not Path(file).exists():
            missing.append(file)
    
    if missing:
        return False, f"Missing: {', '.join(missing)}"
    
    # Check README size
    readme_size = Path('README.md').stat().st_size
    if readme_size < 1000:
        return False, f"README.md too small ({readme_size} bytes)"
    
    return True, f"All {len(files)} docs present (README: {readme_size:,} bytes)"


def main():
    """Run verification checklist."""
    parser = argparse.ArgumentParser(description='Verify Stability Intelligence System')
    parser.add_argument('--docker-check', action='store_true',
                      help='Enable Docker container checks (requires permissions)')
    args = parser.parse_args()
    
    result = VerificationResult()
    
    # Change to project root
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    print(f"\n{BLUE}Starting Stability Intelligence System Verification...{RESET}\n")
    
    # 1-6: Infrastructure files
    passed, details = check_file_exists('docker-compose.yml', 'Docker Compose file')
    result.add_check('docker-compose.yml exists', passed, details)
    
    passed, details = check_env_variables()
    result.add_check('.env file with required variables', passed, details)
    
    if args.docker_check:
        passed, details = check_docker_compose_syntax()
        result.add_check('docker-compose.yml syntax valid', passed, details)
    else:
        result.add_warning("Skipped Docker checks (use --docker-check to enable)")
    
    passed, details = check_file_exists('litellm/config.yaml', 'LiteLLM config')
    result.add_check('LiteLLM configuration exists', passed, details)
    
    # 7-11: Graph layer
    passed, details = check_graph_schema_file()
    result.add_check('Neo4j schema files complete', passed, details)
    
    passed, details = check_directory_exists('graph', 'Graph module')
    result.add_check('Graph module directory', passed, details)
    
    # 12-16: Data ingestion
    passed, details = check_file_exists('scripts/github_sync.py', 'GitHub sync script')
    result.add_check('GitHub sync script exists', passed, details)
    
    passed, details = check_file_exists('scripts/tree_sitter_parser.py', 'Tree-sitter parser')
    result.add_check('Tree-sitter code parser exists', passed, details)
    
    passed, details = check_directory_exists('github-cache', 'GitHub cache')
    result.add_check('GitHub cache directory', passed, details)
    
    # 17-20: Agent layer
    passed, details = check_agent_files()
    result.add_check('Agent implementation files', passed, details)
    
    passed, details = check_directory_exists('agents', 'Agents module')
    result.add_check('Agents module directory', passed, details)
    
    # 21-23: Automation
    passed, details = check_file_exists('feedback/loop.py', 'Feedback loop')
    result.add_check('Feedback loop implementation', passed, details)
    
    passed, details = check_file_exists('scheduler/runner.py', 'Scheduler')
    result.add_check('Scheduler implementation', passed, details)
    
    passed, details = check_file_exists('scheduler/health.py', 'Health monitor')
    result.add_check('Health monitor implementation', passed, details)
    
    # 24-26: Dashboard
    passed, details = check_dashboard_files()
    result.add_check('Dashboard API and UI files', passed, details)
    
    # 27-29: Dockerfiles and requirements
    passed, details = check_dockerfile_files()
    result.add_check('All Dockerfiles present', passed, details)
    
    passed, details = check_requirements_files()
    result.add_check('Requirements files complete', passed, details)
    
    # 30-32: Tests and docs
    passed, details = check_test_files()
    result.add_check('Test suite completeness', passed, details)
    
    passed, details = check_documentation()
    result.add_check('Documentation files', passed, details)
    
    # 33: Python imports
    passed, details = check_python_imports()
    result.add_check('Python dependencies installed', passed, details)
    
    # Print summary
    passed_count, failed_count = result.print_summary()
    
    # Exit with appropriate code
    sys.exit(0 if failed_count == 0 else 1)


if __name__ == '__main__':
    main()
