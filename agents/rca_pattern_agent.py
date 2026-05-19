"""RCA Pattern Agent - extracts affected components from incidents and links them to pattern clusters.

Runs after incident ingestion to ensure PatternCluster nodes have accurate
affected_components data and proper Neo4j AFFECTS relationships.
"""
import logging
import uuid
from typing import List, Dict, Any, Set

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class RcaPatternAgent(BaseAgent):
    """Links affected components to pattern clusters via Neo4j AFFECTS relationships.

    Workflow:
    1. Query all PatternClusters that have linked Incidents
    2. Collect affected_flows from those incidents
    3. Create Component nodes for each unique flow/component
    4. Create PatternCluster -[:AFFECTS]-> Component relationships
    5. Update pc.affected_components property for fast property reads
    6. Log activity
    """

    def __init__(self):
        super().__init__(name="rca_pattern_agent")

    def run(self):
        """Run the RCA pattern agent."""
        logger.info("RCA pattern agent starting...")

        clusters_updated = 0
        components_created = 0

        clusters = self._get_clusters_with_incidents()
        logger.info(f"Found {len(clusters)} pattern clusters with linked incidents")

        for cluster in clusters:
            try:
                n_components = self._link_components_to_cluster(cluster)
                if n_components:
                    clusters_updated += 1
                    components_created += n_components
            except Exception as e:
                logger.error(
                    f"Failed to process cluster {cluster.get('id')}: {e}"
                )

        self.log_activity(
            message=(
                f"RCA pattern agent complete: {clusters_updated} clusters updated, "
                f"{components_created} component links created"
            ),
            data={
                "clusters_processed": len(clusters),
                "clusters_updated": clusters_updated,
                "components_created": components_created,
            },
        )
        logger.info(
            f"RCA pattern agent complete: {clusters_updated} clusters updated, "
            f"{components_created} component links created"
        )

    def _get_clusters_with_incidents(self) -> List[Dict[str, Any]]:
        """Return pattern clusters along with affected_flows from linked incidents."""
        cypher = """
        MATCH (pc:PatternCluster)<-[:BELONGS_TO_CLUSTER]-(i:Incident)
        WHERE i.affected_flows IS NOT NULL AND size(i.affected_flows) > 0
        RETURN pc.id AS id,
               pc.name AS name,
               collect(DISTINCT i.affected_flows) AS flows_per_incident
        """
        return self.query_graph(cypher)

    def _link_components_to_cluster(self, cluster: Dict[str, Any]) -> int:
        """Create Component nodes and AFFECTS relationships for a single cluster.

        Returns the number of new component links created.
        """
        cluster_id = cluster.get("id")
        flows_per_incident: List[List[str]] = cluster.get("flows_per_incident", [])

        # Flatten and deduplicate component names
        component_names: Set[str] = set()
        for flows in flows_per_incident:
            if isinstance(flows, list):
                for flow in flows:
                    if flow and isinstance(flow, str) and flow.strip():
                        component_names.add(flow.strip())

        if not component_names:
            return 0

        # Create Component nodes and AFFECTS relationships for each component
        links_created = 0
        for name in sorted(component_names):
            component_id = f"comp-{uuid.uuid5(uuid.NAMESPACE_DNS, name).hex[:12]}"
            cypher = """
            MERGE (c:Component {name: $component_name})
            ON CREATE SET c.id = $component_id,
                          c.component_type = 'module',
                          c.stability_score = 1.0,
                          c.incident_count = 0,
                          c.created_at = datetime(),
                          c.updated_at = datetime()
            ON MATCH SET  c.updated_at = datetime()
            WITH c
            MATCH (pc:PatternCluster {id: $pattern_cluster_id})
            MERGE (pc)-[r:AFFECTS]->(c)
            RETURN c.name AS component_name
            """
            result = self.write_graph(cypher, {
                "component_name": name,
                "component_id": component_id,
                "pattern_cluster_id": cluster_id,
            })
            if result:
                links_created += 1

        if links_created:
            # Update the pc.affected_components property for fast property access
            all_names = list(sorted(component_names))
            update_cypher = """
            MATCH (pc:PatternCluster {id: $cluster_id})
            SET pc.affected_components = $components,
                pc.updated_at = datetime()
            RETURN pc.id AS id
            """
            self.write_graph(update_cypher, {
                "cluster_id": cluster_id,
                "components": all_names[:20],  # cap at 20
            })
            logger.info(
                f"Cluster {cluster_id}: linked {links_created} components "
                f"{all_names[:5]}..."
            )

        return links_created
