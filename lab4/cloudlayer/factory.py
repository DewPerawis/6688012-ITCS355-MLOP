"""Select the configured cloud implementation."""
from cloudlayer.base import CloudAdapter


def get_adapter(cfg) -> CloudAdapter:
    if cfg.provider.lower() != "azure":
        raise ValueError("Lab 3 is configured for Azure; only the Azure adapter is implemented")
    from cloudlayer.azure import AzureAdapter

    return AzureAdapter(cfg)
