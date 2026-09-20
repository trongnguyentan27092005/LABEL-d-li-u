"""Create blind, balanced pilot tasks for the public GitHub Pages annotator.

Selection labels are used only here to stratify the sample.  They are never
written to the public JSON consumed by the web application.
"""
from __future__ import annotations

import json
import random
import shutil
from PIL import Image
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Data" / "ViRPM.json"
PUBLIC = ROOT / "Label" / "pages"
ASSETS = PUBLIC / "assets"
OUTPUT = ROOT / "outputs" / "labeling_pilot"
RNG = random.Random(20260920)


def as_list(value):
    return value if isinstance(value, list) else json.loads(value)


def copy_asset(relative: str) -> str:
    source = ROOT / "Data" / relative
    target = ASSETS / relative
    if source.is_file() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            image.thumbnail((640, 640))
            image.save(target, quality=72, optimize=True)
    return "assets/" + relative.replace("\\", "/")


def main() -> None:
    rows = json.loads(SOURCE.read_text(encoding="utf-8"))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "data").mkdir(parents=True, exist_ok=True)
    if ASSETS.exists():
        shutil.rmtree(ASSETS)

    # T2T: exactly 10 rows from each of the 10 diagnostic groups.
    t2t = []
    for group in ["R1", "R2", "R3", "R4", "N1", "N2", "N3", "N4", "N5", "N6"]:
        candidates = [row for row in rows if row["Group T2T"] == group]
        chosen = RNG.sample(candidates, 10)
        t2t.extend({
            "item_id": f"pilot-t2t:{row['CommentId']}", "subset": "pilot-t2t-100",
            "review_id": str(row["CommentId"]), "product_id": str(row["ProductId"]),
            "product_name": row["ProductName"], "product_description": row["ProductDescription"],
            "comment": row["Comment"],
        } for row in chosen)
    RNG.shuffle(t2t)

    # I2I: all groups are present. M2 has only four natural image units in`n    # the frozen source, so it is included exhaustively rather than repeated.
    i2i_by_group = {group: [] for group in ["Match", "M1", "M2", "M3", "M4", "M5", "M6"]}
    for row in rows:
        review_paths, product_paths = as_list(row["CommentPath"]), as_list(row["ProductPath"])
        labels, groups = as_list(row["Label I2I"]), as_list(row["Group I2I"])
        for index, (review_path, label, group) in enumerate(zip(review_paths, labels, groups)):
            if group not in i2i_by_group:
                continue
            i2i_by_group[group].append((row, index, review_path, product_paths, label))

    quotas = {"Match": 26, "M1": 14, "M2": 4, "M3": 14, "M4": 14, "M5": 14, "M6": 14}
    i2i = []
    selected_counts = {}
    for group, quota in quotas.items():
        candidates = i2i_by_group[group]
        if len(candidates) < quota:
            raise RuntimeError(f"Not enough {group} units: {len(candidates)} < {quota}")
        selected = RNG.sample(candidates, quota)
        selected_counts[group] = len(selected)
        for row, index, review_path, product_paths, _label in selected:
            i2i.append({
                "item_id": f"pilot-i2i:{row['CommentId']}:{index}", "subset": "pilot-i2i-100",
                "review_id": str(row["CommentId"]), "image_index": index,
                "product_id": str(row["ProductId"]), "product_name": row["ProductName"],
                "product_description": row["ProductDescription"], "comment": row["Comment"],
                "review_image": copy_asset(review_path),
                "product_images": [copy_asset(path) for path in product_paths],
            })
    RNG.shuffle(i2i)

    # Public files contain no original labels or diagnostic group labels.
    (PUBLIC / "data" / "pilot_t2t.json").write_text(json.dumps(t2t, ensure_ascii=False), encoding="utf-8")
    (PUBLIC / "data" / "pilot_i2i.json").write_text(json.dumps(i2i, ensure_ascii=False), encoding="utf-8")
    audit = {
        "seed": 20260920,
        "t2t_rows": len(t2t), "t2t_sampling": {group: 10 for group in ["R1", "R2", "R3", "R4", "N1", "N2", "N3", "N4", "N5", "N6"]},
        "i2i_image_units": len(i2i), "i2i_sampling": selected_counts,
        "public_files_exclude_gold_labels": True,
        "copied_assets": sum(1 for path in ASSETS.rglob("*") if path.is_file()),
    }
    (OUTPUT / "pilot_sampling_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


