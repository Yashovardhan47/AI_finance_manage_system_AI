from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSession:
    provider: str
    status: str
    checkout_url: str


class SandboxPaymentProvider:
    """Safe local provider used until a licensed payment integration is configured."""

    name = "sandbox"

    def prepare(self, payment_id: int) -> ProviderSession:
        return ProviderSession(
            provider=self.name,
            status="requires_authorization",
            checkout_url=f"/sandbox/authorize/{payment_id}",
        )


def get_payment_provider() -> SandboxPaymentProvider:
    return SandboxPaymentProvider()

