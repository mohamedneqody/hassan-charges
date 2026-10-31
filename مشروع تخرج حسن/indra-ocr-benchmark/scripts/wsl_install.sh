#!/usr/bin/env bash
# Isolated installation of indra-ocr 1.1.2 into a WSL2 Ubuntu venv.
# The venv lives in the WSL home directory (ext4) to avoid slow /mnt/d I/O
# inflating cold-start measurements. Project artifacts stay on D:.
set -u

stamp() { date +"%Y-%m-%d %H:%M:%S"; }

VENV_PARENT="$HOME/indra-ocr-bench"
mkdir -p "$VENV_PARENT"
cd "$VENV_PARENT" || exit 1

# Ubuntu lacks python3.12-venv (ensurepip). Avoid touching the system:
# create the venv without pip, then bootstrap pip into it via get-pip.py.
if [ ! -x .venv/bin/pip ]; then
  echo "[$(stamp)] creating venv at $VENV_PARENT/.venv"
  rm -rf .venv
  python3 -m venv --without-pip .venv || { echo "venv creation FAILED"; exit 1; }
  echo "[$(stamp)] bootstrapping pip via get-pip.py"
  if command -v curl >/dev/null 2>&1; then
    curl -sS https://bootstrap.pypa.io/get-pip.py -o get-pip.py || exit 1
  else
    wget -q https://bootstrap.pypa.io/get-pip.py || exit 1
  fi
  .venv/bin/python get-pip.py -q || { echo "get-pip FAILED"; exit 1; }
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip -q

echo "[$(stamp)] pip installing indra-ocr and helper packages"
pip install indra-ocr==1.1.2 pillow numpy psutil jiwer arabic-reshaper python-bidi fpdf2 img2pdf
RC=$?
echo "[$(stamp)] pip install rc=$RC"
if [ "$RC" -ne 0 ]; then exit "$RC"; fi

echo "=== pip freeze ==="
pip freeze

python - <<'PYEOF'
import indra_ocr, PIL, cv2, onnxruntime, numpy, jiwer, psutil
print("import check OK")
print("indra_ocr file:", indra_ocr.__file__)
print("indra_ocr version:", getattr(indra_ocr, "__version__", "?"))
print("onnxruntime:", onnxruntime.__version__, "| providers:", onnxruntime.get_available_providers())
print("opencv:", cv2.__version__)
PYEOF
echo "[$(stamp)] INSTALL DONE"
