"""Provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Provider(ABC):
    name: str

    @abstractmethod
    def is_configured(self) -> bool:
        """Credentials are present (not validated against the service)."""

    @abstractmethod
    def describe(self) -> str:
        """One safe line for logs: secrets are masked."""

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Send one user prompt, return the reply text."""
