# -*- coding: utf-8 -*-
"""Patch: add the 7 absolute-value entries to metric_registry.py."""
import ast

P = "src/analysis/metric_registry.py"
s = open(P, encoding="utf-8").read()

addition = '''    # ── القيم المطلقة المطبوعة (صفوف مستقلة في التقرير — مستخلصة وتتحقق آليًا) ──
    MetricEntry("revenue", "الإيرادات", "Revenue (reported)",
        "القيمة المطبوعة في قائمة الدخل — مستخلصة وتتحقق طبقات المصادر",
        ("revenue",), "الإيراد المحقق", "قائمة الدخل", "لا ينطبق (قيمة مطبوعة)",
        "عملة", 0, "لا ينطبق", "لا يُشتق أبدًا — قراءة مباشرة موثقة", _N,
        "Growth & Income", "test_decision_log", "validated"),
    MetricEntry("net_income", "صافي أرباح العام", "Net Income (reported)",
        "القيمة المطبوعة — تُطبع في ثلاث قوائم ويحسم التصويت والتحقق",
        ("net_income",), "صافي ربح العام", "ثلاث قوائم + تحقق مركزي + رأي ثالث",
        "لا ينطبق", "عملة", 0, "لا ينطبق", "لا يُشتق — الأكثر تحققًا في النظام",
        _N, "Growth & Income", "test_decision_log", "validated"),
    MetricEntry("gross_profit", "مجمل الربح", "Gross Profit (reported)",
        "المطبوع؛ يُشتق (الإيراد − التكلفة) عند غيابه مع علم", ("gross_profit",),
        "مجمل الربح", "قائمة الدخل", "لا ينطبق", "عملة", 0, "لا ينطبق",
        "الاشتقاق مسموح مع علم — الإيراد والتكلفة يتحققان بالهوية", _N,
        "Profitability", "test_pipeline", "validated"),
    MetricEntry("operating_income", "الربح التشغيلي", "Operating Income (reported)",
        "المطبوع؛ يُشتق (المجمل − المصروفات) عند غيابه", ("operating_income",),
        "الربح التشغيلي", "قائمة الدخل", "لا ينطبق", "عملة", 0, "لا ينطبق",
        "يُشتق مع علم عند الغياب", _N, "Profitability", "test_pipeline", "documented"),
    MetricEntry("operating_cash_flow", "صافي التدفق التشغيلي", "Operating Cash Flow (reported)",
        "المطبوع في قائمة التدفقات — يتحقق بطبقة مخصصة بنسختي معالجة",
        ("operating_cash_flow",), "التدفق التشغيلي", "قائمة التدفقات + تحقق مخصص",
        "لا ينطبق", "عملة", 0, "لا ينطبق", "السالب = استهلاك نقدي", _N,
        "Cash Flow", "test_decision_log", "validated"),
    MetricEntry("investing_cash_flow", "صافي التدفق الاستثماري", "Investing Cash Flow (reported)",
        "المطبوع في قائمة التدفقات — يتحقق بطبقة التدفقات", ("investing_cash_flow",),
        "التدفق الاستثماري", "قائمة التدفقات + تحقق مزدوج", "لا ينطبق",
        "عملة", 0, "لا ينطبق", "السالب طبيعي (استثمار)", _N, "Cash Flow",
        "test_decision_log", "validated"),
    MetricEntry("financing_cash_flow", "صافي التدفق التمويلي", "Financing Cash Flow (reported)",
        "المطبوع — يتحقق بطبقة مزدوجة (صحح لايف 727,093,341 → 727,063,341)",
        ("financing_cash_flow",), "التدفق التمويلي", "قائمة التدفقات + تحقق مزدوج",
        "لا ينطبق", "عملة", 0, "لا ينطبق", "السالب طبيعي (سداد)", _N,
        "Cash Flow", "test_decision_log", "validated"),
    # ── Profitability (الربحية) ──'''

anchor = "    # ── Profitability (الربحية) ──"
assert anchor in s, "anchor missing"
s = s.replace(anchor, addition, 1)
open(P, "w", encoding="utf-8").write(s)
ast.parse(s)
print("patched + syntax OK")
