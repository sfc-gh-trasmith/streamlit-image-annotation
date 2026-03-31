import os
import json
import random
import shutil
import base64
import datetime
from glob import glob
from io import BytesIO
from pathlib import Path
from collections import Counter

import yaml
import streamlit as st
from PIL import Image, ImageDraw

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(APP_DIR)
IMAGES_DIR = os.path.join(PROJECT_ROOT, "images")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
ANNOTATIONS_DIR = os.path.join(OUTPUT_DIR, "annotations")
ANNOTATED_DIR = os.path.join(OUTPUT_DIR, "annotated")
EXPORTS_DIR = os.path.join(OUTPUT_DIR, "exports")
CONFIG_PATH = os.path.join(OUTPUT_DIR, "config.json")
CANVAS_MAX_WIDTH = 960
DEFAULT_LABELS = ["plane", "terminal", "car"]
COLOR_PALETTE = [
    "#00C853",
    "#2196F3",
    "#FF9800",
    "#E91E63",
    "#9C27B0",
    "#00BCD4",
    "#CDDC39",
    "#FF5722",
    "#795548",
    "#607D8B",
]

st.set_page_config(page_title="Image Annotation Tool", layout="wide")

st.markdown(
    """
<style>
html, body, [data-testid="stAppViewContainer"] { margin: 0 !important; padding: 0 !important; }
.block-container { margin: 0 !important; max-width: 100% !important; padding: 1.5rem 1rem 0 5rem !important; }
header[data-testid="stHeader"] { display: none !important; }
#MainMenu { display: none !important; }
footer { display: none !important; }
.appview-container .main .block-container { padding-top: 1.5rem !important; margin-top: 0 !important; padding-left: 5rem !important; }
h3 { white-space: nowrap; overflow: visible; margin-top: 0 !important; padding-top: 0 !important; }
section[data-testid="stSidebar"] > div:first-child { padding-top: 0 !important; margin-top: -3rem !important; }
[data-testid="stSidebar"] { min-width: 320px; max-width: 360px; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.3rem; }
[data-testid="stVerticalBlock"] { gap: 0.4rem; }
.stat-box {
    background: #1a1a2e; border: 1px solid #333; border-radius: 8px;
    padding: 10px 14px; text-align: center;
}
.stat-box .num  { font-size: 1.6rem; font-weight: 700; color: #00C853; }
.stat-box .lbl  { font-size: 0.7rem; color: #888; text-transform: uppercase; letter-spacing: 1px; }
.pill {
    display: inline-block; padding: 2px 10px; border-radius: 10px;
    font-size: 0.72rem; font-weight: 600; margin-left: 6px; vertical-align: middle;
}
.pill-yes { background: #4A6FA5; color: #fff; }
.pill-no  { background: #1B2A4A; color: #fff; }
[data-testid="stSidebar"] button[kind="primary"] { background-color: #4A6FA5 !important; border-color: #4A6FA5 !important; color: #fff !important; }
[data-testid="stSidebar"] button[kind="secondary"] { background-color: #1B2A4A !important; border-color: #1B2A4A !important; color: #fff !important; }
</style>
""",
    unsafe_allow_html=True,
)

for d in [IMAGES_DIR, ANNOTATIONS_DIR, ANNOTATED_DIR, EXPORTS_DIR]:
    os.makedirs(d, exist_ok=True)


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {"labels": DEFAULT_LABELS, "splits": {}}


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def get_label_colors(labels):
    colors = {}
    for i, label in enumerate(labels):
        colors[label] = COLOR_PALETTE[i % len(COLOR_PALETTE)]
    return colors


def get_image_list():
    exts = ("*.png", "*.jpg", "*.jpeg", "*.bmp", "*.tiff")
    files = []
    for ext in exts:
        files.extend(glob(os.path.join(IMAGES_DIR, ext)))
    return sorted(files)


def annotation_path(image_path):
    return os.path.join(ANNOTATIONS_DIR, f"{Path(image_path).stem}.json")


def load_annotation(image_path):
    p = annotation_path(image_path)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {"image": os.path.basename(image_path), "annotations": []}


def save_annotation(image_path, annotations, label_colors):
    img = Image.open(image_path)
    data = {
        "image": os.path.basename(image_path),
        "image_width": img.width,
        "image_height": img.height,
        "annotations": annotations,
        "saved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    with open(annotation_path(image_path), "w") as f:
        json.dump(data, f, indent=2)

    annotated = img.copy().convert("RGBA")
    overlay = Image.new("RGBA", annotated.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for ann in annotations:
        c = label_colors.get(ann.get("label", ""), "#00C853")
        r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
        if ann.get("type") == "bbox":
            x1, y1, x2, y2 = ann["x1"], ann["y1"], ann["x2"], ann["y2"]
            draw.rectangle(
                [x1, y1, x2, y2], fill=(r, g, b, 50), outline=(r, g, b, 255), width=2
            )
            draw.text((x1 + 4, y1 - 14), ann.get("label", ""), fill=(r, g, b, 255))
        else:
            pts = ann.get("points", [])
            if len(pts) < 3:
                continue
            coords = [(p[0], p[1]) for p in pts]
            draw.polygon(coords, fill=(r, g, b, 50), outline=(r, g, b, 255))
            draw.text(
                (coords[0][0] + 4, coords[0][1] - 14),
                ann.get("label", ""),
                fill=(r, g, b, 255),
            )
    annotated = Image.alpha_composite(annotated, overlay).convert("RGB")
    annotated.save(os.path.join(ANNOTATED_DIR, os.path.basename(image_path)))


def image_to_data_uri(image_path, max_w):
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    scale = min(max_w / w, 1.0)
    new_w, new_h = int(w * scale), int(h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}", new_w, new_h, scale


def export_coco(image_list, config, label_colors):
    categories = []
    label_to_id = {}
    for i, label in enumerate(config["labels"]):
        cat_id = i + 1
        categories.append({"id": cat_id, "name": label, "supercategory": "none"})
        label_to_id[label] = cat_id

    images = []
    coco_annotations = []
    ann_id = 1

    for img_id, img_path in enumerate(image_list, start=1):
        ann_data = load_annotation(img_path)
        img_w = ann_data.get("image_width")
        img_h = ann_data.get("image_height")
        if img_w is None or img_h is None:
            img = Image.open(img_path)
            img_w, img_h = img.size

        split = config.get("splits", {}).get(os.path.basename(img_path), "train")
        images.append(
            {
                "id": img_id,
                "file_name": os.path.basename(img_path),
                "width": img_w,
                "height": img_h,
                "split": split,
            }
        )

        for ann in ann_data.get("annotations", []):
            cat_id = label_to_id.get(ann.get("label"), 1)
            if ann.get("type") == "bbox":
                x1, y1, x2, y2 = ann["x1"], ann["y1"], ann["x2"], ann["y2"]
                w = x2 - x1
                h = y2 - y1
                bbox = [x1, y1, w, h]
                area = w * h
                seg = [[x1, y1, x2, y1, x2, y2, x1, y2]]
            else:
                pts = ann.get("points", [])
                if len(pts) < 3:
                    continue
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                x_min, x_max = min(xs), max(xs)
                y_min, y_max = min(ys), max(ys)
                bbox = [x_min, y_min, x_max - x_min, y_max - y_min]
                area = (x_max - x_min) * (y_max - y_min)
                seg = [[coord for p in pts for coord in p]]

            coco_annotations.append(
                {
                    "id": ann_id,
                    "image_id": img_id,
                    "category_id": cat_id,
                    "bbox": bbox,
                    "area": area,
                    "segmentation": seg,
                    "iscrowd": 0,
                }
            )
            ann_id += 1

    coco = {
        "info": {
            "description": "Exported from Image Annotation Tool",
            "date_created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
        "images": images,
        "annotations": coco_annotations,
        "categories": categories,
    }

    out_path = os.path.join(EXPORTS_DIR, "coco_annotations.json")
    with open(out_path, "w") as f:
        json.dump(coco, f, indent=2)
    return out_path


def export_yolo(image_list, config, label_colors):
    label_to_id = {label: i for i, label in enumerate(config["labels"])}
    yolo_dir = os.path.join(EXPORTS_DIR, "yolo")
    for split in ["train", "val", "test"]:
        os.makedirs(os.path.join(yolo_dir, "labels", split), exist_ok=True)
        os.makedirs(os.path.join(yolo_dir, "images", split), exist_ok=True)

    for img_path in image_list:
        ann_data = load_annotation(img_path)
        img_w = ann_data.get("image_width")
        img_h = ann_data.get("image_height")
        if img_w is None or img_h is None:
            img = Image.open(img_path)
            img_w, img_h = img.size

        basename = os.path.basename(img_path)
        split = config.get("splits", {}).get(basename, "train")
        stem = Path(img_path).stem

        shutil.copy2(img_path, os.path.join(yolo_dir, "images", split, basename))

        lines = []
        for ann in ann_data.get("annotations", []):
            cls_id = label_to_id.get(ann.get("label"), 0)
            if ann.get("type") == "bbox":
                x1, y1, x2, y2 = ann["x1"], ann["y1"], ann["x2"], ann["y2"]
            else:
                pts = ann.get("points", [])
                if len(pts) < 3:
                    continue
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                x1, y1 = min(xs), min(ys)
                x2, y2 = max(xs), max(ys)

            cx = ((x1 + x2) / 2) / img_w
            cy = ((y1 + y2) / 2) / img_h
            bw = (x2 - x1) / img_w
            bh = (y2 - y1) / img_h
            lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")

        label_path = os.path.join(yolo_dir, "labels", split, f"{stem}.txt")
        with open(label_path, "w") as f:
            f.write("\n".join(lines))

    data_yaml = {
        "path": yolo_dir,
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": {i: name for i, name in enumerate(config["labels"])},
    }
    yaml_path = os.path.join(yolo_dir, "data.yaml")
    with open(yaml_path, "w") as f:
        yaml.dump(data_yaml, f, default_flow_style=False)
    return yolo_dir


def auto_split(image_list, train_pct, val_pct):
    names = [os.path.basename(p) for p in image_list]
    random.shuffle(names)
    n = len(names)
    n_train = max(1, int(n * train_pct / 100))
    n_val = max(0, int(n * val_pct / 100))
    splits = {}
    for i, name in enumerate(names):
        if i < n_train:
            splits[name] = "train"
        elif i < n_train + n_val:
            splits[name] = "val"
        else:
            splits[name] = "test"
    return splits


CANVAS_HTML = '<div id="root"><canvas id="c"></canvas></div>'

CANVAS_CSS = """
#root { position: relative; display: inline-block; }
#c { display: block; cursor: crosshair; border: 2px solid #444; border-radius: 6px; }
.toolbar { display: flex; gap: 6px; margin-top: 8px; align-items: center; flex-wrap: wrap; }
.toolbar button {
    padding: 5px 14px; border-radius: 4px; cursor: pointer;
    font-size: 12px; font-weight: 500; border: 1px solid #555;
    background: #2a2a3e; color: #ddd;
}
.toolbar button.green { border-color: #4A6FA5; background: #4A6FA5; color: #fff; font-weight: 700; }
.toolbar button.red { border-color: #1B2A4A; background: #1B2A4A; color: #fff; }
.toolbar button.outline-red { border-color: #1B2A4A; background: transparent; color: #8FA3C4; }
.toolbar .status { color: #888; font-size: 11px; margin-left: 6px; }
.mode-indicator {
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 11px; font-weight: 700; margin-left: 6px;
}
.mode-poly { background: #00C853; color: #000; }
.mode-bbox { background: #2196F3; color: #fff; }
"""

CANVAS_JS = """
export default function(component) {
  const { data, parentElement, setTriggerValue } = component;
  if (!data) return;

  const root = parentElement.querySelector("#root");
  if (!root) return;

  const COLOR = data.color || "#00C853";
  const LABEL_COLORS = data.label_colors || {};
  root.__currentLabel = data.label || "plane";
  const SCALE = data.scale || 1;
  const canvasW = data.canvas_w || 800;
  const canvasH = data.canvas_h || 600;
  const DRAW_MODE = data.draw_mode || "polygon";

  let canvas = root.querySelector("#c");
  canvas.width = canvasW;
  canvas.height = canvasH;
  const ctx = canvas.getContext("2d");

  if (!root.querySelector(".toolbar")) {
    const tb = document.createElement("div");
    tb.className = "toolbar";
    tb.innerHTML = `
      <button id="btnUndo">Undo Point</button>
      <button id="btnClose" class="green">Close Polygon</button>
      <button id="btnDelete" class="red">Delete Last</button>
      <button id="btnClear" class="outline-red">Clear All</button>
      <button id="btnSave" class="green">Save</button>
      <span class="status" id="status"></span>
    `;
    root.appendChild(tb);
  }

  const btnClose = root.querySelector("#btnClose");
  const btnUndo = root.querySelector("#btnUndo");
  if (DRAW_MODE === "bbox") {
    btnClose.style.display = "none";
    btnUndo.style.display = "none";
  } else {
    btnClose.style.display = "";
    btnUndo.style.display = "";
  }

  const img = new window.Image();
  let annotations = root.__annotations || JSON.parse(JSON.stringify(data.annotations || []));
  let currentPoints = root.__currentPoints || [];
  let mousePos = root.__mousePos || null;
  let bboxStart = root.__bboxStart || null;
  let bboxDragging = root.__bboxDragging || false;
  root.__annotations = annotations;
  root.__currentPoints = currentPoints;
  root.__mousePos = mousePos;

  function draw() {
    ctx.clearRect(0, 0, canvasW, canvasH);
    ctx.drawImage(img, 0, 0, canvasW, canvasH);

    annotations.forEach(function(ann, ai) {
      const ac = LABEL_COLORS[ann.label] || COLOR;
      const af = ac + "30";

      if (ann.type === "bbox") {
        const sx = ann.x1 * SCALE, sy = ann.y1 * SCALE;
        const ex = ann.x2 * SCALE, ey = ann.y2 * SCALE;
        ctx.fillStyle = af;
        ctx.fillRect(sx, sy, ex - sx, ey - sy);
        ctx.strokeStyle = ac;
        ctx.lineWidth = 2;
        ctx.strokeRect(sx, sy, ex - sx, ey - sy);
        ctx.font = "bold 12px sans-serif";
        ctx.fillStyle = ac;
        ctx.fillText(ann.label + " #" + (ai+1), sx + 4, sy - 6);
      } else {
        const pts = ann.points;
        if (pts.length < 2) return;
        ctx.beginPath();
        ctx.moveTo(pts[0][0] * SCALE, pts[0][1] * SCALE);
        for (let i = 1; i < pts.length; i++)
          ctx.lineTo(pts[i][0] * SCALE, pts[i][1] * SCALE);
        ctx.closePath();
        ctx.fillStyle = af;
        ctx.fill();
        ctx.strokeStyle = ac;
        ctx.lineWidth = 2;
        ctx.stroke();
        pts.forEach(function(p) {
          ctx.beginPath();
          ctx.arc(p[0]*SCALE, p[1]*SCALE, 4, 0, Math.PI*2);
          ctx.fillStyle = ac;
          ctx.fill();
        });
        ctx.font = "bold 12px sans-serif";
        ctx.fillStyle = ac;
        ctx.fillText(ann.label + " #" + (ai+1), pts[0][0]*SCALE + 6, pts[0][1]*SCALE - 6);
      }
    });

    if (DRAW_MODE === "polygon" && currentPoints.length > 0) {
      ctx.beginPath();
      ctx.moveTo(currentPoints[0][0]*SCALE, currentPoints[0][1]*SCALE);
      for (let i = 1; i < currentPoints.length; i++)
        ctx.lineTo(currentPoints[i][0]*SCALE, currentPoints[i][1]*SCALE);
      if (mousePos) ctx.lineTo(mousePos[0], mousePos[1]);
      ctx.strokeStyle = "#FFEB3B";
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 3]);
      ctx.stroke();
      ctx.setLineDash([]);
      currentPoints.forEach(function(p, i) {
        ctx.beginPath();
        ctx.arc(p[0]*SCALE, p[1]*SCALE, i === 0 ? 7 : 4, 0, Math.PI*2);
        ctx.fillStyle = i === 0 ? "#FFEB3B" : "#fff";
        ctx.fill();
        ctx.strokeStyle = "#333";
        ctx.lineWidth = 1;
        ctx.stroke();
      });
    }

    if (DRAW_MODE === "bbox" && bboxStart && mousePos) {
      const sx = bboxStart[0], sy = bboxStart[1];
      const mx = mousePos[0], my = mousePos[1];
      ctx.strokeStyle = "#FFEB3B";
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 3]);
      ctx.strokeRect(sx, sy, mx - sx, my - sy);
      ctx.setLineDash([]);
      ctx.fillStyle = "#FFEB3B30";
      ctx.fillRect(sx, sy, mx - sx, my - sy);
    }

    const s = root.querySelector("#status");
    if (s) {
      if (DRAW_MODE === "bbox") {
        s.textContent = (bboxStart ? "Release to finish box" : annotations.length + " annotation(s) — click & drag to draw box");
      } else {
        s.textContent = currentPoints.length > 0
          ? currentPoints.length + " pts — click near start to close"
          : annotations.length + " annotation(s)";
      }
    }
  }

  function closePolygon() {
    if (currentPoints.length >= 3) {
      annotations.push({ type: "polygon", label: root.__currentLabel || "plane", points: currentPoints.slice() });
      currentPoints.length = 0;
      root.__currentPoints = currentPoints;
      draw();
    }
  }

  if (!root.__listenersAttached) {
    root.__listenersAttached = true;

    canvas.addEventListener("mousedown", function(e) {
      if (DRAW_MODE !== "bbox") return;
      const rect = canvas.getBoundingClientRect();
      bboxStart = [e.clientX - rect.left, e.clientY - rect.top];
      bboxDragging = true;
      root.__bboxStart = bboxStart;
      root.__bboxDragging = bboxDragging;
    });

    canvas.addEventListener("mouseup", function(e) {
      if (DRAW_MODE !== "bbox" || !bboxDragging || !bboxStart) return;
      const rect = canvas.getBoundingClientRect();
      const ex = e.clientX - rect.left;
      const ey = e.clientY - rect.top;
      const x1 = Math.min(bboxStart[0], ex) / SCALE;
      const y1 = Math.min(bboxStart[1], ey) / SCALE;
      const x2 = Math.max(bboxStart[0], ex) / SCALE;
      const y2 = Math.max(bboxStart[1], ey) / SCALE;
      if (Math.abs(x2 - x1) > 5 && Math.abs(y2 - y1) > 5) {
        annotations.push({
          type: "bbox",
          label: root.__currentLabel || "plane",
          x1: parseFloat(x1.toFixed(1)),
          y1: parseFloat(y1.toFixed(1)),
          x2: parseFloat(x2.toFixed(1)),
          y2: parseFloat(y2.toFixed(1)),
        });
      }
      bboxStart = null;
      bboxDragging = false;
      root.__bboxStart = null;
      root.__bboxDragging = false;
      draw();
    });

    canvas.addEventListener("click", function(e) {
      if (DRAW_MODE !== "polygon") return;
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const realX = parseFloat((x / SCALE).toFixed(1));
      const realY = parseFloat((y / SCALE).toFixed(1));
      if (currentPoints.length >= 3) {
        const sx = currentPoints[0][0]*SCALE, sy = currentPoints[0][1]*SCALE;
        if (Math.hypot(x - sx, y - sy) < 15) {
          closePolygon();
          return;
        }
      }
      currentPoints.push([realX, realY]);
      root.__currentPoints = currentPoints;
      draw();
    });

    canvas.addEventListener("mousemove", function(e) {
      const rect = canvas.getBoundingClientRect();
      mousePos = [e.clientX - rect.left, e.clientY - rect.top];
      root.__mousePos = mousePos;
      if (DRAW_MODE === "polygon" && currentPoints.length > 0) draw();
      if (DRAW_MODE === "bbox" && bboxDragging && bboxStart) draw();
    });

    root.querySelector("#btnUndo").addEventListener("click", function() {
      if (currentPoints.length > 0) { currentPoints.pop(); draw(); }
    });
    root.querySelector("#btnClose").addEventListener("click", closePolygon);
    root.querySelector("#btnDelete").addEventListener("click", function() {
      if (annotations.length > 0) { annotations.pop(); draw(); }
    });
    root.querySelector("#btnClear").addEventListener("click", function() {
      annotations.length = 0; currentPoints.length = 0;
      bboxStart = null; bboxDragging = false;
      root.__bboxStart = null; root.__bboxDragging = false;
      draw();
    });
    root.querySelector("#btnSave").addEventListener("click", function() {
      setTriggerValue("saved", JSON.stringify(annotations));
    });

    parentElement.addEventListener("keydown", function(e) {
      if (e.key === "Escape") {
        currentPoints.length = 0; root.__currentPoints = currentPoints;
        bboxStart = null; bboxDragging = false;
        root.__bboxStart = null; root.__bboxDragging = false;
        draw();
      }
      if (e.key === "z" && (e.ctrlKey || e.metaKey) && currentPoints.length > 0) {
        currentPoints.pop(); draw();
      }
    });
  }

  img.onload = draw;
  img.src = data.image_uri;
}
"""

_annotation_canvas = st.components.v2.component(
    "annotation_canvas",
    html=CANVAS_HTML,
    css=CANVAS_CSS,
    js=CANVAS_JS,
)


def annotation_canvas(
    image_uri,
    canvas_w,
    canvas_h,
    scale,
    annotations,
    color,
    label,
    draw_mode,
    label_colors,
    key,
):
    result = _annotation_canvas(
        data={
            "image_uri": image_uri,
            "canvas_w": canvas_w,
            "canvas_h": canvas_h,
            "scale": scale,
            "annotations": annotations,
            "color": color,
            "label": label,
            "draw_mode": draw_mode,
            "label_colors": label_colors,
        },
        key=key,
        height=canvas_h + 60,
        on_saved_change=lambda: None,
    )
    return result


config = load_config()
if "labels" not in config:
    config["labels"] = DEFAULT_LABELS
if "splits" not in config:
    config["splits"] = {}
label_colors = get_label_colors(config["labels"])

image_list = get_image_list()

with st.sidebar:
    st.markdown("# Annotation Tool")
    st.caption("Object Detection Annotation")
    st.divider()

    uploaded = st.file_uploader(
        "Upload Images",
        type=["png", "jpg", "jpeg", "bmp", "tiff"],
        accept_multiple_files=True,
    )
    if uploaded:
        for uf in uploaded:
            dest = os.path.join(IMAGES_DIR, uf.name)
            if not os.path.exists(dest):
                with open(dest, "wb") as f:
                    f.write(uf.getbuffer())
        st.toast(f"Uploaded {len(uploaded)} image(s)")
        st.rerun()

    image_list = get_image_list()
    if not image_list:
        st.error(f"No images in `{IMAGES_DIR}`")
        st.stop()

    filter_mode = st.selectbox(
        "Filter", ["All", "Labeled", "Unlabeled"], key="filter_mode"
    )
    if filter_mode == "Labeled":
        image_list = [
            p
            for p in image_list
            if os.path.exists(annotation_path(p))
            and len(load_annotation(p).get("annotations", [])) > 0
        ]
    elif filter_mode == "Unlabeled":
        image_list = [
            p
            for p in image_list
            if not os.path.exists(annotation_path(p))
            or len(load_annotation(p).get("annotations", [])) == 0
        ]

    if not image_list:
        st.info("No images match filter.")
        st.stop()

    if "current_idx" not in st.session_state:
        st.session_state.current_idx = 0
    if st.session_state.current_idx >= len(image_list):
        st.session_state.current_idx = 0
    idx = st.session_state.current_idx

    image_names = [os.path.basename(p) for p in image_list]
    selected_image = st.selectbox("Image", image_names, index=idx, key="image_selector")
    new_idx = image_names.index(selected_image)
    if new_idx != idx:
        st.session_state.current_idx = new_idx
        st.rerun()

    st.divider()
    draw_mode = st.radio(
        "Draw Mode", ["polygon", "bbox"], horizontal=True, key="draw_mode"
    )
    selected_label = st.selectbox("Label Class", config["labels"])
    st.divider()

    with st.expander("Manage Labels"):
        new_label = st.text_input("Add label", key="new_label_input")
        if st.button("Add", key="add_label_btn") and new_label.strip():
            nl = new_label.strip().lower()
            if nl not in config["labels"]:
                config["labels"].append(nl)
                save_config(config)
                st.rerun()
        if len(config["labels"]) > 1:
            remove_label = st.selectbox(
                "Remove label", config["labels"], key="remove_label_sel"
            )
            if st.button("Remove", key="remove_label_btn"):
                config["labels"].remove(remove_label)
                save_config(config)
                st.rerun()

    st.divider()

    current_image = image_list[idx]
    img_basename = os.path.basename(current_image)
    current_split = config["splits"].get(img_basename, "train")
    new_split = st.selectbox(
        "Split",
        ["train", "val", "test"],
        index=["train", "val", "test"].index(current_split),
        key="split_sel",
    )
    if new_split != current_split:
        config["splits"][img_basename] = new_split
        save_config(config)

    with st.expander("Auto-Split All"):
        tc, vc = st.columns(2)
        with tc:
            train_pct = st.number_input("Train %", 10, 90, 70, key="train_pct")
        with vc:
            val_pct = st.number_input("Val %", 5, 50, 20, key="val_pct")
        if st.button("Auto-Split", key="auto_split_btn"):
            all_images = get_image_list()
            config["splits"] = auto_split(all_images, train_pct, val_pct)
            save_config(config)
            st.toast("Auto-split complete")
            st.rerun()

    st.divider()

    with st.expander("Export"):
        if st.button("Export COCO JSON", key="export_coco"):
            all_images = get_image_list()
            out = export_coco(all_images, config, label_colors)
            st.success(f"Saved to `{out}`")

        if st.button("Export YOLO", key="export_yolo"):
            all_images = get_image_list()
            out = export_yolo(all_images, config, label_colors)
            st.success(f"Saved to `{out}`")

    st.divider()

    with st.expander("Class Distribution"):
        all_images_full = get_image_list()
        class_counts = Counter()
        type_counts = Counter()
        split_counts = Counter()
        for ip in all_images_full:
            ad = load_annotation(ip)
            bn = os.path.basename(ip)
            split_counts[config["splits"].get(bn, "train")] += 1
            for a in ad.get("annotations", []):
                class_counts[a.get("label", "unknown")] += 1
                type_counts[a.get("type", "polygon")] += 1
        if class_counts:
            for label, count in class_counts.most_common():
                c = label_colors.get(label, "#888")
                st.markdown(
                    f"<span style='color:{c};font-weight:700'>{label}</span>: {count}",
                    unsafe_allow_html=True,
                )
            st.caption(
                f"Polygons: {type_counts.get('polygon', 0)} | Boxes: {type_counts.get('bbox', 0)}"
            )
        else:
            st.caption("No annotations yet")
        if split_counts:
            st.caption(
                f"Train: {split_counts.get('train', 0)} | Val: {split_counts.get('val', 0)} | Test: {split_counts.get('test', 0)}"
            )

    st.divider()
    st.markdown("**Shortcuts**")
    if draw_mode == "polygon":
        st.markdown(
            "- **Click** add vertex\n- **Click near start** close\n- **Esc** cancel\n- **Ctrl+Z** undo"
        )
    else:
        st.markdown("- **Click+drag** draw box\n- **Esc** cancel")

label_colors = get_label_colors(config["labels"])
current_image = image_list[idx]
img_name = os.path.basename(current_image)
annotation = load_annotation(current_image)
has_annotation = len(annotation.get("annotations", [])) > 0

hdr_l, hdr_r = st.columns([3, 1])
with hdr_l:
    st.markdown(f"### {img_name}", unsafe_allow_html=True)
with hdr_r:
    st.caption(f"Image {idx + 1} / {len(image_list)}")

n1, n2, n3, n4 = st.columns(4)
with n1:
    if st.button("\u23ee First", use_container_width=True, disabled=idx == 0):
        st.session_state.current_idx = 0
        st.rerun()
with n2:
    if st.button("\u25c0 Prev", use_container_width=True, disabled=idx == 0):
        st.session_state.current_idx = idx - 1
        st.rerun()
with n3:
    if st.button(
        "Next \u25b6", use_container_width=True, disabled=idx >= len(image_list) - 1
    ):
        st.session_state.current_idx = idx + 1
        st.rerun()
with n4:
    if st.button(
        "Last \u23ed", use_container_width=True, disabled=idx >= len(image_list) - 1
    ):
        st.session_state.current_idx = len(image_list) - 1
        st.rerun()

data_uri, canvas_w, canvas_h, scale = image_to_data_uri(current_image, CANVAS_MAX_WIDTH)
color = label_colors.get(selected_label, "#00C853")

result = annotation_canvas(
    image_uri=data_uri,
    canvas_w=canvas_w,
    canvas_h=canvas_h,
    scale=scale,
    annotations=annotation.get("annotations", []),
    color=color,
    label=selected_label,
    draw_mode=draw_mode,
    label_colors=label_colors,
    key=f"canvas_{img_name}_{draw_mode}",
)

if result and result.saved:
    try:
        anns = json.loads(result.saved)
    except (json.JSONDecodeError, TypeError):
        anns = []
    save_annotation(current_image, anns, label_colors)
    st.toast(f"Saved {len(anns)} annotation(s) for {img_name}", icon="\u2705")
    st.rerun()

col1, _, _ = st.columns([1, 1, 4])
with col1:
    if st.button("\U0001f5d1\ufe0f Clear Annotations", use_container_width=True):
        save_annotation(current_image, [], label_colors)
        st.rerun()

if has_annotation:
    with st.expander(
        f"Saved annotations ({len(annotation['annotations'])} items)", expanded=False
    ):
        for i, ann in enumerate(annotation["annotations"]):
            atype = ann.get("type", "polygon")
            if atype == "bbox":
                st.markdown(
                    f"**Box {i + 1}** \u2014 `{ann['label']}` \u2014 ({ann['x1']:.0f},{ann['y1']:.0f})-({ann['x2']:.0f},{ann['y2']:.0f})"
                )
            else:
                st.markdown(
                    f"**Polygon {i + 1}** \u2014 `{ann['label']}` \u2014 {len(ann.get('points', []))} vertices"
                )
        st.json(annotation)
