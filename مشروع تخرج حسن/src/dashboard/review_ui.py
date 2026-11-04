# -*- coding: utf-8 -*-
"""Review UI (واجهة المراجعة البشرية) — pure view builder + thin Streamlit
renderer. The reviewer sees the PAGE image with the cell bbox drawn, the
crop, the field, the year, EVERY machine reading, the conflict reason, and
the proposed value — and decides approve / correct / reject. Ground Truth is
NEVER shown: the pure builder raises if a GT key reaches a packet."""
from __future__ import annotations

import cv2
import numpy as np


def build_review_view(packet: dict) -> dict:
    """Everything the reviewer needs, GT-free by construction."""
    banned = {"gt", "gt_value", "ground_truth", "answer"}
    if banned & set(packet.keys()):
        raise ValueError("GT must never reach the reviewer's view")
    page_path = packet.get("page_image")
    page_with_box = None
    bbox = packet.get("bbox_rel")
    if page_path and bbox:
        img = cv2.imdecode(np.fromfile(page_path, dtype=np.uint8),
                           cv2.IMREAD_GRAYSCALE)
        if img is not None:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            h, w = img.shape[:2]
            x0, y0, x1, y1 = [int(v * d) for v, d in
                              zip(bbox, (w, h, w, h))]
            cv2.rectangle(img, (x0, y0), (x1, y1), (0, 0, 255), 3)
            ok, out = cv2.imencode(".png", img)
            page_with_box = out.tobytes() if ok else None
    return {
        "packet_id": packet["packet_id"],
        "field": packet["field"],
        "year": packet["year"],
        "page_image": page_path,
        "page_with_bbox_png": page_with_box,
        "crop_image": packet.get("crop_image"),
        "machine_selected": packet.get("machine_selected"),
        "readings": packet.get("readings", {}),
        "conflict_reason": packet.get("conflict_reason"),
        "proposed_value": packet.get("machine_selected"),
        "actions": ("adopt_proposed", "correct_value", "reject_unreadable"),
    }


def render_review_tab(st, queue: list[dict], reviewer: str) -> None:
    """Thin Streamlit wrapper (importable only inside the app)."""
    st.header("🔍 مراجعة الخانات غير الحاسمة")
    st.caption("اعتمد القيمة المقترحة، أو صحّحها من الصورة المطبوعة، أو ارفضها "
               "كنغير مقروءة — بندًا وسنةً وموضعًا وقيمةً معًا. الإجابات "
               "المرجعية غير معروضة عمدًا.")
    name = st.text_input("اسم المراجع", value=reviewer or "")
    pin = st.text_input("رمز التحقق (PIN)", type="password")
    for pkt in queue:
        view = build_review_view(pkt)
        with st.expander(f"{view['field']} — {view['year']} "
                         f"({view['machine_selected'] and format(view['machine_selected'], ',.0f')})"):
            c1, c2 = st.columns(2)
            with c1:
                if view["page_with_bbox_png"]:
                    st.image(view["page_with_bbox_png"],
                             caption="الصفحة وحدود الخانة")
            with c2:
                if view["crop_image"]:
                    st.image(view["crop_image"], caption="القصاصة المركزة")
            st.write(f"**قراءات الآلة:** {view['readings']}")
            st.warning(f"**سبب التعارض:** {view['conflict_reason']}")
            st.info(f"**القيمة المقترحة:** {view['proposed_value']}")
            b1, b2, b3 = st.columns(3)
            if b1.button("✅ اعتماد المقترح", key=f"ok_{pkt['packet_id']}"):
                from src.extraction.human_review import apply_review

                try:
                    apply_review(queue, pkt["packet_id"],
                                 view["proposed_value"], reviewer=name,
                                 credential=pin)
                    st.success("سُجل الاعتماد في سلسلة التدقيق")
                except PermissionError as e:
                    st.error(f"مرفوض: {e}")
            val = b2.number_input("قيمة مصححة", key=f"fix_{pkt['packet_id']}")
            if b2.button("✏️ اعتماد قيمة مصححة", key=f"fixgo_{pkt['packet_id']}"):
                from src.extraction.human_review import apply_review

                try:
                    apply_review(queue, pkt["packet_id"], float(val),
                                 reviewer=name, credential=pin)
                    st.success("سُجل التصحيح")
                except PermissionError as e:
                    st.error(f"مرفوض: {e}")
            if b3.button("🚫 رفض — غير مقروءة", key=f"rej_{pkt['packet_id']}"):
                from src.extraction.human_review import apply_review

                try:
                    apply_review(queue, pkt["packet_id"], None, reviewer=name,
                                 credential=pin)
                    st.warning("سُجل الرفض")
                except PermissionError as e:
                    st.error(f"مرفوض: {e}")
