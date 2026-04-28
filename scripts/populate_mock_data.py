#!/usr/bin/env python3
"""
Populate Neo4j with mock RCA data for testing the dashboard.
"""

import os
from datetime import datetime, timezone, timedelta
from neo4j import GraphDatabase

# Neo4j connection
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:9687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "changeme_neo4j_pass123")

def create_mock_data():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session() as session:
        # Clear existing data
        print("Clearing existing data...")
        session.run("MATCH (n) DETACH DELETE n")
        
        # Create sample incidents
        print("Creating sample incidents and action items...")
        incidents = [
            {
                "id": "inc-12001",
                "number": 12001,
                "title": "[Bug] Payment timeout causing customer complaints",
                "description": "Multiple customers reported payment timeouts during checkout. Root cause: Database connection pool exhaustion.",
                "severity": "high",
                "status": "open",
                "created_at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "id": "inc-12002",
                "number": 12002,
                "title": "[Incident] API rate limit exceeded",
                "description": "Third-party API rate limit exceeded during peak hours. Need to implement caching.",
                "severity": "medium",
                "status": "investigating",
                "created_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "id": "inc-12003",
                "number": 12003,
                "title": "[RCA] Memory leak in payment processor",
                "description": "Investigation revealed memory leak in payment processor service. Requires code refactoring.",
                "severity": "high",
                "status": "resolved",
                "created_at": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
                "updated_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            },
        ]
        
        for incident in incidents:
            session.run("""
                CREATE (i:Incident {
                    id: $id,
                    number: $number,
                    title: $title,
                    description: $description,
                    severity: $severity,
                    status: $status,
                    created_at: $created_at,
                    updated_at: $updated_at,
                    repo: 'juspay/hyperswitch'
                })
            """, **incident)
        
        # Create action items
        action_items = [
            {
                "id": "ai-001",
                "title": "Increase database connection pool size",
                "description": "Increase max connections from 10 to 50 and implement connection timeout",
                "status": "open",
                "priority_score": 0.85,
                "forward_score": 8,
                "backward_score": 3,
            },
            {
                "id": "ai-002",
                "title": "Implement Redis caching layer",
                "description": "Add Redis cache with 5-minute TTL for frequently accessed API data",
                "status": "in_progress",
                "priority_score": 0.78,
                "forward_score": 7,
                "backward_score": 4,
            },
            {
                "id": "ai-003",
                "title": "Fix memory leak in payment processor",
                "description": "Refactor payment processor to properly release memory",
                "status": "resolved",
                "priority_score": 0.92,
                "forward_score": 9,
                "backward_score": 2,
            },
        ]
        
        for item in action_items:
            session.run("""
                CREATE (ai:ActionItem {
                    id: $id,
                    title: $title,
                    description: $description,
                    status: $status,
                    priority_score: $priority_score,
                    forward_score: $forward_score,
                    backward_score: $backward_score,
                    created_at: datetime(),
                    updated_at: datetime()
                })
            """, **item)
        
        # Create code files
        print("Creating code files...")
        files = [
            {"path": "src/core/payments/processor.rs", "language": "rust"},
            {"path": "src/core/database/pool.rs", "language": "rust"},
            {"path": "src/api/payments.rs", "language": "rust"},
        ]
        
        for file in files:
            session.run("""
                CREATE (f:CodeFile {
                    path: $path,
                    language: $language,
                    repo: 'juspay/hyperswitch'
                })
            """, **file)
        
        # Create RCA analyses
        print("Creating RCA analyses...")
        session.run("""
            MATCH (i:Incident {id: 'inc-12001'})
            CREATE (a:Analysis {
                id: randomUUID(),
                root_cause: 'Database connection pool exhaustion',
                symptoms: ['Payment timeouts', 'High latency', 'Connection errors'],
                timeline: '2026-04-21T10:00:00Z - Issue started',
                contributing_factors: ['High traffic', 'Insufficient pool size'],
                created_at: datetime()
            })
            CREATE (i)-[:HAS_ANALYSIS]->(a)
        """)
        
        session.run("""
            MATCH (i:Incident {id: 'inc-12002'})
            CREATE (a:Analysis {
                id: randomUUID(),
                root_cause: 'Third-party API rate limiting without caching',
                symptoms: ['API 429 errors', 'Failed requests'],
                timeline: '2026-04-23T14:30:00Z - Peak traffic triggered rate limit',
                contributing_factors: ['No caching layer', 'High request volume'],
                created_at: datetime()
            })
            CREATE (i)-[:HAS_ANALYSIS]->(a)
        """)
        
        # Create strategies
        print("Creating strategies...")
        session.run("""
            MATCH (ai:ActionItem {id: 'ai-001'})
            CREATE (s:Strategy {
                id: randomUUID(),
                title: 'Increase database connection pool size',
                description: 'Increase max connections from 10 to 50 and implement connection timeout',
                implementation_steps: ['Update pool config', 'Add monitoring', 'Load test'],
                estimated_impact: 'High',
                estimated_effort: 'Low',
                priority_score: 0.85,
                status: 'proposed',
                created_at: datetime()
            })
            CREATE (ai)-[:IMPLEMENTS]->(s)
        """)
        
        session.run("""
            MATCH (ai:ActionItem {id: 'ai-002'})
            CREATE (s:Strategy {
                id: randomUUID(),
                title: 'Implement Redis caching layer for API calls',
                description: 'Add Redis cache with 5-minute TTL for frequently accessed API data',
                implementation_steps: ['Deploy Redis', 'Implement cache wrapper', 'Update API client'],
                estimated_impact: 'High',
                estimated_effort: 'Medium',
                priority_score: 0.78,
                status: 'in_progress',
                created_at: datetime()
            })
            CREATE (ai)-[:IMPLEMENTS]->(s)
        """)
        
        session.run("""
            MATCH (ai:ActionItem {id: 'ai-003'})
            CREATE (s:Strategy {
                id: randomUUID(),
                title: 'Fix memory leak in payment processor',
                description: 'Refactor payment processor to properly release memory after each transaction',
                implementation_steps: ['Profile memory usage', 'Identify leak source', 'Refactor code', 'Test'],
                estimated_impact: 'High',
                estimated_effort: 'High',
                priority_score: 0.92,
                status: 'implemented',
                created_at: datetime()
            })
            CREATE (ai)-[:IMPLEMENTS]->(s)
        """)
        
        # Create pattern clusters
        print("Creating pattern clusters...")
        session.run("""
            CREATE (pc:PatternCluster {
                id: randomUUID(),
                name: 'Database Connection Pool Exhaustion',
                description: 'Recurring pattern of connection pool issues during peak load',
                frequency: 3,
                severity: 'high',
                trend: 'increasing',
                first_seen: '2026-03-15T00:00:00Z',
                last_seen: '2026-04-21T10:00:00Z',
                affected_components: ['payment-processor', 'database-layer']
            })
        """)
        
        session.run("""
            CREATE (pc:PatternCluster {
                id: randomUUID(),
                name: 'Third-Party API Rate Limiting',
                description: 'Rate limit issues with external APIs during traffic spikes',
                frequency: 2,
                severity: 'medium',
                trend: 'stable',
                first_seen: '2026-04-10T00:00:00Z',
                last_seen: '2026-04-23T14:30:00Z',
                affected_components: ['api-client', 'payment-gateway']
            })
        """)
        
        # Link incidents to pattern clusters
        session.run("""
            MATCH (i:Incident {id: 'inc-12001'})
            MATCH (pc:PatternCluster {name: 'Database Connection Pool Exhaustion'})
            CREATE (i)-[:EXHIBITS]->(pc)
        """)
        
        session.run("""
            MATCH (i:Incident {id: 'inc-12002'})
            MATCH (pc:PatternCluster {name: 'Third-Party API Rate Limiting'})
            CREATE (i)-[:EXHIBITS]->(pc)
        """)
        
        # Create metrics
        print("Creating metrics...")
        session.run("""
            CREATE (m:Metric {
                id: randomUUID(),
                name: 'mttr_hours',
                value: 4.5,
                timestamp: datetime(),
                category: 'reliability'
            })
        """)
        
        session.run("""
            CREATE (m:Metric {
                id: randomUUID(),
                name: 'incident_count_7d',
                value: 3,
                timestamp: datetime(),
                category: 'reliability'
            })
        """)
        
        print("\n✅ Mock data created successfully!")
        print("\nSummary:")
        print("  - 3 Incidents created")
        print("  - 3 Action Items created")
        print("  - 3 Code files created")
        print("  - 2 RCA analyses created")
        print("  - 2 Strategies created")
        print("  - 2 Pattern Clusters created")
        print("  - 2 Metrics created")
        
        # Verify data
        result = session.run("""
            MATCH (i:Incident)
            RETURN count(i) as count
        """)
        incident_count = result.single()["count"]
        
        result = session.run("""
            MATCH (ai:ActionItem)
            RETURN count(ai) as count
        """)
        action_count = result.single()["count"]
        
        result = session.run("""
            MATCH (s:Strategy)
            RETURN count(s) as count
        """)
        strategy_count = result.single()["count"]
        
        print(f"\nVerification:")
        print(f"  - {incident_count} incidents in database")
        print(f"  - {action_count} action items in database")
        print(f"  - {strategy_count} strategies in database")
    
    driver.close()

if __name__ == "__main__":
    create_mock_data()
