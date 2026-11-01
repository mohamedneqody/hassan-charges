import json
import os
import subprocess

# We can run node to inspect the SPEAKERS array directly
node_code = """
const S = [
  ...require('./.docgen8/content_s1_s4.js'),
  ...require('./.docgen8/content_s5_s8.js')
];

const report = S.map(s => {
  return {
    num: s.num,
    file: s.file,
    title: s.title,
    subtitle: s.subtitle,
    opening_len: s.opening ? s.opening.length : 0,
    delivery_points: s.delivery ? s.delivery.length : 0,
    delivery_titles: s.delivery ? s.delivery.map(d => d.h) : [],
    tech_count: s.tech ? s.tech.length : 0,
    tech_files: s.tech ? s.tech.map(t => t.file) : [],
    evidence_count: s.evidence ? s.evidence.length : 0,
    qa_count: s.qa ? s.qa.length : 0,
    tips_count: s.tips ? s.tips.length : 0,
    tips: s.tips,
    handoff: s.handoff
  };
});

console.log(JSON.stringify(report, null, 2));
"""

res = subprocess.run(["node", "-e", node_code], cwd=r"D:\hassan_charges\مشروع تخرج حسن", capture_output=True, text=True, encoding="utf-8")
if res.returncode != 0:
    print("Node error:", res.stderr)
    exit(1)

data = json.loads(res.stdout)
print(f"Verified {len(data)} speakers:")
for s in data:
    print(f"\n--- المتحدث {s['num']}: {s['title']} ---")
    print(f"  الملف: {s['file']}")
    print(f"  الافتتاحية: {s['opening_len']} حرف")
    print(f"  نقاط الإلقاء: {s['delivery_points']} نقاط -> {', '.join(s['delivery_titles'][:3])}...")
    print(f"  الشرح التقني (إزاي اتعمل): {s['tech_count']} آليات في ملفات: {', '.join(s['tech_files'][:3])}...")
    print(f"  الأدلة الرقمية: {s['evidence_count']} أدلة")
    print(f"  أسئلة اللجنة: {s['qa_count']} أسئلة بإجاباتها")
    print(f"  نصائح العرض: {s['tips_count']} نصائح")
    print(f"  جملة التسليم: {s['handoff'][:60]}...")
