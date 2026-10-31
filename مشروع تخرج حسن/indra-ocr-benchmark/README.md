# Indra OCR Benchmark — HP ZBook Studio G8 (CPU فقط)

مشروع قياس عملي لتثبيت وتشغيل واختبار **Datalab Indra OCR 1.1.2** محليًا على المعالج فقط (بدون GPU وبدون APIs مدفوعة)، مع قياس السرعة الحقيقية والدقة للعربية والإنجليزية.

## البيئة المستخدمة

- الجهاز: HP ZBook Studio 15.6 G8 — Intel Core i7-11850H (8 أنوية فعلية / 16 منطقية، AVX2/AVX512/FMA)، 32GB RAM.
- نظام التشغيل: Windows 11 Pro + **WSL2 (Ubuntu, Python 3.12.3)** — المنصة الرسمية المُختبَرة للحزمة (Linux x86_64).
- محرك الاستدلال: ONNX Runtime (CPUExecutionProvider) — لا يوجد PyTorch ولا GPU.
- الأوزان: `datalab-to/indra-ocr` من Hugging Face (~76MB) في cache دائم: `~/.cache/huggingface/hub/models--datalab-to--indra-ocr` داخل WSL.

## بنية المشروع

```
indra-ocr-benchmark/
├── scripts/
│   ├── wsl_install.sh      # إنشاء venv معزول في WSL وتثبيت الحزم
│   ├── make_test_data.py   # توليد عينات الاختبار + ground truth
│   ├── run_samples.sh      # تشغيل كل العينات عبر CLI الرسمي (3 صيغ)
│   ├── accuracy.py         # حساب CER/WER وتشخيص أخطاء الترتيب
│   ├── benchmark.py        # منسّق القياس (taskset + تكرارات + results.csv)
│   └── bench_child.py      # عملية قياس واحدة (load/warmup/infer + مراقبة CPU/RAM)
├── test_data/
│   ├── images/             # صور: عربي، إنجليزي، مختلط، جدول
│   ├── pdfs/               # searchable.pdf (طبقة نصية)، scanned.pdf (صور فقط)، bench_40p.pdf (40 صفحة OCR فعلي)
│   └── ground_truth.json   # النص الأصلي الدقيق لكل عينة
├── outputs/                # مخرجات OCR: TXT + JSONL + MD لكل عينة ووضع
├── benchmarks/
│   ├── results.csv         # كل قياسات السرعة الفعلية (API + CLI)
│   ├── runs/               # JSON لكل تشغيل مفرد
│   └── accuracy_results.json
├── logs/                   # سجلات التثبيت والتشغيل
├── BENCHMARK_REPORT.md     # التقرير النهائي بالأرقام الحقيقية
└── README.md
```

## إعادة التشغيل من الصفر (WSL2 Ubuntu)

```bash
# 1) التثبيت (venv معزول في ~/indra-ocr-bench/.venv — لا يلمس بايثون النظام)
bash scripts/wsl_install.sh

# 2) توليد عينات الاختبار والـ ground truth
~/indra-ocr-bench/.venv/bin/python scripts/make_test_data.py "$(pwd)"

# 3) تشغيل كل العينات وحفظ TXT/JSONL/MD
bash scripts/run_samples.sh

# 4) تقييم الدقة CER/WER
~/indra-ocr-bench/.venv/bin/python scripts/accuracy.py "$(pwd)"

# 5) قياس السرعة: 1/2/4/8 أنوية × 3 تكرارات + CLI كامل
export INDRA_BENCH_PROJ="$(pwd)"
~/indra-ocr-bench/.venv/bin/python scripts/benchmark.py --core-list 1,2,4,8 --repeats 3
```

ملاحظات مهمة:
- السكربتات على قرص Windows (/mnt/d) قد تحتوي نهايات أسطر CRLF؛ السكربتات تُشغَّل عبر نسخة منقّاة من `\r` كما في الأوامر أعلاه أو بتنفيذ `sed -i 's/\r$//' scripts/*.py` مرة واحدة.
- ربط الأنوية يتم بـ `taskset -c 0-(2N-1)` لأن كل نواة فعلية = مؤشرا CPU متتاليان على i7-11850H (تحقق: `lscpu -e`).
- الاستخدام المباشر للنموذج بعد التثبيت:

```bash
export PATH="$HOME/indra-ocr-bench/.venv/bin:$PATH"
indra-ocr file.pdf                      # markdown إلى stdout
indra-ocr scan.png --format json        # أسطر + صناديق + ثقة + توقيتات
indra-ocr doc.pdf --mode ocr --cores 4  # تجاهل طبقة النص وإجبار OCR
```

## ملاحظة عن الترخيص

الكود Apache-2.0، والأوزان رخصة OpenRAIL-M معدّلة: مسموح للبحث والاستخدام الشخصي والشركات الناشئة تحت 20M$ تمويل/إيرادات، وممنوع المنافسة المباشرة مع API شركة Datalab.
