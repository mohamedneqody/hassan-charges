// مولد ملفات المتحدثين الثمانية — عربي RTL، غلاف R1 (DS-1)، docx-js
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, HeadingLevel, BorderStyle, WidthType, ShadingType,
  TableLayoutType, Header, Footer, PageNumber, NumberFormat,
} = require("docx");
const fs = require("fs");
const path = require("path");

const SPEAKERS = [
  ...require("./content_s1_s4.js"),
  ...require("./content_s5_s8.js"),
];

const OUT_DIR = path.resolve(__dirname, "..", "عرض_المتحدثين");
if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });

// ── لوحة DS-1 (Deep Sea) ──
const PAL = {
  bg: "0B1C2C", accent: "529286",
  cover: { titleColor: "FFFFFF", subtitleColor: "B0B8C0", metaColor: "90989F", footerColor: "687078" },
  table: { headerBg: "529286", headerText: "FFFFFF", accentLine: "529286", innerLine: "BECFCC", surface: "E8ECEB" },
  body: "1F2937", secondary: "475569", primary: "0B1C2C",
};

const NB = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const noBorders = { top: NB, bottom: NB, left: NB, right: NB };
const allNoBorders = { top: NB, bottom: NB, left: NB, right: NB, insideHorizontal: NB, insideVertical: NB };

const AR_FONT = "Arial";

// ── دوال الغلاف الإلزامية (من design-system.md) ──
function splitTitleLines(title, charsPerLine) {
  if (title.length <= charsPerLine) return [title];
  const breakAfter = new Set([..."\u060C\u061B\u061F", ..."-_\u2014\u2013\u00B7/", ..." \t", ":"]);
  const lines = [];
  let remaining = title;
  while (remaining.length > charsPerLine) {
    let breakAt = -1;
    for (let i = charsPerLine; i >= Math.floor(charsPerLine * 0.6); i--) {
      if (i < remaining.length && breakAfter.has(remaining[i - 1])) { breakAt = i; break; }
    }
    if (breakAt === -1) {
      const limit = Math.min(remaining.length, Math.ceil(charsPerLine * 1.3));
      for (let i = charsPerLine + 1; i < limit; i++) {
        if (breakAfter.has(remaining[i - 1])) { breakAt = i; break; }
      }
    }
    if (breakAt === -1) breakAt = charsPerLine;
    lines.push(remaining.slice(0, breakAt).trim());
    remaining = remaining.slice(breakAt).trim();
  }
  if (remaining) lines.push(remaining);
  return lines;
}

function calcTitleLayout(title, maxWidthTwips, preferredPt = 40, minPt = 24) {
  // العربية أضيق من CJK: عرض الحرف ≈ pt × 12 twips
  const charWidth = (pt) => pt * 12;
  const charsPerLine = (pt) => Math.floor(maxWidthTwips / charWidth(pt));
  let titlePt = preferredPt;
  let lines;
  while (titlePt >= minPt) {
    const cpl = charsPerLine(titlePt);
    if (cpl < 2) { titlePt -= 2; continue; }
    lines = splitTitleLines(title, cpl);
    if (lines.length <= 3) break;
    titlePt -= 2;
  }
  if (!lines || lines.length > 3) {
    lines = splitTitleLines(title, charsPerLine(minPt));
    titlePt = minPt;
  }
  return { titlePt, titleLines: lines };
}

function calcCoverSpacing(params) {
  const { titleLineCount = 1, titlePt = 36, hasSubtitle = false,
          hasEnglishLabel = false, metaLineCount = 0,
          fixedHeight = 800, pageHeight = 16838 } = params;
  const SAFETY = 1200;
  const usableHeight = pageHeight - SAFETY;
  const titleHeight = titleLineCount * (titlePt * 23 + 200);
  const subtitleHeight = hasSubtitle ? (12 * 23 + 600) : 0;
  const labelHeight = hasEnglishLabel ? (9 * 23 + 600) : 0;
  const metaHeight = metaLineCount * (10 * 23 + 100);
  const implicitParaHeight = 3 * 300;
  const contentHeight = titleHeight + subtitleHeight + labelHeight + metaHeight + fixedHeight + implicitParaHeight;
  const remainingSpace = usableHeight - contentHeight;
  const safeRemaining = Math.max(remainingSpace, 400);
  const FOOTER_MIN = 800;
  const rawTop = Math.floor(safeRemaining * 0.45);
  const rawBottom = Math.floor(safeRemaining * 0.45);
  const bottomSpacing = Math.max(rawBottom, FOOTER_MIN);
  const topSpacing = Math.max(rawTop - Math.max(0, FOOTER_MIN - rawBottom), 400);
  return { topSpacing, midSpacing: Math.max(safeRemaining - topSpacing - bottomSpacing, 0), bottomSpacing };
}

// ── غلاف R1 معرّب (يمين-محاذاة، بنية الوصفة محفوظة) ──
function buildCoverR1Arabic(config) {
  const P = config.palette;
  const padL = 800, padR = 1200;
  const availableWidth = 11906 - padL - padR - 300;
  const { titlePt, titleLines } = calcTitleLayout(config.title, availableWidth, 40, 24);
  const titleSize = titlePt * 2;
  const spacing = calcCoverSpacing({
    titleLineCount: titleLines.length, titlePt,
    hasSubtitle: !!config.subtitle, hasEnglishLabel: !!config.englishLabel,
    metaLineCount: (config.metaLines || []).length, fixedHeight: 400,
  });
  const accentRight = { style: BorderStyle.SINGLE, size: 8, color: P.accent, space: 12 };
  const children = [];

  children.push(new Paragraph({ spacing: { before: spacing.topSpacing } }));

  if (config.englishLabel) {
    children.push(new Paragraph({
      bidirectional: true, alignment: AlignmentType.RIGHT,
      indent: { left: padL, right: padR }, spacing: { after: 500 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: P.accent, space: 8 } },
      children: [new TextRun({ text: config.englishLabel, size: 22, color: P.accent, font: AR_FONT, rightToLeft: true })],
    }));
  }

  for (let i = 0; i < titleLines.length; i++) {
    children.push(new Paragraph({
      bidirectional: true, alignment: AlignmentType.RIGHT,
      indent: { right: padR },
      spacing: { after: i < titleLines.length - 1 ? 100 : 300, line: Math.ceil(titlePt * 23), lineRule: "atLeast" },
      children: [new TextRun({ text: titleLines[i], size: titleSize, bold: true, boldComplexScript: true,
        sizeComplexScript: titleSize, color: P.titleColor, font: AR_FONT, rightToLeft: true })],
    }));
  }

  if (config.subtitle) {
    children.push(new Paragraph({
      bidirectional: true, alignment: AlignmentType.RIGHT,
      indent: { right: padR }, spacing: { after: 800 },
      children: [new TextRun({ text: config.subtitle, size: 24, sizeComplexScript: true,
        color: P.subtitleColor, font: AR_FONT, rightToLeft: true })],
    }));
  }

  for (const line of (config.metaLines || [])) {
    children.push(new Paragraph({
      bidirectional: true, alignment: AlignmentType.RIGHT,
      indent: { right: padR + 200 }, spacing: { after: 80 },
      border: { right: accentRight },
      children: [new TextRun({ text: line, size: 24, sizeComplexScript: true,
        color: P.metaColor, font: AR_FONT, rightToLeft: true })],
    }));
  }

  children.push(new Paragraph({ spacing: { before: spacing.bottomSpacing } }));

  children.push(new Paragraph({
    bidirectional: true, alignment: AlignmentType.RIGHT,
    indent: { left: padL, right: padR },
    border: { top: { style: BorderStyle.SINGLE, size: 2, color: P.accent, space: 8 } },
    spacing: { before: 200 },
    children: [
      new TextRun({ text: config.footerRight || "", size: 16, sizeComplexScript: true, color: P.footerColor, font: AR_FONT, rightToLeft: true }),
      new TextRun({ text: "                                   " }),
      new TextRun({ text: config.footerLeft || "", size: 16, sizeComplexScript: true, color: P.footerColor, font: AR_FONT, rightToLeft: true }),
    ],
  }));

  return [new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    layout: TableLayoutType.FIXED,
    borders: allNoBorders,
    rows: [new TableRow({
      height: { value: 16838, rule: "exact" },
      children: [new TableCell({
        shading: { type: ShadingType.CLEAR, fill: P.bg }, borders: noBorders,
        children,
      })],
    })],
  })];
}

// ── بنّائات المتن (RTL) ──
function h1(text) {
  return new Paragraph({
    bidirectional: true, alignment: AlignmentType.RIGHT,
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 400, after: 160, line: 312 },
    children: [new TextRun({ text, bold: true, boldComplexScript: true, size: 32, sizeComplexScript: 32,
      color: PAL.primary, font: AR_FONT, rightToLeft: true })],
  });
}
function h2(text) {
  return new Paragraph({
    bidirectional: true, alignment: AlignmentType.RIGHT,
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 120, line: 312 },
    border: { right: { style: BorderStyle.SINGLE, size: 12, color: PAL.accent, space: 8 } },
    children: [new TextRun({ text, bold: true, boldComplexScript: true, size: 27, sizeComplexScript: 27,
      color: PAL.primary, font: AR_FONT, rightToLeft: true })],
  });
}
function body(text, opts = {}) {
  return new Paragraph({
    bidirectional: true, alignment: AlignmentType.JUSTIFIED,
    spacing: { line: 312, after: opts.after ?? 120 },
    children: [new TextRun({ text, size: 24, sizeComplexScript: true, color: PAL.body,
      font: AR_FONT, rightToLeft: true, bold: opts.bold || false, boldComplexScript: opts.bold || false })],
  });
}
function bullet(text, marker = "\u2022 ") {
  return new Paragraph({
    bidirectional: true, alignment: AlignmentType.JUSTIFIED,
    indent: { right: 340 }, spacing: { line: 312, after: 100 },
    children: [new TextRun({ text: marker + text, size: 24, sizeComplexScript: true,
      color: PAL.body, font: AR_FONT, rightToLeft: true })],
  });
}
function quoteBox(text, label) {
  const children = [];
  if (label && label.trim().length > 0) {
    children.push(new TextRun({
      text: label.trim() + " ",
      bold: true, boldComplexScript: true, size: 24, sizeComplexScript: true,
      color: PAL.primary, font: AR_FONT, rightToLeft: true
    }));
  }
  children.push(new TextRun({
    text, size: 24, sizeComplexScript: true,
    color: PAL.body, font: AR_FONT, rightToLeft: true
  }));

  return new Paragraph({
    bidirectional: true, alignment: AlignmentType.JUSTIFIED,
    indent: { right: 340, left: 340 },
    spacing: { line: 312, before: 120, after: 200 },
    shading: { type: ShadingType.CLEAR, fill: PAL.table.surface },
    border: { right: { style: BorderStyle.SINGLE, size: 16, color: PAL.accent, space: 10 } },
    children,
  });
}

// ── بناء مستند متحدث ──
function buildDoc(S) {
  const cover = buildCoverR1Arabic({
    title: S.title,
    subtitle: S.subtitle,
    englishLabel: "المتحدث رقم " + S.num + " من 8",
    metaLines: [
      "مشروع التخرج: مساعد ذكي لتحليل القوائم المالية — دراسة تطبيقية على الشركات المقيدة بالبورصة المصرية",
      "وثيقة الإلقاء والتفصيل التقني الخاصة بك",
      "قاعدة العرض: وثيقة 2022 الحقيقية هي الملف البطل الذي يمر عبر كل المتحدثين",
    ],
    footerRight: "Financial Statement Analysis Agent",
    footerLeft: "2026",
    palette: { bg: PAL.bg, titleColor: PAL.cover.titleColor, subtitleColor: PAL.cover.subtitleColor,
               metaColor: PAL.cover.metaColor, accent: PAL.accent, footerColor: PAL.cover.footerColor },
  });

  const bodyChildren = [];

  // ترويسة المتحدث وعنوانه وفكرة دوره في سطرين (الصفحة 2 وما بعدها)
  bodyChildren.push(new Paragraph({
    bidirectional: true, alignment: AlignmentType.RIGHT,
    spacing: { before: 100, after: 80 },
    children: [
      new TextRun({
        text: `المتحدث ${S.num} من 8: ${S.title}`,
        bold: true, boldComplexScript: true,
        size: 34, sizeComplexScript: 34,
        color: PAL.primary, font: AR_FONT, rightToLeft: true
      }),
    ],
  }));

  if (S.subtitle) {
    bodyChildren.push(new Paragraph({
      bidirectional: true, alignment: AlignmentType.RIGHT,
      spacing: { after: 140 },
      children: [
        new TextRun({
          text: S.subtitle,
          size: 22, sizeComplexScript: true,
          color: PAL.secondary, font: AR_FONT, rightToLeft: true
        }),
      ],
    }));
  }

  if (S.roleSummary) {
    bodyChildren.push(quoteBox(S.roleSummary, "فكرة دورك في سطرين:"));
  }

  // 1. بطاقة دورك وافتتاحيتك في سطور
  bodyChildren.push(h1("أولًا: بطاقة دورك وافتتاحيتك في سطور"));
  bodyChildren.push(body(S.opening));

  // 2. نص الإلقاء التفصيلي
  bodyChildren.push(h1("ثانيًا: نص الإلقاء التفصيلي — نقطة بنقطة"));
  bodyChildren.push(body("كل نقطة أدناه مكتوبة كنص كامل: اقرأها مرتين ثم أعد صياغتها بكلماتك — الترتيب والتسليم أهم من الحفظ الحرفي.", { bold: true }));
  for (const item of S.delivery) {
    bodyChildren.push(h2(item.h));
    for (const p of item.paras) bodyChildren.push(body(p));
  }

  // 3. إزاي اتعمل — الشرح التقني المفصل
  bodyChildren.push(h1("ثالثًا: إزاي اتعمل — الشرح التقني المفصل"));
  bodyChildren.push(body("هذا القسم يجيب سؤال اللجنة الأول: «كيف اتعمل؟». كل آلية بالملف المسؤول عنها في الكود، وكيف تعمل داخليًا، وبمثال حقيقي من وثيقة 2022 بأرقامها الفعلية.", { bold: true }));
  for (const t of S.tech) {
    bodyChildren.push(h2(t.name));
    bodyChildren.push(body("الملف المسؤول: " + t.file, { bold: true }));
    for (const step of t.how) bodyChildren.push(bullet(step));
    if (t.example) bodyChildren.push(quoteBox(t.example, "مثال حقيقي:"));
  }

  // 4. أدلتك الرقمية
  bodyChildren.push(h1("رابعًا: أدلتك الرقمية — احفظها وأعد قولها"));
  for (const e of S.evidence) bodyChildren.push(bullet(e, "\u2713 "));

  // 5. أسئلة اللجنة المتوقعة
  bodyChildren.push(h1("خامسًا: أسئلة اللجنة المتوقعة — وإجاباتك النموذجية"));
  for (const qa of S.qa) {
    bodyChildren.push(h2("سؤال: " + qa.q));
    bodyChildren.push(body("الإجابة: " + qa.a));
  }

  // 6. نصائح العرض + التسليم
  bodyChildren.push(h1("سادسًا: نصائح عرضك الخاصة (التوقيت والنبرة والمحاذير)"));
  for (const t of S.tips) bodyChildren.push(bullet(t, "\u2190 "));

  const handoffTitle = S.num === 8
    ? "سابعًا: جملة تسليم العرض وختامه أمام لجنة المحكمين — قلها بثقة"
    : "سابعًا: جملة تسليمك للمتحدث التالي — قلها حرفيًا";
  bodyChildren.push(h1(handoffTitle));
  bodyChildren.push(quoteBox(S.handoff, ""));

  const doc = new Document({
    styles: { default: { document: {
      run: { font: AR_FONT, size: 24, color: PAL.body },
      paragraph: { spacing: { line: 312 } },
    }}},
    features: { updateFields: false },
    sections: [
      { properties: { page: { size: { width: 11906, height: 16838 },
          margin: { top: 0, bottom: 0, left: 0, right: 0 } } },
        children: cover },
      { properties: { page: { margin: { top: 1300, bottom: 1300, left: 1500, right: 1500 },
          pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL } } },
        headers: { default: new Header({ children: [new Paragraph({
          bidirectional: true, alignment: AlignmentType.RIGHT,
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: PAL.table.innerLine, space: 4 } },
          children: [new TextRun({ text: "مشروع التخرج — مساعد ذكي لتحليل القوائم المالية | المتحدث " + S.num,
            size: 16, sizeComplexScript: true, color: PAL.secondary, font: AR_FONT, rightToLeft: true })],
        })] }) },
        footers: { default: new Footer({ children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [new TextRun({ children: [PageNumber.CURRENT], size: 18, color: PAL.secondary, font: AR_FONT })],
        })] }) },
        children: bodyChildren },
    ],
  });

  return doc;
}

// ── التوليد ──
(async () => {
  for (const S of SPEAKERS) {
    const doc = buildDoc(S);
    const buf = await Packer.toBuffer(doc);
    const out = path.join(OUT_DIR, S.file);
    fs.writeFileSync(out, buf);
    console.log("OK:", S.file, Math.round(buf.length / 1024) + " KB");
  }
  console.log("ALL DONE:", SPEAKERS.length, "files");
})();
