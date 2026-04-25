"""
Secrets Management Module.

Supports:
- HashiCorp Vault (primary)
- AWS Secrets Manager (secondary)
- Environment variable fallback (development only)

Configuration:
    SECRETS_BACKEND=vault|aws|env
    VAULT_ADDR=https://vault.example.com
    VAULT_ROLE_ID=role-id
    VAULT_SECRET_ID=secret-id
    AWS_REGION=us-east-1
    AWS_SECRET_NAME=my-app/secrets
"""

import os
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod


@dataclass
class SecretValue:
    """Container for secret values with metadata."""
    value: str
    metadata: Dict[str, Any]
    backend: str
    version: Optional[int] = None


class SecretsBackend(ABC):
    """Abstract base class for secrets backends."""
    
    @abstractmethod
    def get_secret(self, key: str) -> Optional[SecretValue]:
        """Retrieve a secret by key."""
        pass
    
    @abstractmethod
    def get_secret_batch(self, keys: list) -> Dict[str, SecretValue]:
        """Retrieve multiple secrets efficiently."""
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """Verify backend connectivity."""
        pass


class VaultBackend(SecretsBackend):
    """HashiCorp Vault backend implementation."""
    
    def __init__(self, addr: str, role_id: str, secret_id: str, mount_point: str = "secret"):
        self.addr = addr.rstrip("/")
        self.role_id = role_id
        self.secret_id = secret_id
        self.mount_point = mount_point
        self._token: Optional[str] = None
        self._client: Any = None
        
    def _get_client(self):
        """Lazy-load hvac client."""
        if self._client is None:
            try:
                import hvac
                self._client = hvac.Client(url=self.addr)
                # AppRole authentication
                response = self._client.auth.approle.login(
                    role_id=self.role_id,
                    secret_id=self.secret_id,
                )
                self._token = response["auth"]["client_token"]
                return self._client
            except ImportError:
                raise RuntimeError("hvac package required for Vault backend. Install: pip install hvac")
        return self._client
    
    def get_secret(self, key: str) -> Optional[SecretValue]:
        """Retrieve secret from Vault KV v2."""
        client = self._get_client()
        try:
            # Parse key format: "path/to/secret.field" or "path/to/secret"
            if "." in key:
                path, field = key.split(".", 1)
            else:
                path, field = key, None
            
            response = client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point=self.mount_point,
            )
            
            data = response["data"]["data"]
            version = response["data"]["metadata"]["version"]
            
            if field and field in data:
                value = data[field]
            elif field is None:
                value = json.dumps(data) if len(data) > 1 else list(data.values())[0]
            else:
                return None
            
            return SecretValue(
                value=str(value),
                metadata={"path": path, "field": field, "backend_version": version},
                backend="vault",
                version=version,
            )
        except Exception as e:
            # Log error but don't expose details
            return None
    
    def get_secret_batch(self, keys: list) -> Dict[str, SecretValue]:
        """Batch retrieve secrets."""
        results = {}
        for key in keys:
            result = self.get_secret(key)
            if result:
                results[key] = result
        return results
    
    def health_check(self) -> bool:
        """Check Vault health."""
        try:
            client = self._get_client()
            return client.sys.is_initialized() and not client.sys.is_sealed()
        except:
            return False


class AWSSecretsBackend(SecretsBackend):
    """AWS Secrets Manager backend."""
    
    def __init__(self, region: str, secret_name: str):
        self.region = region
        self.secret_name = secret_name
        self._client: Any = None
    
    def _get_client(self):
        """Lazy-load boto3 client."""
        if self._client is None:
            try:
                import boto3
                self._client = boto3.client(
                    service_name="secretsmanager",
                    region_name=self.region,
                )
                return self._client
            except ImportError:
                raise RuntimeError("boto3 package required for AWS backend. Install: pip install boto3")
        return self._client
    
    def get_secret(self, key: str) -> Optional[SecretValue]:
        """Retrieve secret from AWS Secrets Manager."""
        client = self._get_client()
        try:
            response = client.get_secret_value(SecretId=self.secret_name)
            
            # Parse JSON secret string
            secret_string = response.get("SecretString", "{}")
            secret_data = json.loads(secret_string)
            
            if key not in secret_data:
                return None
            
            return SecretValue(
                value=secret_data[key],
                metadata={
                    "arn": response.get("ARN"),
                    "created_date": str(response.get("CreatedDate")),
                },
                backend="aws",
                version=response.get("VersionId"),
            )
        except Exception:
            return None
    
    def get_secret_batch(self, keys: list) -> Dict[str, SecretValue]:
        """Batch retrieve from AWS (single call for all keys)."""
        client = self._get_client()
        try:
            response = client.get_secret_value(SecretId=self.secret_name)
            secret_string = response.get("SecretString", "{}")
            secret_data = json.loads(secret_string)
            
            results = {}
            for key in keys:
                if key in secret_data:
                    results[key] = SecretValue(
                        value=secret_data[key],
                        metadata={"arn": response.get("ARN")},
                        backend="aws",
                        version=response.get("VersionId"),
                    )
            return results
        except Exception:
            return {}
    
    def health_check(self) -> bool:
        """Check AWS Secrets Manager connectivity."""
        try:
            client = self._get_client()
            client.describe_secret(SecretId=self.secret_name)
            return True
        except:
            return False


class EnvBackend(SecretsBackend):
    """Environment variable backend (DEVELOPMENT ONLY)."""
    
    def __init__(self, prefix: str = ""):
        self.prefix = prefix
    
    def get_secret(self, key: str) -> Optional[SecretValue]:
        """Get secret from environment variable."""
        env_key = f"{self.prefix}{key}".upper().replace(".", "_")
        value = os.getenv(env_key)
        
        if value is None:
            return None
        
        return SecretValue(
            value=value,
            metadata={"source": "environment"},
            backend="env",
        )
    
    def get_secret_batch(self, keys: list) -> Dict[str, SecretValue]:
        """Batch retrieve from environment."""
        results = {}
        for key in keys:
            result = self.get_secret(key)
            if result:
                results[key] = result
        return results
    
    def health_check(self) -> bool:
        """Environment is always healthy."""
        return True


class SecretsManager:
    """
    Primary interface for secrets management.
    
    Auto-selects backend based on environment configuration:
    - Production: Vault or AWS
    - Development: Environment variables
    
    All values are cached for 5 minutes to reduce backend calls.
    """
    
    _instance: Optional["SecretsManager"] = None
    _backend: Optional[SecretsBackend] = None
    _cache: Dict[str, tuple] = {}  # key -> (value, timestamp)
    _cache_ttl_seconds: int = 300
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize_backend()
        return cls._instance
    
    def _initialize_backend(self):
        """Initialize appropriate backend based on config."""
        backend_type = os.getenv("SECRETS_BACKEND", "env").lower()
        
        if backend_type == "vault":
            addr = os.getenv("VAULT_ADDR")
            role_id = os.getenv("VAULT_ROLE_ID")
            secret_id = os.getenv("VAULT_SECRET_ID")
            mount_point = os.getenv("VAULT_MOUNT_POINT", "secret")
            
            if not all([addr, role_id, secret_id]):
                raise ValueError("Vault backend requires VAULT_ADDR, VAULT_ROLE_ID, VAULT_SECRET_ID")
            
            self._backend = VaultBackend(addr, role_id, secret_id, mount_point)
            
        elif backend_type == "aws":
            region = os.getenv("AWS_REGION", "us-east-1")
            secret_name = os.getenv("AWS_SECRET_NAME")
            
            if not secret_name:
                raise ValueError("AWS backend requires AWS_SECRET_NAME")
            
            self._backend = AWSSecretsBackend(region, secret_name)
            
        else:
            # Default to environment variables
            self._backend = EnvBackend()
    
    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get secret value by key."""
        import time
        
        # Check cache
        now = time.time()
        if key in self._cache:
            value, timestamp = self._cache[key]
            if now - timestamp < self._cache_ttl_seconds:
                return value
        
        # Fetch from backend
        result = self._backend.get_secret(key)
        if result:
            self._cache[key] = (result.value, now)
            return result.value
        
        return default
    
    def get_required(self, key: str) -> str:
        """Get secret, raise if missing."""
        value = self.get(key)
        if value is None:
            raise ValueError(f"Required secret '{key}' not found in {self._backend.__class__.__name__}")
        return value
    
    def get_batch(self, keys: list) -> Dict[str, str]:
        """Get multiple secrets efficiently."""
        results = self._backend.get_secret_batch(keys)
        return {k: v.value for k, v in results.items()}
    
    def health_check(self) -> bool:
        """Verify secrets backend is accessible."""
        return self._backend.health_check()
    
    def invalidate_cache(self):
        """Clear the secrets cache."""
        self._cache.clear()


def get_secrets_manager() -> SecretsManager:
    """Get the singleton SecretsManager instance."""
    return SecretsManager()
