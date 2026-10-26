"""Optional interface for a future validated crop-hazard ML model.

No model is installed by this phase. This module deliberately returns an
unavailable result until an exact crop/hazard target has validated metadata.
"""
from typing import Any, Mapping, Optional, Protocol


class CropHazardModel(Protocol):
    version: str
    supported_targets: set[tuple[str, str]]
    validation_metadata: Mapping[str, Any]

    def predict(self, features: Mapping[str, Any]) -> Any: ...


def predict_crop_hazard(
    crop_id: str,
    hazard: str,
    features: Mapping[str, Any],
    model: Optional[CropHazardModel] = None,
) -> dict[str, Any]:
    """Return a validated target prediction, or MODEL_NOT_AVAILABLE.

    A model must explicitly support the exact canonical crop and hazard and
    provide validation metadata marked ``validated``. No damage probability is
    synthesized when those requirements are not met.
    """
    target = (crop_id, hazard)
    unavailable = {
        "status": "MODEL_NOT_AVAILABLE",
        "prediction": None,
        "model_version": None,
        "supported_target": {"crop_id": crop_id, "hazard": hazard},
        "validation_metadata": None,
    }
    if model is None:
        return unavailable
    metadata = getattr(model, "validation_metadata", None)
    targets = getattr(model, "supported_targets", set())
    version = getattr(model, "version", None)
    if (
        not isinstance(metadata, Mapping)
        or metadata.get("validation_status") != "validated"
        or target not in targets
        or not isinstance(version, str)
        or not version.strip()
    ):
        return unavailable
    return {
        "status": "PREDICTED",
        "prediction": model.predict(features),
        "model_version": version,
        "supported_target": {"crop_id": crop_id, "hazard": hazard},
        "validation_metadata": dict(metadata),
    }
