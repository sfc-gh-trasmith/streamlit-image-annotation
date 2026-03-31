# Image Annotation Tool

A Streamlit-based image annotation tool for object detection workflows. Supports polygon and bounding box annotations, dynamic label management, train/val/test splitting, and COCO JSON + YOLO export formats.

## Quickstart

```bash
# Clone and enter the project
cd streamlit-image-annotation

# Install dependencies (requires Python 3.13+)
uv sync

# Optional: install pyyaml for YOLO export support
uv add pyyaml

# Run the app
uv run streamlit run app/main.py
```

The app opens at `http://localhost:8501`. Drop images into the `images/` directory or upload them via the sidebar.

## Features

### Annotation Modes
- **Polygon** — click to place vertices, click near the start point to close the shape
- **Bounding Box** — click and drag to draw a rectangle

Switch modes with the **Draw Mode** radio in the sidebar. Both types can coexist on the same image.

### Canvas Controls
| Button | Action |
|--------|--------|
| Undo Point | Remove last polygon vertex |
| Close Polygon | Finish current polygon |
| Delete Last | Remove most recent annotation |
| Clear All | Remove all annotations from canvas |
| Save | Persist annotations to disk |

**Keyboard shortcuts:** `Esc` cancel current shape, `Ctrl+Z` undo last vertex (polygon mode).

### Label Management
- Select the active label class from the sidebar dropdown
- Add or remove labels via the **Manage Labels** expander
- Labels persist in `output/config.json`

### Dataset Splitting
- Assign each image to **train**, **val**, or **test** via the sidebar dropdown
- Use **Auto-Split All** to randomly distribute images by percentage (default 70/20/10)

### Export Formats
- **COCO JSON** — standard COCO format with images, annotations (bbox + segmentation), and categories. Saved to `output/exports/coco_annotations.json`
- **YOLO** — normalized `cls cx cy w h` text files organized into `images/{split}/` and `labels/{split}/` directories with a `data.yaml`. Saved to `output/exports/yolo/`. Requires `pyyaml`.

### Other Features
- Image upload via sidebar (PNG, JPG, JPEG, BMP, TIFF)
- Filter images by labeled/unlabeled status
- Progress stats (total images, labeled count, completion %)
- Class distribution analytics
- Annotated overlay previews saved to `output/annotated/`

## Project Structure

```
streamlit-image-annotation/
├── app/
│   └── main.py              # Application code
├── images/                   # Source images (add yours here)
├── output/
│   ├── annotations/          # Per-image JSON annotation files
│   ├── annotated/            # Overlay preview images
│   ├── exports/              # COCO JSON and YOLO exports
│   └── config.json           # Labels and split assignments
├── pyproject.toml
└── README.md
```

## Requirements

- Python >= 3.13
- streamlit >= 1.55.0
- Pillow (bundled with streamlit)
- pyyaml (optional, for YOLO export)
