"""Sample priority score calculations for documentation."""


def calculate_priority_score(forward_score: int, backward_score: int, complexity: str, expected_reduction: float) -> float:
    """Calculate priority score using the formula.
    
    Formula:
    priority_score = (forward_score + backward_score) * (expected_reduction / 100) / complexity_weight
    
    Higher score = higher priority
    """
    complexity_weight = {
        "low": 1,
        "medium": 2,
        "high": 3,
    }
    
    weight = complexity_weight.get(complexity.lower(), 2)
    
    priority_score = (
        (forward_score + backward_score) * 
        (expected_reduction / 100.0) /
        weight
    )
    
    return round(priority_score, 2)


def main():
    """Generate sample calculations for documentation."""
    print("\n" + "=" * 80)
    print("PRIORITY ESTIMATION AGENT - SAMPLE CALCULATIONS")
    print("=" * 80)
    
    # Sample 1: High-impact, low-complexity action
    print("\nSample 1: Contract Test Suite")
    print("-" * 80)
    forward_score = 12  # Pattern occurs 12 times
    backward_score = 7  # Would have prevented 7 past incidents
    complexity = "low"
    expected_reduction = 85.0
    
    priority = calculate_priority_score(
        forward_score, backward_score, complexity, expected_reduction
    )
    
    print(f"Forward Score (pattern frequency): {forward_score}")
    print(f"Backward Score (historical impact): {backward_score}")
    print(f"Complexity: {complexity}")
    print(f"Expected Reduction: {expected_reduction}%")
    print(f"Priority Score: {priority}")
    print(f"Formula: ({forward_score} + {backward_score}) * ({expected_reduction}/100) / 1 = {priority}")
    
    # Sample 2: Medium-impact, medium-complexity action
    print("\n\nSample 2: Automated Regression Suite")
    print("-" * 80)
    forward_score = 6
    backward_score = 4
    complexity = "medium"
    expected_reduction = 60.0
    
    priority = calculate_priority_score(
        forward_score, backward_score, complexity, expected_reduction
    )
    
    print(f"Forward Score (pattern frequency): {forward_score}")
    print(f"Backward Score (historical impact): {backward_score}")
    print(f"Complexity: {complexity}")
    print(f"Expected Reduction: {expected_reduction}%")
    print(f"Priority Score: {priority}")
    print(f"Formula: ({forward_score} + {backward_score}) * ({expected_reduction}/100) / 2 = {priority}")
    
    # Sample 3: Low-frequency, high-complexity action
    print("\n\nSample 3: Architecture Refactoring")
    print("-" * 80)
    forward_score = 3
    backward_score = 2
    complexity = "high"
    expected_reduction = 40.0
    
    priority = calculate_priority_score(
        forward_score, backward_score, complexity, expected_reduction
    )
    
    print(f"Forward Score (pattern frequency): {forward_score}")
    print(f"Backward Score (historical impact): {backward_score}")
    print(f"Complexity: {complexity}")
    print(f"Expected Reduction: {expected_reduction}%")
    print(f"Priority Score: {priority}")
    print(f"Formula: ({forward_score} + {backward_score}) * ({expected_reduction}/100) / 3 = {priority}")
    
    # Sample 4: Critical pattern with high impact
    print("\n\nSample 4: Critical Bug Fix with High Impact")
    print("-" * 80)
    forward_score = 20
    backward_score = 15
    complexity = "medium"
    expected_reduction = 95.0
    
    priority = calculate_priority_score(
        forward_score, backward_score, complexity, expected_reduction
    )
    
    print(f"Forward Score (pattern frequency): {forward_score}")
    print(f"Backward Score (historical impact): {backward_score}")
    print(f"Complexity: {complexity}")
    print(f"Expected Reduction: {expected_reduction}%")
    print(f"Priority Score: {priority}")
    print(f"Formula: ({forward_score} + {backward_score}) * ({expected_reduction}/100) / 2 = {priority}")
    
    # Sample 5: Edge case - no historical data
    print("\n\nSample 5: New Pattern (No Historical Data)")
    print("-" * 80)
    forward_score = 8
    backward_score = 0  # No historical incidents
    complexity = "low"
    expected_reduction = 70.0
    
    priority = calculate_priority_score(
        forward_score, backward_score, complexity, expected_reduction
    )
    
    print(f"Forward Score (pattern frequency): {forward_score}")
    print(f"Backward Score (historical impact): {backward_score}")
    print(f"Complexity: {complexity}")
    print(f"Expected Reduction: {expected_reduction}%")
    print(f"Priority Score: {priority}")
    print(f"Formula: ({forward_score} + {backward_score}) * ({expected_reduction}/100) / 1 = {priority}")
    
    # Sample 6: Edge case - no pattern found
    print("\n\nSample 6: Isolated Action Item (No Pattern)")
    print("-" * 80)
    forward_score = 1  # Default when no pattern found
    backward_score = 0
    complexity = "medium"
    expected_reduction = 30.0
    
    priority = calculate_priority_score(
        forward_score, backward_score, complexity, expected_reduction
    )
    
    print(f"Forward Score (pattern frequency): {forward_score} [DEFAULT]")
    print(f"Backward Score (historical impact): {backward_score}")
    print(f"Complexity: {complexity}")
    print(f"Expected Reduction: {expected_reduction}%")
    print(f"Priority Score: {priority}")
    print(f"Formula: ({forward_score} + {backward_score}) * ({expected_reduction}/100) / 2 = {priority}")
    
    print("\n" + "=" * 80)
    print("INTERPRETATION GUIDE")
    print("=" * 80)
    print("Priority Score > 10:  CRITICAL  - Implement immediately")
    print("Priority Score 5-10:  HIGH      - Schedule in current sprint")
    print("Priority Score 2-5:   MEDIUM    - Plan for next sprint")
    print("Priority Score < 2:   LOW       - Backlog item")
    print("=" * 80)
    
    print("\n" + "=" * 80)
    print("SCORING ALGORITHM SUMMARY")
    print("=" * 80)
    print("""
The Priority Estimation Agent uses a data-driven approach to score ActionItems:

1. FORWARD SCORE (Future Impact):
   - Derived from related PatternCluster frequency
   - Represents how many future incidents this action will prevent
   - Default: 1 (if no pattern found)

2. BACKWARD SCORE (Historical Impact):
   - Count of past incidents that share affected components
   - Represents validation that this would have helped historically
   - Default: 0 (if no matching incidents)

3. COMPLEXITY ESTIMATION (via LLM):
   - Uses Claude to analyze action item description
   - Estimates: complexity (low/medium/high), effort hours, risk, expected reduction
   - Complexity weights: low=1, medium=2, high=3

4. PRIORITY SCORE FORMULA:
   priority_score = (forward_score + backward_score) × (expected_reduction / 100) / complexity_weight

5. BENEFITS:
   - Objective, data-driven prioritization
   - Balances impact vs effort
   - Accounts for both future prevention and historical validation
   - LLM provides nuanced complexity assessment
   - Automated re-scoring as new data arrives

6. SCHEDULED EXECUTION:
   - Runs every 2 hours
   - Scores ActionItems without priority_score
   - Updates graph with all calculated metrics
    """)
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
