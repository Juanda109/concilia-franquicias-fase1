"""El ConfigMap del dataset en IaC debe ser copia exacta del dataset versionado."""

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_dataset_configmap import DATASETS, OUT, render  # noqa: E402


def test_configmap_matches_every_dataset():
    cm = yaml.safe_load(OUT.read_text())
    assert set(cm["data"]) == {d.name for d in DATASETS}
    for dataset in DATASETS:
        assert json.loads(cm["data"][dataset.name]) == json.loads(dataset.read_text())


def test_configmap_file_is_up_to_date():
    assert OUT.read_text() == render(), "regenerar con scripts/build_dataset_configmap.py"
