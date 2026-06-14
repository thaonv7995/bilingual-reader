#!/usr/bin/env bash
# Repair broken editable install (ModuleNotFoundError: books_cli).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

PYVER="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
SITE=".venv/lib/python${PYVER}/site-packages"

echo "Cleaning broken books-core editable files..."
rm -f "${SITE}"/__editable__* "${SITE}"/__editable___books_core* 2>/dev/null || true
rm -rf "${SITE}"/books_core*.dist-info 2>/dev/null || true

if ! pip install --force-reinstall -e backend; then
  echo "Editable install failed; repairing PyMuPDF and retrying without dependency reinstall..."
  pip install --ignore-installed --no-deps "pymupdf>=1.24.0"
  pip install --no-deps -e backend
fi

python - <<'PY'
from pathlib import Path
import site

root = Path.cwd().resolve()
site_dir = Path(site.getsitepackages()[0])
(site_dir / "books_core_backend.pth").write_text(str(root / "backend") + "\n", encoding="utf-8")
(site_dir / "sitecustomize.py").write_text(
    "from pathlib import Path\n"
    "import sys\n"
    "backend = Path(__file__).resolve().parents[4] / 'backend'\n"
    "if backend.is_dir() and str(backend) not in sys.path:\n"
    "    sys.path.insert(0, str(backend))\n",
    encoding="utf-8",
)
PY

cat > .venv/bin/books-cli <<'PY'
#!/usr/bin/env python
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from books_cli.main import main

raise SystemExit(main())
PY
chmod +x .venv/bin/books-cli

PYTHONPATH="$ROOT/backend" python -c "import books_cli, books_core; print('OK: books-cli ready')"
books-cli --help | head -3
