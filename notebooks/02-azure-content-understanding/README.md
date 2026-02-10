# Azure Content Understanding (ACU)

This notebook demonstrates how to call Azure Content Understanding (ACU) to analyze documents and visualize the returned field/line bounding boxes.

ACU returns normalized fields and page-level geometry in its JSON output. Each field includes a `source` string with one or more `D(...)` polygons (page + 4-point quad). These can be drawn over the corresponding PDF page image to validate extraction quality.

## Poppler (Windows) for PDF Rendering

The visualization relies on `pdf2image`, which requires Poppler on Windows.

1. Download the latest Poppler release:
   https://github.com/oschwartz10612/poppler-windows/releases
2. Extract the zip to a folder, e.g. `C:\Users\deril\poppler`.
3. Use the `bin` folder path when converting PDFs:

```python
from pdf2image import convert_from_path
pdf_images = convert_from_path(
    pdf_path,
    poppler_path=r"C:\Users\deril\poppler\Library\bin"
)
```

You can also add the Poppler `bin` folder to your system PATH if you want to omit `poppler_path`.
