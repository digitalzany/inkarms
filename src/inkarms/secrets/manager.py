"""
Secrets manager for InkArms.

Manages encrypted storage of API keys and other sensitive data.
Uses Fernet symmetric encryption with a master key.
"""

import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class SecretsError(Exception):
    """Base exception for secrets-related errors."""

    pass


class SecretNotFoundError(SecretsError):
    """Requested secret does not exist."""

    pass


class DecryptionError(SecretsError):
    """Failed to decrypt a secret."""

    pass


class SecretsManager:
    """
    Manages encrypted API keys and secrets.

    Secrets are stored as individual encrypted files in the secrets directory.
    A master key is used for encryption/decryption and is stored separately.
    """

    # Standard environment variable mappings for providers
    PROVIDER_ENV_VARS = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "google": "GOOGLE_API_KEY",
        "gemini": "GOOGLE_API_KEY",
        "huggingface": "HUGGINGFACE_API_KEY",
        "cohere": "COHERE_API_KEY",
        "replicate": "REPLICATE_API_TOKEN",
        "azure": "AZURE_API_KEY",
        "aws": "AWS_ACCESS_KEY_ID",  # Note: AWS needs multiple keys
        "mistral": "MISTRAL_API_KEY",
        "groq": "GROQ_API_KEY",
        "together": "TOGETHER_API_KEY",
        "anyscale": "ANYSCALE_API_KEY",
        "perplexity": "PERPLEXITYAI_API_KEY",
        "deepinfra": "DEEPINFRA_API_KEY",
    }

    def __init__(self, secrets_dir: Path | None = None):
        """
        Initialize the secrets manager.

        Args:
            secrets_dir: Directory to store secrets. Defaults to ~/.inkarms/secrets/
        """
        if secrets_dir is None:
            from inkarms.storage.paths import get_secrets_dir

            secrets_dir = get_secrets_dir()

        self.secrets_dir = Path(secrets_dir)
        self._ensure_secrets_dir()
        self._fernet: Fernet | None = None

    def _ensure_secrets_dir(self) -> None:
        """Ensure secrets directory exists with proper permissions."""
        self.secrets_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

        # Ensure directory has restricted permissions
        try:
            self.secrets_dir.chmod(0o700)
        except OSError:
            logger.warning(f"Could not set permissions on secrets directory: {self.secrets_dir}")

    def _get_fernet(self) -> Fernet:
        """Get or create the Fernet encryption instance."""
        if self._fernet is None:
            self._fernet = self._load_or_create_key()
        return self._fernet

    def _load_or_create_key(self) -> Fernet:
        """Load existing master key or create new one."""
        key_path = self.secrets_dir / "master.key"

        if key_path.exists():
            key = key_path.read_bytes()
            logger.debug("Loaded existing master key")
        else:
            key = Fernet.generate_key()
            key_path.write_bytes(key)
            try:
                key_path.chmod(0o600)  # Owner read/write only
            except OSError:
                logger.warning("Could not set permissions on master key file")
            logger.info("Generated new master key")

        return Fernet(key)

    def set(self, name: str, value: str) -> None:
        """
        Store an encrypted secret.

        Args:
            name: Secret name (e.g., 'openai', 'anthropic').
            value: The secret value to encrypt and store.
        """
        fernet = self._get_fernet()
        encrypted = fernet.encrypt(value.encode())

        secret_path = self.secrets_dir / f"{name}.enc"
        secret_path.write_bytes(encrypted)

        try:
            secret_path.chmod(0o600)  # Owner read/write only
        except OSError:
            logger.warning(f"Could not set permissions on secret file: {name}")

        logger.info(f"Stored secret: {name}")

    def get(self, name: str) -> str | None:
        """
        Retrieve a decrypted secret.

        Args:
            name: Secret name to retrieve.

        Returns:
            The decrypted secret value, or None if not found.

        Raises:
            DecryptionError: If decryption fails (likely master key changed).
        """
        secret_path = self.secrets_dir / f"{name}.enc"

        if not secret_path.exists():
            return None

        try:
            fernet = self._get_fernet()
            encrypted = secret_path.read_bytes()
            return fernet.decrypt(encrypted).decode()
        except InvalidToken as e:
            raise DecryptionError(
                f"Failed to decrypt secret '{name}'. Master key may have changed."
            ) from e

    def delete(self, name: str) -> bool:
        """
        Delete a secret.

        Args:
            name: Secret name to delete.

        Returns:
            True if deleted, False if not found.
        """
        secret_path = self.secrets_dir / f"{name}.enc"

        if secret_path.exists():
            secret_path.unlink()
            logger.info(f"Deleted secret: {name}")
            return True

        return False

    def list(self) -> list[str]:
        """
        List all stored secret names.

        Returns:
            List of secret names (without .enc extension).
        """
        return sorted(p.stem for p in self.secrets_dir.glob("*.enc") if p.is_file())

    def exists(self, name: str) -> bool:
        """
        Check if a secret exists.

        Args:
            name: Secret name to check.

        Returns:
            True if the secret exists.
        """
        secret_path = self.secrets_dir / f"{name}.enc"
        return secret_path.exists()

    def load_to_env(self, name: str, env_var: str | None = None) -> bool:
        """
        Load a secret into an environment variable.

        Args:
            name: Secret name to load.
            env_var: Environment variable name. Defaults to standard mapping.

        Returns:
            True if loaded, False if secret not found.
        """
        # Determine environment variable name
        if env_var is None:
            env_var = self.PROVIDER_ENV_VARS.get(name.lower())
            if env_var is None:
                # Default pattern: uppercase with _API_KEY suffix
                env_var = f"{name.upper()}_API_KEY"

        # Skip if already set in environment
        if os.environ.get(env_var):
            logger.debug(f"{env_var} already set in environment, skipping")
            return True

        # Get and set the secret
        value = self.get(name)
        if value:
            os.environ[env_var] = value
            logger.debug(f"Loaded secret {name} into {env_var}")
            return True

        return False

    def load_all_to_env(self) -> dict[str, bool]:
        """
        Load all stored secrets into environment variables.

        Returns:
            Dict mapping secret names to whether they were loaded.
        """
        results = {}
        for name in self.list():
            results[name] = self.load_to_env(name)
        return results

    def get_env_var_name(self, provider: str) -> str:
        """
        Get the environment variable name for a provider.

        Args:
            provider: Provider name.

        Returns:
            The environment variable name.
        """
        return self.PROVIDER_ENV_VARS.get(provider.lower(), f"{provider.upper()}_API_KEY")

    def is_key_available(self, provider: str) -> bool:
        """
        Check if an API key is available (from env or secrets).

        Args:
            provider: Provider name to check.

        Returns:
            True if a key is available.
        """
        # Check environment variable first
        env_var = self.get_env_var_name(provider)
        if os.environ.get(env_var):
            return True

        # Check encrypted secrets
        return self.exists(provider)
