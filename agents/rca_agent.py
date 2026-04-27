"""RCA Analysis Agent - Core intelligence for root cause analysis with pattern recognition.

This agent:
1. Analyzes unanalyzed Incident nodes
2. Uses LiteLLM to extract root causes with historical context
3. Detects recurring patterns (clusters of >= 3 similar incidents)
4. Creates Analysis and PatternCluster nodes
"""
import json
import logging
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class RCAAgent(BaseAgent):
    """Analyzes incidents for root causes and detects patterns."""
    
    def __init__(self):
        super().__init__(name="rca_agent")
    
    def run(self) -> Dict[str, Any]:
        """Main entry point for RCA agent.
        
        Returns:
            Statistics dict with incidents_analyzed and patterns_detected
        """
        logger.info("RCA Agent starting...")
        
        # Step 1: Find unanalyzed incidents
        unanalyzed_incidents = self._find_unanalyzed_incidents()
        logger.info(f"Found {len(unanalyzed_incidents)} unanalyzed incidents")
        
        incidents_analyzed = 0
        
        # Step 2: Analyze each incident
        for incident in unanalyzed_incidents:
            try:
                self.analyze_incident(incident)
                incidents_analyzed += 1
                logger.info(f"Analyzed incident {incident['id']}: {incident['title']}")
            except Exception as e:
                logger.error(f"Failed to analyze incident {incident['id']}: {e}")
        
        # Step 3: Detect patterns
        patterns_detected = 0
        try:
            patterns_detected = self.detect_patterns()
            logger.info(f"Detected {patterns_detected} new pattern clusters")
        except Exception as e:
            logger.error(f"Pattern detection failed: {e}")
        
        # Step 4: Log activity
        stats = {
            "incidents_analyzed": incidents_analyzed,
            "patterns_detected": patterns_detected,
        }
        
        self.log_activity(
            message=f"RCA analysis complete: {incidents_analyzed} incidents analyzed, {patterns_detected} patterns detected",
            data=stats,
        )
        
        logger.info(f"RCA Agent complete: {stats}")
        return stats
    
    def _find_unanalyzed_incidents(self) -> List[Dict[str, Any]]:
        """Find Incident nodes without Analysis."""
        cypher = """
        MATCH (i:Incident)
        WHERE NOT EXISTS {
            MATCH (i)-[:HAS_ANALYSIS]->(:Analysis)
        }
        RETURN i.id AS id,
               i.title AS title,
               i.body AS body,
               i.raw_body AS raw_body,
               i.github_number AS github_number,
               i.severity AS severity,
               i.occurred_at AS occurred_at,
               i.affected_flows AS affected_flows,
               i.created_at AS created_at
        ORDER BY i.created_at DESC
        LIMIT 50
        """
        return self.query_graph(cypher)
    
    def analyze_incident(self, incident: Dict[str, Any]):
        """Analyze a single incident with historical context.
        
        Args:
            incident: Incident node data
        """
        # Find similar historical incidents
        similar_incidents = self.find_similar_incidents(incident)
        
        # Build LiteLLM prompt
        prompt = self._build_analysis_prompt(incident, similar_incidents)
        
        # Call LiteLLM
        try:
            system_prompt = """You are an expert SRE analyzing production incidents for the Hyperswitch payment platform.
Your goal is to identify root causes, categorize incidents, and detect patterns.
Always respond with valid JSON matching the requested schema."""
            
            response = self.call_claude(
                prompt=prompt,
                system=system_prompt,
                trace_name="rca-incident-analysis",
                max_tokens=2000,
            )
            
            # Parse response
            analysis_data = self._parse_llm_response(response)
            
            # Create Analysis node
            self._create_analysis_node(incident["id"], analysis_data)
            
        except Exception as e:
            logger.error(f"LiteLLM call failed for incident {incident['id']}: {e}")
            # Create basic analysis with error flag
            self._create_fallback_analysis(incident["id"], str(e))
    
    def find_similar_incidents(self, incident: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find similar historical incidents for context.
        
        Uses:
        - Same severity
        - Overlapping affected_flows
        - Similar title keywords
        
        Args:
            incident: Current incident data
        
        Returns:
            List of up to 5 similar incidents with their analyses
        """
        # Extract keywords from title
        title = incident.get("title", "")
        # Simple keyword extraction (could be enhanced with NLP)
        keywords = [word.lower() for word in title.split() if len(word) > 4][:5]
        
        cypher = """
        MATCH (i:Incident)-[:HAS_ANALYSIS]->(a:Analysis)
        WHERE i.id <> $current_id
          AND i.occurred_at < $current_occurred_at
        WITH i, a,
             CASE 
                 WHEN i.severity = $severity THEN 2
                 ELSE 0
             END AS severity_score,
             size([flow IN i.affected_flows WHERE flow IN $affected_flows]) AS flow_overlap
        WHERE severity_score > 0 OR flow_overlap > 0
        OPTIONAL MATCH (a)-[:HAS_ROOT_CAUSE]->(rc:RootCause)
        RETURN i.id AS id,
               i.title AS title,
               i.body AS body,
               i.severity AS severity,
               i.occurred_at AS occurred_at,
               COALESCE(rc.description, 'Unknown') AS root_cause,
               a.category AS category,
               a.affected_components AS affected_components,
               (severity_score + flow_overlap * 3) AS similarity_score
        ORDER BY similarity_score DESC
        LIMIT 5
        """
        
        params = {
            "current_id": incident["id"],
            "current_occurred_at": incident.get("occurred_at") or incident.get("created_at"),
            "severity": incident.get("severity", "P3"),
            "affected_flows": incident.get("affected_flows") or [],
        }
        
        return self.query_graph(cypher, params)
    
    def _build_analysis_prompt(
        self,
        incident: Dict[str, Any],
        similar_incidents: List[Dict[str, Any]],
    ) -> str:
        """Build the LiteLLM analysis prompt."""
        # Format similar incidents
        historical_context = ""
        if similar_incidents:
            historical_context = "\n\nSimilar Historical Incidents (for context):\n"
            for i, sim in enumerate(similar_incidents, 1):
                historical_context += f"""
{i}. [{sim.get('severity', 'P3')}] {sim.get('title', 'N/A')}
   Occurred: {sim.get('occurred_at', 'N/A')}
   Root Cause: {sim.get('root_cause', 'N/A')}
   Category: {sim.get('category', 'N/A')}
   Components: {sim.get('affected_components', [])}
"""
        
        prompt = f"""You are analyzing a production incident for Hyperswitch payment platform.

Current Incident:
Title: {incident.get('title', 'N/A')}
Severity: {incident.get('severity', 'P3')}
Created: {incident.get('created_at', 'N/A')}
Affected Flows: {incident.get('affected_flows', [])}

Description:
{incident.get('body', incident.get('raw_body', 'No description available'))}
{historical_context}

Based on the incident description and historical context, extract the following in JSON format:

{{
  "root_cause": "Brief 1-2 sentence root cause description",
  "category": "timeout|config|race_condition|api_change|infrastructure|data_corruption|backward_compat|resource_exhaustion|dependency_failure|other",
  "contributing_factors": ["factor1", "factor2", "..."],
  "affected_components": ["component1", "component2", "..."],
  "is_recurring": true/false,
  "pattern_signature": "unique identifier combining category + key components (e.g., 'timeout-redis-cache' or 'config-payment-gateway')"
}}

Instructions:
- Be specific and concise in root_cause
- Choose the most accurate category
- List 2-5 contributing factors (technical reasons)
- Identify 2-5 affected components (services, APIs, databases, etc.)
- Mark is_recurring as true if similar historical incidents exist
- Create pattern_signature by combining category with main affected component(s)

Respond ONLY with valid JSON, no other text.
"""
        return prompt
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parse LiteLLM JSON response.
        
        Args:
            response: LiteLLM response text
            
        Returns:
            Parsed analysis data
        """
        try:
            # Try to find JSON in response (handle cases where LLM adds extra text)
            start_idx = response.find("{")
            end_idx = response.rfind("}") + 1
            
            if start_idx == -1 or end_idx == 0:
                raise ValueError("No JSON object found in response")
            
            json_str = response[start_idx:end_idx]
            data = json.loads(json_str)
            
            # Validate required fields
            required_fields = ["root_cause", "category", "pattern_signature"]
            for field in required_fields:
                if field not in data:
                    raise ValueError(f"Missing required field: {field}")
            
            # Set defaults for optional fields
            data.setdefault("contributing_factors", [])
            data.setdefault("affected_components", [])
            data.setdefault("is_recurring", False)
            
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}\nResponse: {response}")
            raise
        except Exception as e:
            logger.error(f"Response parsing error: {e}")
            raise
    
    def _create_analysis_node(self, incident_id: str, analysis_data: Dict[str, Any]):
        """Create Analysis node and link to Incident.
        
        Also creates a RootCause node with proper graph relationships.
        
        Args:
            incident_id: Incident node ID
            analysis_data: Parsed analysis data from LiteLLM
        """
        analysis_id = f"analysis-{uuid.uuid4().hex[:12]}"
        root_cause_id = f"rootcause-{uuid.uuid4().hex[:12]}"
        
        cypher = """
        MATCH (i:Incident {id: $incident_id})
        
        // Create Analysis node (without root_cause as string property)
        CREATE (a:Analysis {
            id: $analysis_id,
            incident_id: $incident_id,
            category: $category,
            contributing_factors: $contributing_factors,
            affected_components: $affected_components,
            is_recurring: $is_recurring,
            pattern_signature: $pattern_signature,
            created_at: datetime(),
            updated_at: datetime()
        })
        CREATE (i)-[:HAS_ANALYSIS]->(a)
        
        // Create RootCause node as separate entity
        CREATE (rc:RootCause {
            id: $root_cause_id,
            description: $root_cause_description,
            category: $category,
            confidence: 0.85,
            mechanism: $root_cause_description,
            created_at: datetime(),
            updated_at: datetime()
        })
        
        // Link Analysis to RootCause
        CREATE (a)-[:HAS_ROOT_CAUSE]->(rc)
        
        // Link Incident to RootCause (identified relationship)
        CREATE (i)-[:IDENTIFIED]->(rc)
        
        RETURN a.id, rc.id
        """
        
        result = self.write_graph(cypher, {
            "analysis_id": analysis_id,
            "root_cause_id": root_cause_id,
            "incident_id": incident_id,
            "root_cause_description": analysis_data["root_cause"],
            "category": analysis_data["category"],
            "contributing_factors": analysis_data.get("contributing_factors", []),
            "affected_components": analysis_data.get("affected_components", []),
            "is_recurring": analysis_data.get("is_recurring", False),
            "pattern_signature": analysis_data["pattern_signature"],
        })
        
        logger.info(f"Created Analysis node: {analysis_id}, RootCause node: {root_cause_id}")
    
    def _create_fallback_analysis(self, incident_id: str, error_msg: str):
        """Create basic analysis when LiteLLM fails.
        
        Also creates a RootCause node for failed analyses.
        
        Args:
            incident_id: Incident node ID
            error_msg: Error message
        """
        analysis_id = f"analysis-{uuid.uuid4().hex[:12]}"
        root_cause_id = f"rootcause-{uuid.uuid4().hex[:12]}"
        
        cypher = """
        MATCH (i:Incident {id: $incident_id})
        
        // Create Analysis node
        CREATE (a:Analysis {
            id: $analysis_id,
            incident_id: $incident_id,
            category: 'other',
            contributing_factors: ['analysis_failed'],
            affected_components: [],
            is_recurring: false,
            pattern_signature: 'unanalyzed',
            created_at: datetime(),
            updated_at: datetime()
        })
        CREATE (i)-[:HAS_ANALYSIS]->(a)
        
        // Create RootCause node for failed analysis
        CREATE (rc:RootCause {
            id: $root_cause_id,
            description: $root_cause_description,
            category: 'unknown',
            confidence: 0.0,
            mechanism: $root_cause_description,
            created_at: datetime(),
            updated_at: datetime()
        })
        
        // Link Analysis to RootCause
        CREATE (a)-[:HAS_ROOT_CAUSE]->(rc)
        
        // Link Incident to RootCause
        CREATE (i)-[:IDENTIFIED]->(rc)
        
        RETURN a.id, rc.id
        """
        
        self.write_graph(cypher, {
            "analysis_id": analysis_id,
            "root_cause_id": root_cause_id,
            "incident_id": incident_id,
            "root_cause_description": f"Analysis failed: {error_msg[:200]}",
        })
        
        logger.warning(f"Created fallback Analysis node: {analysis_id}, RootCause node: {root_cause_id}")
    
    def detect_patterns(self) -> int:
        """Detect pattern clusters from analyzed incidents.
        
        Groups incidents by:
        - Same pattern_signature
        - Same category + overlapping components
        
        Creates PatternCluster for groups with >= 3 incidents.
        
        Returns:
            Number of new pattern clusters created
        """
        # Step 1: Find existing pattern signatures
        existing_patterns = self._get_existing_pattern_signatures()
        
        # Step 2: Group incidents by pattern_signature
        pattern_groups = self._group_incidents_by_pattern()
        
        patterns_created = 0
        
        for pattern_sig, incidents in pattern_groups.items():
            # Skip if already have a cluster for this pattern
            if pattern_sig in existing_patterns:
                continue
            
            # Skip if fewer than 3 incidents
            if len(incidents) < 3:
                continue
            
            try:
                # Calculate trend
                trend = self._calculate_trend(incidents)
                
                # Create PatternCluster
                self._create_pattern_cluster(pattern_sig, incidents, trend)
                patterns_created += 1
                
            except Exception as e:
                logger.error(f"Failed to create pattern cluster for {pattern_sig}: {e}")
        
        return patterns_created
    
    def _get_existing_pattern_signatures(self) -> set:
        """Get set of existing pattern signatures."""
        cypher = """
        MATCH (pc:PatternCluster)
        RETURN pc.pattern_signature AS signature
        """
        results = self.query_graph(cypher)
        return {r["signature"] for r in results if r.get("signature")}
    
    def _group_incidents_by_pattern(self) -> Dict[str, List[Dict[str, Any]]]:
        """Group incidents by pattern_signature.
        
        Returns:
            Dict mapping pattern_signature to list of incident data
        """
        cypher = """
        MATCH (i:Incident)-[:HAS_ANALYSIS]->(a:Analysis)
        WHERE a.pattern_signature IS NOT NULL
          AND a.pattern_signature <> 'unanalyzed'
        OPTIONAL MATCH (a)-[:HAS_ROOT_CAUSE]->(rc:RootCause)
        RETURN i.id AS incident_id,
               i.title AS title,
               i.occurred_at AS occurred_at,
               i.created_at AS created_at,
               a.pattern_signature AS pattern_signature,
               a.category AS category,
               COALESCE(rc.description, 'Unknown') AS root_cause,
               a.affected_components AS affected_components
        ORDER BY a.pattern_signature, i.occurred_at
        """
        
        results = self.query_graph(cypher)
        
        # Group by pattern_signature
        groups = {}
        for result in results:
            sig = result["pattern_signature"]
            if sig not in groups:
                groups[sig] = []
            groups[sig].append(result)
        
        return groups
    
    def _calculate_trend(self, incidents: List[Dict[str, Any]]) -> str:
        """Calculate trend for a pattern cluster.
        
        Compares last 30 days vs previous 30 days.
        
        Args:
            incidents: List of incidents in this pattern
            
        Returns:
            Trend string: 'worsening', 'stable', or 'improving'
        """
        now = datetime.utcnow()
        last_30_days = now - timedelta(days=30)
        prev_30_days = now - timedelta(days=60)
        
        recent_count = 0
        previous_count = 0
        
        for incident in incidents:
            occurred_at = incident.get("occurred_at") or incident.get("created_at")
            
            # Handle string datetime
            if isinstance(occurred_at, str):
                try:
                    occurred_at = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
                except:
                    continue
            
            if not occurred_at:
                continue
            
            if occurred_at >= last_30_days:
                recent_count += 1
            elif occurred_at >= prev_30_days:
                previous_count += 1
        
        # Determine trend
        if recent_count > previous_count:
            return "worsening"
        elif recent_count < previous_count:
            return "improving"
        else:
            return "stable"
    
    def _create_pattern_cluster(
        self,
        pattern_signature: str,
        incidents: List[Dict[str, Any]],
        trend: str,
    ):
        """Create PatternCluster node.
        
        Args:
            pattern_signature: Unique pattern identifier
            incidents: List of incidents in this pattern
            trend: Trend direction
        """
        cluster_id = f"pattern-{uuid.uuid4().hex[:12]}"
        
        # Extract metadata from incidents
        category = incidents[0].get("category", "unknown")
        affected_components = []
        for inc in incidents:
            components = inc.get("affected_components") or []
            affected_components.extend(components)
        # Get unique components
        affected_components = list(set(affected_components))
        
        # Get date range
        dates = []
        for inc in incidents:
            occurred_at = inc.get("occurred_at") or inc.get("created_at")
            if isinstance(occurred_at, str):
                try:
                    occurred_at = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
                except:
                    continue
            if occurred_at:
                dates.append(occurred_at)
        
        first_occurrence = min(dates) if dates else datetime.utcnow()
        last_occurrence = max(dates) if dates else datetime.utcnow()
        
        # Create descriptive name
        name = f"{category.title()} Pattern: {pattern_signature}"
        description = f"Recurring pattern affecting {', '.join(affected_components[:3])}"
        
        cypher = """
        CREATE (pc:PatternCluster {
            id: $id,
            pattern_signature: $pattern_signature,
            name: $name,
            description: $description,
            frequency: $frequency,
            trend: $trend,
            root_cause_category: $category,
            affected_components: $affected_components,
            first_occurrence: $first_occurrence,
            last_occurrence: $last_occurrence,
            created_at: datetime(),
            updated_at: datetime()
        })
        WITH pc
        UNWIND $incident_ids AS incident_id
        MATCH (i:Incident {id: incident_id})
        CREATE (i)-[:EXHIBITS]->(pc)
        RETURN pc.id
        """
        
        self.write_graph(cypher, {
            "id": cluster_id,
            "pattern_signature": pattern_signature,
            "name": name,
            "description": description,
            "frequency": len(incidents),
            "trend": trend,
            "category": category,
            "affected_components": affected_components,
            "first_occurrence": first_occurrence,
            "last_occurrence": last_occurrence,
            "incident_ids": [inc["incident_id"] for inc in incidents],
        })
        
        logger.info(f"Created PatternCluster: {cluster_id} - {name} (frequency={len(incidents)}, trend={trend})")
