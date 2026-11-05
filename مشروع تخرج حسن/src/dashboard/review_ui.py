# -*- coding: utf-8 -*-
"""Review UI (واجهة المراجعة البشرية) — pure view builder + thin Streamlit
renderer. The reviewer sees the PAGE image with the cell bbox drawn, the
surrounding ROW strip, the printed YEAR HEADER above the column, the crop,
the field label, the year, EVERY machine reading, the conflict reason, and
the proposed value — and must EXPLICITLY confirm five things (document,
field, year, position, value) before the backend accepts an attestation.
Ground Truth is NEVER shown: the pure builder raises if a GT key reaches a
packet. Roles/sessions are enforced in the BACKEND (human_review), the UI
merely collects credentials."""
from __future__ import annotations

import cv2
import numpy as np

from src.extraction.human_review import CONFIRMATION_KEYS, CONFIRMATION_LABELS_AR


def _imread(path: str | None):
    if not path:
        return None
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)


def _encode(img) -> bytes | None:
    ok, out = cv2.imencode(".png", img)
    return out.tobytes() if ok else None


def _row_strip(page_path: str, bbox, grow: float = 1.6) -> tuple | None:
    """Full-width strip around the cell's row (the surrounding context) with
    the cell boxed in red — so the reviewer sees the row, not just the cell."""
    img = _imread(page_path)
    if img is None or not bbox:
        return None
    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    h, w = img.shape[:2]
    x0, y0, x1, y1 = [int(v * d) for v, d in zip(bbox, (w, h, w, h))]
    ch = y1 - y0
    pad = int(ch * grow)
    sy0, sy1 = max(0, y0 - pad), min(h, y1 + pad)
    strip = img[sy0:sy1, 0:w].copy()
    cv2.rectangle(strip, (x0, y0 - sy0), (x1, y1 - sy0), (0, 0, 255), 3)
    return _encode(strip)


def _page_with_box(page_path: str, bbox) -> bytes | None:
    img = _imread(page_path)
    if img is None or not bbox:
        return None
    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    h, w = img.shape[:2]
    x0, y0, x1, y1 = [int(v * d) for v, d in zip(bbox, (w, h, w, h))]
    cv2.rectangle(img, (x0, y0), (x1, y1), (0, 0, 255), 3)
    return _encode(img)


def _cell_zoom(crop_path: str | None, bbox=None, page_path: str | None = None,
               scale: int = 3) -> bytes | None:
    """The cell crop, enlarged; falls back to cropping the page by bbox."""
    img = _imread(crop_path) if crop_path else None
    if img is None and bbox and page_path:
        page = _imread(page_path)
        if page is not None and bbox:
            h, w = page.shape[:2]
            x0, y0, x1, y1 = [int(v * d) for v, d in zip(bbox, (w, h, w, h))]
            img = page[max(0, y0 - 2):y1 + 2, max(0, x0 - 2):x1 + 2]
    if img is None:
        return None
    img = cv2.resize(img, None, fx=scale, fy=scale,
                     interpolation=cv2.INTER_CUBIC)
    return _encode(img)


def build_review_view(packet: dict) -> dict:
    """Everything the reviewer needs, GT-free by construction."""
    banned = {"gt", "gt_value", "ground_truth", "answer"}
    if banned & set(packet.keys()):
        raise ValueError("GT must never reach the reviewer's view")
    page_path = packet.get("page_image")
    bbox = packet.get("bbox_rel")
    page_with_box = _page_with_box(page_path, bbox) if page_path else None
    row_strip = _row_strip(page_path, bbox) if page_path else None
    crop_png = _cell_zoom(packet.get("crop_image"), bbox, page_path)
    ctx = packet.get("context") or {}
    return {
        "packet_id": packet["packet_id"],
        "field": packet["field"],
        "year": packet["year"],
        "page_image": page_path,
        "page_with_bbox_png": page_with_box,
        "row_strip_png": row_strip,
        "crop_image_png": crop_png,
        "crop_image": packet.get("crop_image"),
        "date_header_image": packet.get("date_header_image"),
        "label_text": packet.get("label_text"),
        "machine_selected": packet.get("machine_selected"),
        "readings": packet.get("readings", {}),
        "conflict_reason": packet.get("conflict_reason"),
        "proposed_value": packet.get("machine_selected"),
        "source_pdf": packet.get("source_pdf"),
        "pdf_sha256": packet.get("pdf_sha256"),
        "page_image_sha256": packet.get("page_image_sha256"),
        "crop_sha256": packet.get("crop_sha256"),
        "extraction_version": packet.get("extraction_version"),
        "context_complete": bool(ctx.get("context_complete", False)),
        "confirmation_keys": list(CONFIRMATION_KEYS),
        "confirmation_labels": dict(CONFIRMATION_LABELS_AR),
        "actions": ("adopt_proposed", "correct_value", "reject_unreadable"),
    }


def _fmt(v) -> str:
    return format(v, ",.0f") if isinstance(v, (int, float)) else "—"


def render_review_tab(st, queue: list[dict], reviewer: str, data=None) -> None:
    """Thin Streamlit wrapper (importable only inside the app). Session-based:
    the PIN is exchanged ONCE for a short-lived token; every action is
    re-authorized in the BACKEND with the token's roles. `data` (optional
    FinancialData) receives the reviewed value so the decision log and the
    engine see EXACTLY what the human attested."""
    import os

    session_ttl = int(os.environ.get("REVIEW_SESSION_TTL", "1800"))
    st.header("🔍 مراجعة الخانات غير الحاسمة")
    st.caption("اعتمد القيمة المقترحة، أو صحّحها من الصورة المطبوعة، أو ارفضها "
               "كنغير مقروءة — بندًا وسنةً وموضعًا وقيمةً معًا، بعد تأكيد "
               "الخمسة عناصر صراحة. الإجابات المرجعية غير معروضة عمدًا.")

    # ── session gate: PIN → token (backend-issued, backend-validated) ──
    if "review_session" not in st.session_state:
        st.session_state["review_session"] = None
    sess = st.session_state["review_session"]
    if sess is None:
        with st.form("reviewer_login"):
            st.subheader("دخول المراجع")
            name = st.text_input("اسم المراجع", value=reviewer or "")
            pin = st.text_input("رمز التحقق (PIN)", type="password")
            if st.form_submit_button("بدء جلسة المراجعة"):
                from src.extraction.human_review import authenticate
                try:
                    st.session_state["review_session"] = authenticate(
                        name, pin, ttl_seconds=session_ttl)
                    st.rerun()
                except PermissionError as e:
                    st.error(f"مرفوض: {e}")
        return

    from src.extraction.human_review import (
        STATUS_HUMAN, apply_review, load_log, revoke_session, session_expiry,
        validate_session,
    )

    info = st.session_state["review_session"]
    remaining = max(0, int((session_expiry(info["token"]) or 0) - __import__("time").time()))
    st.success(f"جلسة المراجع **{info['reviewer']}** نشطة — "
               f"تنتهي بعد ~{remaining // 60} دقيقة")
    if st.button("🚪 إنهاء الجلسة"):
        revoke_session(info["token"])
        st.session_state["review_session"] = None
        st.rerun()
    reviewer_name = info["reviewer"]
    token = info["token"]

    done = {}
    try:
        from src.extraction.human_review import REVIEW_LOG as _log
        for r in load_log():
            if r.get("reviewer") == reviewer_name:
                done[r["packet_id"]] = r
    except Exception:
        pass

    for pkt in queue:
        view = build_review_view(pkt)
        pid = view["packet_id"]
        title_label = view.get("label_text") or view["field"]
        if done.get(pid, {}).get("status") == STATUS_HUMAN:
            st.expander(f"✔️ {title_label} — {view['year']} — تمت مراجعته "
                        f"({_fmt(view['machine_selected'])})", expanded=False)
            continue
        with st.expander(f"{title_label} — {view['year']} "
                         f"({view['machine_selected'] and _fmt(view['machine_selected'])})"):
            if not view["context_complete"]:
                st.error("⚠️ سياق غير مكتمل (ترويسة السنة أو تسمية البند غير "
                         "ظاهرة) — يمكن الرفض فقط، ولا يُقبل اعتماد قيمة.")
            c1, c2 = st.columns(2)
            with c1:
                if view["page_with_bbox_png"]:
                    st.image(view["page_with_bbox_png"],
                             caption="الصفحة وحدود الخانة")
                if view["date_header_image"]:
                    st.image(view["date_header_image"],
                             caption=f"ترويسة السنة فوق العمود (الصفحة {pkt['page']})")
            with c2:
                if view["crop_image_png"]:
                    st.image(view["crop_image_png"], caption="القصاصة المركّزة (مكبّرة)")
            if view["row_strip_png"]:
                st.image(view["row_strip_png"], caption="الصف المحيط كامل العرض")
            st.write(f"**البند:** {view['label_text'] or 'غير متوفر'} — "
                     f"**السنة:** {view['year']}")
            st.write(f"**قراءات الآلة:** {view['readings']}")
            st.warning(f"**سبب عدم الاعتماد الآلي:** {view['conflict_reason']}")
            st.info(f"**القيمة المقترحة:** {_fmt(view['proposed_value'])}")
            st.caption(f"المصدر: {view['source_pdf']} — بصمة PDF "
                       f"{view['pdf_sha256']} — بصمة الصفحة "
                       f"{view['page_image_sha256']} — بصمة القصاصة "
                       f"{view['crop_sha256']} — نسخة الاستخراج "
                       f"{view['extraction_version']}")

            # ── the five explicit confirmations ──
            st.markdown("**أكّد صراحة (الخمسة):**")
            conf = {}
            for k in view["confirmation_keys"]:
                conf[k] = bool(st.checkbox(view["confirmation_labels"][k],
                                           key=f"conf_{k}_{pid}"))
            all_id_ok = all(conf[k] for k in view["confirmation_keys"]
                            if k != "value")
            all_ok = all(conf.values())

            val = st.number_input("قيمة مصححة", key=f"fix_{pid}")
            b1, b2, b3 = st.columns(3)
            disabled = not all_ok
            if b1.button("✅ اعتماد المقترح", key=f"ok_{pid}",
                         disabled=disabled,
                         help="يتطلب تأكيد الخمسة عناصر"):
                try:
                    rec = apply_review(queue, pid, view["proposed_value"],
                                       reviewer=reviewer_name,
                                       session_token=token, data=data,
                                       confirmations=conf)
                    st.success(f"سُجل الاعتماد في سلسلة التدقيق "
                               f"(seq={rec['seq']})")
                except (PermissionError, ValueError) as e:
                    st.error(f"مرفوض: {e}")
            if b2.button("✏️ اعتماد قيمة مصححة", key=f"fixgo_{pid}",
                         disabled=disabled,
                         help="يتطلب تأكيد الخمسة عناصر"):
                try:
                    rec = apply_review(queue, pid, float(val),
                                       reviewer=reviewer_name,
                                       session_token=token, data=data,
                                       confirmations=conf)
                    st.success(f"سُجل التصحيح (seq={rec['seq']})")
                except (PermissionError, ValueError) as e:
                    st.error(f"مرفوض: {e}")
            if b3.button("🚫 رفض — غير مقروءة", key=f"rej_{pid}",
                         disabled=not all_id_ok,
                         help="الرفض يتطلب تأكيد الهوية (بند/سنة/موضع/مستند)"):
                try:
                    rec = apply_review(queue, pid, None,
                                       reviewer=reviewer_name,
                                       session_token=token, data=data,
                                       confirmations=conf)
                    st.warning(f"سُجل الرفض (seq={rec['seq']})")
                except (PermissionError, ValueError) as e:
                    st.error(f"مرفوض: {e}")
