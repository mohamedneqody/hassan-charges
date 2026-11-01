import subprocess

node_code = """
const S = [
  ...require('./.docgen8/content_s1_s4.js'),
  ...require('./.docgen8/content_s5_s8.js')
];

S.forEach(s => {
  console.log(`Speaker ${s.num}:`);
  s.tips.forEach(t => console.log(`  - ${t}`));
});
"""

res = subprocess.run(["node", "-e", node_code], cwd=r"D:\hassan_charges\مشروع تخرج حسن", capture_output=True, text=True, encoding="utf-8")
print(res.stdout)
