"""Neo4j driver with connection retry logic."""
import os
import time
import logging
from typing import Optional, List, Dict, Any, Callable
from contextlib import contextmanager

from neo4j import GraphDatabase, Driver, Session
from neo4j.exceptions import ServiceUnavailable, AuthError, TransientError

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Neo4j client with retry and connection pooling."""
    
    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        max_retries: int = 5,
        retry_delay: float = 5.0,
    ):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://neo4j:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "password")
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._driver: Optional[Driver] = None
    
    def connect(self) -> Driver:
        """Connect to Neo4j with retry logic."""
        if self._driver is not None:
            return self._driver
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Connecting to Neo4j at {self.uri} (attempt {attempt + 1}/{self.max_retries})")
                self._driver = GraphDatabase.driver(
                    self.uri,
                    auth=(self.user, self.password),
                )
                # Verify connectivity
                self._driver.verify_connectivity()
                logger.info("Neo4j connection established")
                return self._driver
            except ServiceUnavailable as e:
                last_error = e
                logger.warning(f"Neo4j unavailable, retrying in {self.retry_delay}s...")
                time.sleep(self.retry_delay)
            except AuthError as e:
                logger.error(f"Neo4j authentication failed: {e}")
                raise
            except Exception as e:
                last_error = e
                logger.warning(f"Neo4j connection error: {e}, retrying in {self.retry_delay}s...")
                time.sleep(self.retry_delay)
        
        raise ServiceUnavailable(f"Failed to connect to Neo4j after {self.max_retries} attempts: {last_error}")
    
    def close(self):
        """Close the Neo4j connection."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")
    
    @contextmanager
    def session(self):
        """Context manager for Neo4j sessions."""
        driver = self.connect()
        session = driver.session()
        try:
            yield session
        finally:
            session.close()
    
    def run(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
        read_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Execute a Cypher query with retry."""
        parameters = parameters or {}
        
        for attempt in range(self.max_retries):
            try:
                with self.session() as session:
                    if read_only:
                        result = session.execute_read(lambda tx: list(tx.run(query, parameters)))
                    else:
                        result = session.execute_write(lambda tx: list(tx.run(query, parameters)))
                    
                    # Convert Neo4j records to dicts
                    return [dict(record) for record in result]
            except TransientError as e:
                if attempt < self.max_retries - 1:
                    logger.warning(f"Transient error, retrying: {e}")
                    time.sleep(self.retry_delay * (attempt + 1))
                else:
                    raise
            except ServiceUnavailable as e:
                if attempt < self.max_retries - 1:
                    logger.warning(f"Service unavailable, retrying: {e}")
                    self._driver = None  # Force reconnect
                    time.sleep(self.retry_delay)
                else:
                    raise
        
        return []
    
    def read(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a read-only Cypher query."""
        return self.run(query, parameters, read_only=True)
    
    def write(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a write Cypher query."""
        return self.run(query, parameters, read_only=False)
    
    def health_check(self) -> Dict[str, Any]:
        """Check Neo4j health status."""
        try:
            result = self.read("CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition")
            return {
                "status": "healthy",
                "components": result,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }


# Singleton instance
_client: Optional[Neo4jClient] = None


def get_client() -> Neo4jClient:
    """Get or create the Neo4j client singleton."""
    global _client
    if _client is None:
        _client = Neo4jClient()
    return _client


def get_driver() -> Driver:
    """Get the underlying Neo4j driver."""
    return get_client().connect()


def close_client():
    """Close the Neo4j client."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


# Convenience functions
def query(cypher: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Execute a Cypher read query."""
    return get_client().read(cypher, parameters)


def write(cypher: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Execute a Cypher write query."""
    return get_client().write(cypher, parameters)
