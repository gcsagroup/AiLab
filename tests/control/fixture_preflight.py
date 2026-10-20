"""仅验证控制进程接口，不冒充真实分词器。"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--snapshot", type=Path, required=True)
parser.add_argument("--output-dir", type=Path, required=True)
args = parser.parse_args()
snapshot = json.loads(args.snapshot.read_text())
recipe = {"id": "control-fixture-only"}
effective = dict(snapshot["runtime"])
if snapshot.get("evaluation_kind") in {"quantized_model", "capability_comparison"}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from adapters.mlx_text.evaluation import model_evaluation_identity
    recipe["evaluation_implementation_sha256"] = hashlib.sha256((Path(__file__).resolve().parents[2] / "adapters/mlx_text/evaluation.py").read_bytes()).hexdigest()
    identity, identity_digest = model_evaluation_identity(snapshot, hashlib.sha256(json.dumps(recipe).encode()).hexdigest())
    effective.update(model_evaluation_recipe=identity, model_evaluation_recipe_digest=identity_digest)
result = {"can_submit": True, "blocking": [], "effective_config": effective, "recipe": recipe,
          "check_report": {"fixture_only": True}, "tokenization_recipe_digest": hashlib.sha256(json.dumps(recipe).encode()).hexdigest()}
print(json.dumps(result))
