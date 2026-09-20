"""Local, blind annotation app for ViRPM.

Run from the repository root, for example:
    python Label/app.py --input artifacts/splits/core.csv --subset core-1000

The application deliberately never sends existing dataset labels, model scores,
or another annotator's labels to the browser.  An annotation unit is one review
image paired with the complete product-image gallery.  T2T is recorded as a
review-level field on each unit; downstream analysis should deduplicate it by
``review_id`` for each annotator.
"""

from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import re
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "Data"
STORE_ROOT = Path(__file__).resolve().parent / "data" / "annotations"
LOCK = threading.Lock()

T2T_GROUPS = {
    "R1": "Thuộc tính / chất lượng",
    "R2": "Trải nghiệm mua hàng",
    "R3": "Không khớp với mô tả",
    "R4": "Khuyến nghị",
    "N1": "Không có nội dung",
    "N2": "Thư rác / quảng cáo",
    "N3": "Lạc đề",
    "N4": "Chỉ để nhận thưởng",
    "N5": "Không khớp sản phẩm",
    "N6": "Khác (cần nêu lý do)",
}
I2I_GROUPS = {
    "M1": "Không thể nhận diện (UND)",
    "M2": "Thư rác / quảng cáo",
    "M3": "Lạc đề",
    "M4": "Chỉ để nhận thưởng",
    "M5": "Không khớp sản phẩm",
    "M6": "Khác (cần nêu lý do)",
}


def parse_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value]
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return []
    try:
        parsed = json.loads(text)
        return [str(x) for x in parsed] if isinstance(parsed, list) else [str(parsed)]
    except json.JSONDecodeError:
        return [text]


def load_rows(input_path: Path, subset: str) -> list[dict]:
    if input_path.suffix.lower() == ".csv":
        with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    else:
        with input_path.open("r", encoding="utf-8") as handle:
            rows = json.load(handle)
        if not isinstance(rows, list):
            raise ValueError("JSON input must be a list of records.")

    units: list[dict] = []
    for row in rows:
        review_paths = parse_list(row.get("CommentPath"))
        product_paths = parse_list(row.get("ProductPath"))
        # A row without a review image cannot be an I2I annotation unit.
        for image_index, review_path in enumerate(review_paths):
            comment_id = str(row.get("CommentId", ""))
            unit_id = f"{subset}:{comment_id}:{image_index}"
            units.append(
                {
                    "item_id": unit_id,
                    "subset": subset,
                    "review_id": comment_id,
                    "image_index": image_index,
                    "product_id": str(row.get("ProductId", "")),
                    "product_name": str(row.get("ProductName", "")),
                    "product_description": str(row.get("ProductDescription", "")),
                    "comment": str(row.get("Comment", "")),
                    "review_image": review_path,
                    "product_images": product_paths,
                }
            )
    return units


def safe_annotator(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())[:80]
    if not cleaned:
        raise ValueError("Tên người gán không hợp lệ.")
    return cleaned


def annotation_file(annotator: str) -> Path:
    return STORE_ROOT / f"{safe_annotator(annotator)}.jsonl"


def completed_ids(annotator: str) -> set[str]:
    path = annotation_file(annotator)
    if not path.exists():
        return set()
    latest: dict[str, dict] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
                latest[record["item_id"]] = record
            except (json.JSONDecodeError, KeyError):
                continue
    return set(latest)


def path_to_url(relative_path: str) -> str | None:
    try:
        candidate = (DATA_ROOT / relative_path).resolve()
        candidate.relative_to(DATA_ROOT.resolve())
    except (ValueError, OSError):
        return None
    return "/image?path=" + relative_path.replace("\\", "/")


def public_unit(unit: dict) -> dict:
    return {
        **{key: unit[key] for key in ("item_id", "subset", "review_id", "image_index", "product_id", "product_name", "product_description", "comment")},
        "review_image_url": path_to_url(unit["review_image"]),
        "product_image_urls": [url for path in unit["product_images"] if (url := path_to_url(path))],
    }


def html_page() -> str:
    return r'''<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ViRPM · Gán nhãn độc lập</title>
<style>
:root{--ink:#172033;--muted:#64748b;--line:#dbe3ef;--bg:#f5f7fb;--blue:#2563eb;--danger:#b42318}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font:15px system-ui,-apple-system,Segoe UI,sans-serif}
header{background:#111827;color:white;padding:16px 5vw;display:flex;justify-content:space-between;align-items:center} header h1{font-size:18px;margin:0} header span{font-size:13px;color:#cbd5e1}
main{max-width:1500px;margin:24px auto;padding:0 24px}.card{background:white;border:1px solid var(--line);border-radius:14px;padding:20px;margin-bottom:16px;box-shadow:0 2px 7px #1720330a}
#login{max-width:520px;margin:72px auto}.hint,.meta{color:var(--muted);font-size:13px}.hidden{display:none!important}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.label-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.title{font-weight:750;font-size:16px;margin:0 0 10px}label{display:block;font-weight:650;margin:12px 0 6px}input,textarea,select,button{font:inherit}input,textarea,select{width:100%;padding:10px;border:1px solid #b9c6d8;border-radius:8px;background:white}textarea{min-height:82px;resize:vertical}.content{white-space:pre-wrap;background:#f8fafc;border-radius:8px;padding:12px;max-height:170px;overflow:auto}.images{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:8px}.images img{width:100%;height:120px;object-fit:contain;background:#f8fafc;border:1px solid var(--line);border-radius:8px}.review-image{max-width:100%;max-height:430px;display:block;margin:auto;object-fit:contain;background:#f8fafc;border-radius:10px;border:1px solid var(--line)}.choices{display:flex;gap:8px;flex-wrap:wrap}.choice{border:1px solid #b9c6d8;border-radius:8px;padding:9px 11px;cursor:pointer;font-weight:600}.choice input{width:auto;margin-right:5px}.choice:has(input:checked){border-color:var(--blue);background:#eff6ff;color:#1d4ed8}.actions{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:18px}button{border:0;border-radius:9px;padding:11px 16px;background:var(--blue);color:white;font-weight:700;cursor:pointer}button.secondary{background:#e8edf5;color:#25324a}button:disabled{opacity:.5;cursor:not-allowed}.error{color:var(--danger);font-weight:650}.required{color:var(--danger)}.nav{display:flex;gap:10px;align-items:center}@media(max-width:850px){.grid,.label-grid{grid-template-columns:1fr}main{padding:0 12px}.images{grid-template-columns:repeat(3,1fr)}}
</style></head><body>
<header><h1>ViRPM · Gán nhãn độc lập</h1><span id="who">Chưa đăng nhập</span></header>
<main>
<section id="login" class="card"><h2 class="title">Bắt đầu phiên gán nhãn</h2><p>Nhập tên hoặc mã người gán. Mỗi người có tệp lưu riêng; nhãn vàng, dự đoán mô hình và nhãn của người khác không hiển thị.</p><label for="annotator">Tên / mã người gán</label><input id="annotator" autocomplete="name" placeholder="Ví dụ: annotator_01"><p id="loginError" class="error"></p><button onclick="start()">Vào gán nhãn</button></section>
<section id="work" class="hidden"><div class="card"><div class="nav"><strong id="progress">Đang tải…</strong><span class="meta" id="unitMeta"></span><button class="secondary" onclick="logout()">Đổi người gán</button></div></div>
<div id="empty" class="card hidden"><h2 class="title">Đã hoàn tất</h2><p>Bạn đã gán tất cả mẫu trong tập hiện tại. Dữ liệu đã được lưu tại máy chủ cục bộ.</p></div>
<form id="form" class="hidden" onsubmit="save(event)">
<div class="grid"><section class="card"><h2 class="title">Thông tin sản phẩm</h2><div class="content" id="product"></div><label>Mô tả sản phẩm</label><div class="content" id="description"></div><label>Ảnh sản phẩm (tập ảnh đối chiếu)</label><div class="images" id="productImages"></div></section>
<section class="card"><h2 class="title">Review</h2><label>Văn bản review</label><div class="content" id="comment"></div><label>Ảnh review cần gán I2I</label><img id="reviewImage" class="review-image" alt="Ảnh review"><p id="missingImage" class="error hidden">Không tìm thấy ảnh review cục bộ.</p></section></div>
<div class="label-grid"><section class="card"><h2 class="title">A. Liên quan văn bản (T2T)</h2><label>Nhãn chính <span class="required">*</span></label><div class="choices"><label class="choice"><input type="radio" name="t2t_label" value="1" required> Relevant (1)</label><label class="choice"><input type="radio" name="t2t_label" value="0"> Irrelevant (0)</label></div><label for="t2t_group">Nhóm chẩn đoán <span class="required">*</span></label><select id="t2t_group" required><option value="">Chọn nhóm…</option></select></section>
<section class="card"><h2 class="title">B. Tương ứng ảnh (I2I)</h2><label>Nhãn chính <span class="required">*</span></label><div class="choices"><label class="choice"><input type="radio" name="i2i_label" value="1" required> Match (1)</label><label class="choice"><input type="radio" name="i2i_label" value="0"> Mismatch (0)</label><label class="choice"><input type="radio" name="i2i_label" value="UND"> UND</label></div><label for="i2i_group">Nhóm chẩn đoán</label><select id="i2i_group"><option value="">Không áp dụng / Match</option></select></section></div>
<section class="card"><label class="choice"><input id="ambiguous" type="checkbox"> Ambiguous — có từ hai nhãn có cơ sở ngang nhau hoặc thiếu ngữ cảnh thiết yếu</label><label for="reason">Lý do ngắn <span class="required" id="reasonMark">*</span></label><textarea id="reason" placeholder="Bắt buộc cho N5, N6, M5, M6 hoặc mẫu ambiguous."></textarea><p id="error" class="error"></p><div class="actions"><button type="button" class="secondary" onclick="skip()">Bỏ qua tạm thời</button><button id="submit" type="submit">Lưu &amp; sang mẫu tiếp</button></div></section></form></section></main>
<script>
const T2T = %T2T%; const I2I = %I2I%; let annotator='', unit=null;
function esc(s){return String(s||'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
function fill(sel, items){const el=document.querySelector(sel); Object.entries(items).forEach(([k,v])=>el.insertAdjacentHTML('beforeend',`<option value="${k}">${k} — ${esc(v)}</option>`));}
fill('#t2t_group',T2T);fill('#i2i_group',I2I);
async function start(){annotator=document.querySelector('#annotator').value.trim();const err=document.querySelector('#loginError');if(!annotator){err.textContent='Hãy nhập tên hoặc mã người gán.';return} const r=await fetch('/api/next?annotator='+encodeURIComponent(annotator));if(!r.ok){err.textContent=(await r.json()).error||'Không thể mở phiên.';return} document.querySelector('#login').classList.add('hidden');document.querySelector('#work').classList.remove('hidden');document.querySelector('#who').textContent='Người gán: '+annotator;load(await r.json())}
function logout(){location.reload()}
function load(data){unit=data.unit;document.querySelector('#progress').textContent=`Tiến độ: ${data.done}/${data.total} ảnh review`;document.querySelector('#unitMeta').textContent=unit?`Review ${unit.review_id} · ảnh ${unit.image_index+1}`:'';document.querySelector('#empty').classList.toggle('hidden',!!unit);document.querySelector('#form').classList.toggle('hidden',!unit);if(!unit)return;document.querySelector('#form').reset();document.querySelector('#error').textContent='';document.querySelector('#product').textContent=unit.product_name||'(Không có tên sản phẩm)';document.querySelector('#description').textContent=unit.product_description||'(Không có mô tả)';document.querySelector('#comment').textContent=unit.comment||'(Không có văn bản review)';const ri=document.querySelector('#reviewImage');ri.src=unit.review_image_url||'';ri.classList.toggle('hidden',!unit.review_image_url);document.querySelector('#missingImage').classList.toggle('hidden',!!unit.review_image_url);document.querySelector('#productImages').innerHTML=(unit.product_image_urls||[]).map((u,i)=>`<img src="${u}" alt="Ảnh sản phẩm ${i+1}">`).join('')||'<span class="meta">Không có ảnh sản phẩm cục bộ.</span>'}
function chosen(n){return document.querySelector(`input[name="${n}"]:checked`)?.value||''}
function needsReason(){const a=document.querySelector('#ambiguous').checked;return a||['N5','N6'].includes(document.querySelector('#t2t_group').value)||['M5','M6'].includes(document.querySelector('#i2i_group').value)}
async function save(e){e.preventDefault();const reason=document.querySelector('#reason').value.trim();if(needsReason()&&!reason){document.querySelector('#error').textContent='Trường hợp này cần ghi lý do ngắn dựa trên bằng chứng quan sát được.';return}const payload={annotator,item_id:unit.item_id,subset:unit.subset,review_id:unit.review_id,image_index:unit.image_index,product_id:unit.product_id,t2t_label:chosen('t2t_label'),t2t_diagnostic_group:document.querySelector('#t2t_group').value,i2i_label:chosen('i2i_label'),i2i_diagnostic_group:document.querySelector('#i2i_group').value,ambiguous:document.querySelector('#ambiguous').checked,reason};const b=document.querySelector('#submit');b.disabled=true;const r=await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});b.disabled=false;if(!r.ok){document.querySelector('#error').textContent=(await r.json()).error||'Không lưu được.';return}load(await r.json())}
async function skip(){const r=await fetch('/api/next?annotator='+encodeURIComponent(annotator)+'&offset=1');load(await r.json())}
</script></body></html>'''.replace("%T2T%", json.dumps(T2T_GROUPS, ensure_ascii=False)).replace("%I2I%", json.dumps(I2I_GROUPS, ensure_ascii=False))


class App(BaseHTTPRequestHandler):
    units: list[dict] = []

    def log_message(self, format: str, *args: object) -> None:
        return  # avoid noisy per-image HTTP logging

    def respond_json(self, status: int, payload: dict) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def get_next(self, annotator: str, offset: int = 0) -> dict:
        done = completed_ids(annotator)
        remaining = [unit for unit in self.units if unit["item_id"] not in done]
        unit = remaining[offset] if len(remaining) > offset else None
        return {"done": len(done & {u['item_id'] for u in self.units}), "total": len(self.units), "unit": public_unit(unit) if unit else None}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = html_page().encode("utf-8")
            self.send_response(HTTPStatus.OK); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
        if parsed.path == "/api/next":
            query = parse_qs(parsed.query)
            try:
                name = query.get("annotator", [""])[0]
                offset = max(0, int(query.get("offset", ["0"])[0]))
                self.respond_json(200, self.get_next(name, offset))
            except (ValueError, TypeError) as exc:
                self.respond_json(400, {"error": str(exc)})
            return
        if parsed.path == "/image":
            relative = unquote(parse_qs(parsed.query).get("path", [""])[0])
            try:
                image = (DATA_ROOT / relative).resolve(); image.relative_to(DATA_ROOT.resolve())
                if not image.is_file(): raise FileNotFoundError
                payload = image.read_bytes(); mime = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
                self.send_response(200); self.send_header("Content-Type", mime); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)
            except (ValueError, OSError, FileNotFoundError):
                self.send_error(404, "Image not found")
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path != "/api/save": self.send_error(404); return
        try:
            size = int(self.headers.get("Content-Length", "0")); payload = json.loads(self.rfile.read(size).decode("utf-8"))
            annotator = safe_annotator(str(payload.get("annotator", "")))
            valid_ids = {unit["item_id"] for unit in self.units}
            if payload.get("item_id") not in valid_ids: raise ValueError("Mẫu không thuộc phiên gán nhãn này.")
            t2t_label = payload.get("t2t_label")
            group_t2t = payload.get("t2t_diagnostic_group")
            if t2t_label not in {"0", "1"}: raise ValueError("Thiếu nhãn T2T.")
            if group_t2t not in T2T_GROUPS: raise ValueError("Thiếu nhóm T2T.")
            if t2t_label == "1" and group_t2t not in {"R1", "R2", "R3", "R4"}: raise ValueError("Relevant chỉ đi với nhóm R1–R4.")
            if t2t_label == "0" and group_t2t not in {"N1", "N2", "N3", "N4", "N5", "N6"}: raise ValueError("Irrelevant chỉ đi với nhóm N1–N6.")
            if payload.get("i2i_label") not in {"0", "1", "UND"}: raise ValueError("Thiếu nhãn I2I.")
            group_i2i = payload.get("i2i_diagnostic_group", "")
            if group_i2i and group_i2i not in I2I_GROUPS: raise ValueError("Nhóm I2I không hợp lệ.")
            if payload["i2i_label"] == "1" and group_i2i: raise ValueError("Match không có nhóm M.")
            if payload["i2i_label"] == "0" and group_i2i not in {"M2", "M3", "M4", "M5", "M6"}: raise ValueError("Mismatch cần một nhóm M2–M6.")
            if payload["i2i_label"] == "UND" and group_i2i not in {"M1", "M3", "M4"}: raise ValueError("UND cần nhóm M1, M3 hoặc M4.")
            required_reason = bool(payload.get("ambiguous")) or payload["t2t_diagnostic_group"] in {"N5", "N6"} or group_i2i in {"M5", "M6"}
            if required_reason and not str(payload.get("reason", "")).strip(): raise ValueError("Mẫu này bắt buộc có lý do.")
            record = {key: payload.get(key) for key in ("item_id", "subset", "review_id", "image_index", "product_id", "t2t_label", "t2t_diagnostic_group", "i2i_label", "i2i_diagnostic_group", "ambiguous", "reason")}
            record.update({"annotator": annotator, "saved_at_utc": datetime.now(timezone.utc).isoformat()})
            STORE_ROOT.mkdir(parents=True, exist_ok=True)
            with LOCK, annotation_file(annotator).open("a", encoding="utf-8") as handle: handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.respond_json(200, self.get_next(annotator))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.respond_json(400, {"error": str(exc)})


def main() -> None:
    parser = argparse.ArgumentParser(description="ViRPM blind annotation app")
    parser.add_argument("--input", default="artifacts/splits/core.csv", help="CSV or JSON annotation source")
    parser.add_argument("--subset", default="core-1000", help="Subset name saved in annotation records")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1", help="127.0.0.1 for this PC; 0.0.0.0 for LAN access")
    args = parser.parse_args()
    source = (ROOT / args.input).resolve() if not Path(args.input).is_absolute() else Path(args.input)
    if not source.is_file(): parser.error(f"Input file not found: {source}")
    App.units = load_rows(source, args.subset)
    if not App.units: parser.error("No review-image annotation units found in the input.")
    server = ThreadingHTTPServer((args.host, args.port), App)
    shown_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    print(f"ViRPM annotation app: http://{shown_host}:{args.port}")
    if args.host == "0.0.0.0":
        print("LAN mode enabled. Share this PC's IPv4 address with annotators, e.g. http://<IPv4>:8765")
    print(f"Input: {source} | units (review images): {len(App.units)} | subset: {args.subset}")
    print(f"Annotations: {STORE_ROOT}")
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nStopped.")
    finally: server.server_close()


if __name__ == "__main__":
    main()
