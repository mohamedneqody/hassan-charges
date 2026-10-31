#!/usr/bin/env bash
# Run every accuracy sample through the official indra-ocr CLI and save
# TXT / JSONL / MD outputs for the accuracy evaluation.
set -u
cd "/mnt/d/hassan_charges/مشروع تخرج حسن/indra-ocr-benchmark" || exit 1
export PATH="$HOME/indra-ocr-bench/.venv/bin:$PATH"

run() { # name file mode
  local name=$1 file=$2 mode=$3
  echo "=== $name [$mode] ==="
  indra-ocr "$file" --mode "$mode" --format text > "outputs/${name}_${mode}.txt" 2>"logs/${name}_${mode}.stderr"
  indra-ocr "$file" --mode "$mode" --format json > "outputs/${name}_${mode}.jsonl" 2>>"logs/${name}_${mode}.stderr"
  indra-ocr "$file" --mode "$mode" --format md > "outputs/${name}_${mode}.md" 2>>"logs/${name}_${mode}.stderr"
}

run en_printed  test_data/images/en_printed.png  ocr
run ar_printed  test_data/images/ar_printed.png  ocr
run mixed_ar_en test_data/images/mixed_ar_en.png ocr
run table       test_data/images/table.png       ocr
run searchable  test_data/pdfs/searchable.pdf    auto
run searchable  test_data/pdfs/searchable.pdf    ocr
run scanned     test_data/pdfs/scanned.pdf       auto
run scanned     test_data/pdfs/scanned.pdf       ocr
echo ALL_SAMPLES_DONE
