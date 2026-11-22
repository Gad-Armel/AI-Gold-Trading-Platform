"""
Model Versioning, Artifact Persistence & Performance Registry.
Manages serialized model weights, preprocessing scalers, calibration parameters,
and historical inference prediction logs for auditability.
"""

from typing import Dict, Any, List, Optional
import os
import json
import time
from datetime import datetime, timezone
import joblib


class ModelRegistry:
    """
    Handles saving, versioning, and loading of trained models,
    metadata checkpoints, and live prediction logs.
    """

    def __init__(self, registry_dir: Optional[str] = None):
        if registry_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            registry_dir = os.path.join(base_dir, "artifacts", "model_registry")
        
        self.registry_dir = registry_dir
        os.makedirs(self.registry_dir, exist_ok=True)
        self.logs_dir = os.path.join(self.registry_dir, "prediction_logs")
        os.makedirs(self.logs_dir, exist_ok=True)

    def save_model_version(
        self,
        model_obj: Any,
        version_tag: str,
        metadata: Dict[str, Any],
        metrics: Dict[str, Any]
    ) -> str:
        """
        Saves a trained model instance with its metadata and out-of-sample metrics.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        version_name = f"xauusd_ai_{version_tag}_{timestamp}"
        version_folder = os.path.join(self.registry_dir, version_name)
        os.makedirs(version_folder, exist_ok=True)

        # Save model object
        model_file = os.path.join(version_folder, "model.joblib")
        joblib.dump(model_obj, model_file)

        # Save manifest
        manifest = {
            "version": version_name,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "symbol": "XAUUSD",
            "model_type": metadata.get("model_type", "HistGradientBoosting"),
            "probability_calibration": metadata.get("probability_calibration", "isotonic"),
            "features_count": metadata.get("features_count", 0),
            "feature_names": metadata.get("feature_names", []),
            "validation_metrics": metrics,
            "notes": "Trained with Purged Walk-Forward TimeSeriesSplit with Embargo."
        }

        manifest_file = os.path.join(version_folder, "manifest.json")
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # Update latest pointer
        latest_file = os.path.join(self.registry_dir, "LATEST_VERSION.txt")
        with open(latest_file, "w", encoding="utf-8") as f:
            f.write(version_name)

        return version_folder

    def log_live_prediction(self, payload: Dict[str, Any]):
        """
        Appends live model prediction payload to daily rolling audit log.
        """
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = os.path.join(self.logs_dir, f"inference_{today_str}.jsonl")
        
        entry = {
            "logged_at_utc": datetime.now(timezone.utc).isoformat(),
            **payload
        }

        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            pass  # Non-blocking for live execution speed
