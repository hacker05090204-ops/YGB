"""GROUP 5 import restoration coverage for impl_v1 symbols."""


def test_governor_import_symbols_are_restored():
    from impl_v1.phase49.governors.g09_device_trust import DeviceTrustGuard
    from impl_v1.phase49.governors.g27_integrity_chain import (
        IntegrityChain,
        IntegrityChainBuilder,
    )

    assert DeviceTrustGuard.__name__ == "DeviceTrustGuard"
    assert issubclass(IntegrityChain, IntegrityChainBuilder)


def test_moe_import_symbol_is_restored():
    from impl_v1.phase49.moe import MoEBugClassifier, MoEClassifier

    assert issubclass(MoEClassifier, MoEBugClassifier)


def test_real_dataset_loader_import_symbol_is_restored():
    from impl_v1.training.data.real_dataset_loader import (
        IngestionPipelineDataset,
        RealDatasetLoader,
    )

    assert issubclass(RealDatasetLoader, IngestionPipelineDataset)
