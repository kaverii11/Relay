#!/bin/sh
# Render writeup/writeup.md to writeup/writeup.pdf: A4, 10 pt, 0.5 in margins (K, 2026-11-12).
# Needs pandoc and Google Chrome (headless print). Also prints page counts: writing only, and the whole file.
set -e
cd "$(dirname "$0")/.."
T=$(mktemp -d)
cat > "$T/p.css" <<'CSS'
@page { size: A4; margin: 0.5in; }
html, body { font-family: Helvetica, Arial, sans-serif !important; font-size: 10pt !important; line-height: 1.2 !important;
             max-width: none !important; padding: 0 !important; margin: 0 !important; }
h1 { font-size: 14pt !important; } h2 { font-size: 12pt !important; margin: 8px 0 3px !important; } h3 { font-size: 11pt !important; }
p, li { margin: 3px 0 !important; } blockquote { margin: 4px 16px !important; }
table { border-collapse: collapse; font-size: 8.5pt !important; } td, th { border: 1px solid #999; padding: 2px 4px; }
code { font-size: 9pt !important; word-break: break-all; }
CSS
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
render() {  # $1 = markdown in, $2 = pdf out
  pandoc "$1" -o "$T/o.html" --standalone --metadata title=" " --css "$T/p.css" --embed-resources
  "$CHROME" --headless --disable-gpu --no-pdf-header-footer --print-to-pdf="$2" "$T/o.html" 2>/dev/null
}
sed -n '1,/^## Results tables/p' writeup/writeup.md | sed '$d' > "$T/prose.md"
render "$T/prose.md" "$T/prose.pdf"
render writeup/writeup.md writeup/writeup.pdf
.venv/bin/python - "$T/prose.pdf" writeup/writeup.pdf <<'PY'
import sys, pymupdf
for name, f in zip(("writing only", "whole write-up"), sys.argv[1:]):
    d = pymupdf.open(f)
    print(f"{name}: {d.page_count} pages (last page {len(d[-1].get_text().split())} words)")
PY
rm -rf "$T"
echo "wrote writeup/writeup.pdf"
