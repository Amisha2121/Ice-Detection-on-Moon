"""DFSAR ingestion metadata — tracks polarimetry source and data quality flags."""

import json
import os

META_FILENAME = "dfsar_ingestion_meta.json"


def meta_path(processed_dir: str) -> str:
    return os.path.join(processed_dir, META_FILENAME)


def write_dfsar_meta(processed_dir: str, **fields) -> str:
    path = meta_path(processed_dir)
    os.makedirs(processed_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fields, f, indent=2)
    return path


def load_dfsar_meta(processed_dir: str) -> dict:
    path = meta_path(processed_dir)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {
        "polarimetry_source": "unknown",
        "synthetic": False,
        "cpr_dop_detection_valid": True,
        "limitation_message": None,
    }


def data_quality_block(meta: dict) -> dict:
    return {
        "synthetic": meta.get("synthetic", False),
        "polarimetry_source": meta.get("polarimetry_source"),
        "cpr_dop_detection_valid": meta.get("cpr_dop_detection_valid", True),
        "limitation_message": meta.get("limitation_message"),
    }
