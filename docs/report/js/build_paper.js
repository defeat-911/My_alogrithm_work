/**
 * new_doc.js — Chinese Academic Paper Template (课程论文模板)
 *
 * All formatting is pre-configured to GB/T 7714 + Chinese university standards:
 *   - A4 page, 2.5 cm margins on all sides
 *   - SimSun 12pt body, SimHei headings (Cambria Math for English/numbers)
 *   - Manual multi-level heading numbering (synchronized counters)
 *   - Three-line table helper with proper border handling
 *   - LaTeX formula support (block and inline) via temml + Word native math
 *   - Citation superscript handling [n] format
 *   - Reference list [1][2][3] numbering
 *   - Footer: centered page number
 *
 * Usage:
 *   1. Edit the CONTENT SECTION below
 *   2. node scripts/new_doc.js
 *   3. Outputs output.docx (or set OUTPUT_PATH)
 *
 * Dependencies:
 *   npm install docx temml fast-xml-parser
 */

'use strict';

const fs   = require('fs');
const path = require('path');

const {
  Document, Packer,
  Paragraph, TextRun, Math, MathRun,
  Table, TableRow, TableCell,
  Header, Footer,
  PageNumber, NumberFormat, AlignmentType, LineRuleType, HeadingLevel,
  LevelFormat, BorderStyle, WidthType, ShadingType, VerticalAlign,
  TableOfContents, PageBreak, ImageRun,
} = require('docx');

// MathML to docx Math converter
const { mathmlToDocxChildren } = require('./mathml-to-docx');
const temml = require('temml');

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const INPUT_MARKDOWN = process.argv[2] ? path.resolve(process.argv[2]) : null;
const BODY_ONLY = process.argv.includes('--body-only') || process.env.BODY_ONLY === '1';
const CAMPUS_TEMPLATE = process.argv.includes('--campus-template') || BODY_ONLY;
const OUTPUT_PATH = process.argv[3] && !process.argv[3].startsWith('--')
  ? path.resolve(process.argv[3])
  : (INPUT_MARKDOWN
      ? path.join(path.dirname(INPUT_MARKDOWN), `${path.parse(INPUT_MARKDOWN).name}.docx`)
      : 'output.docx');

// Page / margin (DXA: 1440 = 1 inch, 567 ≈ 1 cm)
const PAGE_W        = 11906;   // A4
const PAGE_H        = 16838;
// 页边距按课程《格式参考.docx》实测值：左右 1800 DXA (3.17cm)、上下 1440 DXA (2.54cm)
const MARGIN        = 1418;    // 2.50 cm (left/right), matches the course template body section
const MARGIN_V      = 1440;    // 2.54 cm (top/bottom)
const CONTENT_W     = PAGE_W - 2 * MARGIN;  // 9070 DXA

// Three-line table border presets
// ISSUE 1 FIX: Use NONE with proper color for invisible borders
const THICK = { style: BorderStyle.SINGLE, size: 12, color: '000000' }; // 1.5 pt
const THIN  = { style: BorderStyle.SINGLE, size: 6,  color: '000000' }; // 0.75 pt
const NONE  = { style: BorderStyle.NONE,   size: 0,  color: 'FFFFFF' };

// 表格内文字用五号（size 20 = 10pt），较正文小一号，是中文论文表格的通行做法，
// 同时显著压缩表格高度（见 build 说明）
const TABLE_FONT_SIZE = 21; // 10.5 pt

// 前置部分（题目+摘要+关键词+目录）在 CONTENT 中的结束下标，由
// buildContentFromMarkdown 在生成目录后填写。-1 表示未找到分节点，
// 此时整篇作为单节处理（不做罗马数字页码）。
let _frontMatterSplitAt = -1;

// ISSUE 3 FIX: Manual heading counters for synchronized numbering
let currentChapter = 0;
let currentSection = 0;
let currentSubsection = 0;

// ─────────────────────────────────────────────────────────────────────────────
// ISSUE 5/7 FIX: Inline Math Detection and Conversion
// ─────────────────────────────────────────────────────────────────────────────

// Unicode math symbols to LaTeX mapping
const UNICODE_TO_LATEX = {
  // Greek letters
  'α': '\\alpha', 'β': '\\beta', 'γ': '\\gamma', 'δ': '\\delta', 'ε': '\\varepsilon',
  'ζ': '\\zeta', 'η': '\\eta', 'θ': '\\theta', 'ι': '\\iota', 'κ': '\\kappa',
  'λ': '\\lambda', 'μ': '\\mu', 'ν': '\\nu', 'ξ': '\\xi', 'π': '\\pi',
  'ρ': '\\rho', 'σ': '\\sigma', 'τ': '\\tau', 'υ': '\\upsilon', 'φ': '\\phi',
  'χ': '\\chi', 'ψ': '\\psi', 'ω': '\\omega',
  'Γ': '\\Gamma', 'Δ': '\\Delta', 'Θ': '\\Theta', 'Λ': '\\Lambda', 'Ξ': '\\Xi',
  'Π': '\\Pi', 'Σ': '\\Sigma', 'Φ': '\\Phi', 'Ψ': '\\Psi', 'Ω': '\\Omega',
  // Subscript digits
  '₀': '_0', '₁': '_1', '₂': '_2', '₃': '_3', '₄': '_4',
  '₅': '_5', '₆': '_6', '₇': '_7', '₈': '_8', '₉': '_9',
  'ₙ': '_n', 'ₓ': '_x', 'ᵢ': '_i', 'ₜ': '_t', 'ₛ': '_s',
  // Superscript
  '⁰': '^0', '¹': '^1', '²': '^2', '³': '^3', '⁴': '^4',
  '⁵': '^5', '⁶': '^6', '⁷': '^7', '⁸': '^8', '⁹': '^9',
  'ⁿ': '^n', 'ⁱ': '^i',
  // Special symbols
  '∞': '\\infty', '∑': '\\sum', '∏': '\\prod', '∫': '\\int',
  '≤': '\\leq', '≥': '\\geq', '≠': '\\neq', '≈': '\\approx',
  '→': '\\to', '←': '\\leftarrow', '↔': '\\leftrightarrow',
  '∈': '\\in', '∉': '\\notin', '⊂': '\\subset', '⊃': '\\supset',
  '∀': '\\forall', '∃': '\\exists', '∧': '\\land', '∨': '\\lor',
  '×': '\\times', '÷': '\\div', '±': '\\pm', '∓': '\\mp',
  '·': '\\cdot', '…': '\\ldots', '⋯': '\\cdots',
  '′': "'", '″': "''",
  '⟨': '\\langle', '⟩': '\\rangle',
  // Superscript letter (for π*, Q*, etc.)
  '*': '^*',
};

/**
 * Convert text with Unicode math symbols to LaTeX format
 * @param {string} text - Text with Unicode math symbols
 * @returns {string} LaTeX formatted text
 */
function unicodeToLatex(text) {
  let result = text;
  for (const [unicode, latex] of Object.entries(UNICODE_TO_LATEX)) {
    result = result.split(unicode).join(latex);
  }
  return result;
}

/**
 * Detect if text contains math content (needs formula editor rendering)
 * ISSUE 7 FIX: Strict detection - don't match plain numbers or English words
 * @param {string} text - Text to detect
 * @returns {boolean}
 */
function containsMath(text) {
  // Detect Greek letters
  if (/[αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ]/.test(text)) return true;
  // Detect Unicode subscript/superscript characters
  if (/[₀₁₂₃₄₅₆₇₈₉ₙₓᵢₜₛ⁰¹²³⁴⁵⁶⁷⁸⁹ⁿⁱ]/.test(text)) return true;
  // Detect math operators and special symbols
  if (/[∞∑∏∫≤≥≠≈→←↔∈∉⊂⊃∀∃∧∨×÷±∓·…⋯′″⟨⟩]/.test(text)) return true;
  // Detect starred symbols like π*, Q* (but not plain words like Agent)
  if (/[A-Z]\*/.test(text)) return true;
  // Detect $...$ LaTeX delimiters
  if (/\$[^$]+\$/.test(text)) return true;
  return false;
}

/**
 * ISSUE 8 FIX: Detect if text contains citation [n] format
 */
function containsCitation(text) {
  return /\[\d+\]/.test(text);
}

/**
 * ISSUE 7 FIX: Parse text into TextRun and Math mixed array (for inline formulas)
 * Strict regex - only matches actual math content, not plain numbers or words
 * @param {string} text - Input text
 * @returns {Array} Array of TextRun and Math objects
 */
function parseInlineContent(text) {
  const children = [];
  
  // Regex matching math content blocks (in priority order):
  // 1. $...$  explicit LaTeX (highest priority)
  // 2. Function form Q(s,a) V(s) Rₓ(a) etc. (only with subscripts or specific single letters)
  // 3. Greek letters (alone or with subscripts)
  // 4. Variables with subscripts like Qₙ xₙ αₙ etc.
  // 5. Starred symbols like π* Q* (single letter only)
  // 
  // NOTE: Does NOT match plain English words like Agent, Watkins, Dayan
  // Does NOT match plain numbers like 1992, 500
  // Does NOT match plain parentheses expressions like (1992)
  
  const mathPattern = /\$([^$]+)\$|([A-Z][₀₁₂₃₄₅₆₇₈₉ₙₓᵢₜₛ⁰¹²³⁴⁵⁶⁷⁸⁹ⁿⁱ]+\*?\s*\([^)]+\))|([A-Z]\s*\([^)]*[αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ₀₁₂₃₄₅₆₇₈₉ₙₓᵢₜₛ][^)]*\))|([αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ][₀₁₂₃₄₅₆₇₈₉ₙₓᵢₜₛ⁰¹²³⁴⁵⁶⁷⁸⁹ⁿⁱ]*\*?)|([A-Za-z][₀₁₂₃₄₅₆₇₈₉ₙₓᵢₜₛ⁰¹²³⁴⁵⁶⁷⁸⁹ⁿⁱ]+\*?)|([A-Z]\*)/g;
  
  let lastIndex = 0;
  let match;
  
  while ((match = mathPattern.exec(text)) !== null) {
    // Add plain text before match
    if (match.index > lastIndex) {
      const plainText = text.slice(lastIndex, match.index);
      if (plainText) {
        children.push(new TextRun(plainText));
      }
    }
    
    // Get matched math content
    const mathContent = match[1] || match[2] || match[3] || match[4] || match[5] || match[6];
    if (mathContent) {
      // Convert Unicode to LaTeX and create Math object
      const latex = unicodeToLatex(mathContent);
      try {
        const mathml = temml.renderToString(latex, { displayMode: false, throwOnError: false });
        const mathChildren = mathmlToDocxChildren(mathml);
        if (mathChildren && mathChildren.length) {
          children.push(new Math({ children: mathChildren }));
        } else {
          // fallback
          children.push(new Math({ children: [new MathRun(mathContent)] }));
        }
      } catch (e) {
        // Parse failed, use MathRun to display original text
        children.push(new Math({ children: [new MathRun(mathContent)] }));
      }
    }
    
    lastIndex = match.index + match[0].length;
  }
  
  // Add remaining plain text
  if (lastIndex < text.length) {
    children.push(new TextRun(text.slice(lastIndex)));
  }
  
  // If no math content matched, return plain text
  if (children.length === 0) {
    children.push(new TextRun(text));
  }
  
  return children;
}

/**
 * ISSUE 8 FIX: Parse text with math content and citations
 * Citations [n] are converted to superscript format
 * @param {string} text - Input text
 * @returns {Array} Array of TextRun and Math objects
 */
function parseInlineContentWithCitations(text) {
  const children = [];
  
  // Combined regex: match math content or citations
  // Citations [n] become superscript
  // Math content becomes Math objects
  const combinedPattern = /(\[\d+\])|\$([^$]+)\$|([A-Z][₀₁₂₃₄₅₆₇₈₉ₙₓᵢₜₛ⁰¹²³⁴⁵⁶⁷⁸⁹ⁿⁱ]+\*?\s*\([^)]+\))|([A-Z]\s*\([^)]*[αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ₀₁₂₃₄₅₆₇₈₉ₙₓᵢₜₛ][^)]*\))|([αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ][₀₁₂₃₄₅₆₇₈₉ₙₓᵢₜₛ⁰¹²³⁴⁵⁶⁷⁸⁹ⁿⁱ]*\*?)|([A-Za-z][₀₁₂₃₄₅₆₇₈₉ₙₓᵢₜₛ⁰¹²³⁴⁵⁶⁷⁸⁹ⁿⁱ]+\*?)|([A-Z]\*)/g;
  
  const plainRun = (value, extra = {}) => new TextRun({
    text: value,
    size: 24,
    font: {
      ascii: 'Times New Roman',
      eastAsia: 'SimSun',
      hAnsi: 'Times New Roman',
    },
    ...extra,
  });

  let lastIndex = 0;
  let match;

  while ((match = combinedPattern.exec(text)) !== null) {
    // Add plain text before match
    if (match.index > lastIndex) {
      const plainText = text.slice(lastIndex, match.index);
      if (plainText) {
        children.push(plainRun(plainText));
      }
    }

    if (match[1]) {
      // Citation [n] - convert to superscript
      children.push(plainRun(match[1], { superScript: true }));
    } else {
      // Math content
      const mathContent = match[2] || match[3] || match[4] || match[5] || match[6] || match[7];
      if (mathContent) {
        const latex = unicodeToLatex(mathContent);
        try {
          const mathml = temml.renderToString(latex, { displayMode: false, throwOnError: false });
          const mathChildren = mathmlToDocxChildren(mathml);
          if (mathChildren && mathChildren.length) {
            children.push(new Math({ children: mathChildren }));
          } else {
            children.push(new Math({ children: [new MathRun(mathContent)] }));
          }
        } catch (e) {
          children.push(new Math({ children: [new MathRun(mathContent)] }));
        }
      }
    }
    
    lastIndex = match.index + match[0].length;
  }
  
  // Add remaining plain text
  if (lastIndex < text.length) {
    children.push(plainRun(text.slice(lastIndex)));
  }

  if (children.length === 0) {
    children.push(plainRun(text));
  }

  return children;
}

// ─────────────────────────────────────────────────────────────────────────────
// Helper: body paragraph (首行缩进 2 字符, 单倍行距) - supports inline formulas
// ─────────────────────────────────────────────────────────────────────────────

function makeBodyParagraph(text, overrides = {}) {
  const children = containsMath(text) || containsCitation(text)
    ? parseInlineContentWithCitations(text)
    : [new TextRun({
        text,
        size: 24,
        font: {
          ascii: 'Times New Roman',
          eastAsia: 'SimSun',
          hAnsi: 'Times New Roman',
        },
      })];

  return new Paragraph({
    spacing: { line: 360, lineRule: LineRuleType.AUTO },
    indent: { firstLine: 480 },
    ...overrides,
    children,
  });
}

function body(text) {
  return makeBodyParagraph(text);
}

function bodyIndented(text, left = 0) {
  return makeBodyParagraph(text, {
    indent: { left, firstLine: 0 },
  });
}

function bodyNoIndent(text, overrides = {}) {
  return makeBodyParagraph(text, {
    indent: { firstLine: 0 },
    ...overrides,
  });
}

// Paragraph with multiple TextRuns
function bodyMulti(runs) {
  return new Paragraph({
    children: runs,
  });
}

const INLINE_LATEX_TO_UNICODE = {
  '\\alpha': 'α',
  '\\beta': 'β',
  '\\gamma': 'γ',
  '\\delta': 'δ',
  '\\epsilon': 'ε',
  '\\varepsilon': 'ε',
  '\\zeta': 'ζ',
  '\\eta': 'η',
  '\\theta': 'θ',
  '\\vartheta': 'ϑ',
  '\\iota': 'ι',
  '\\kappa': 'κ',
  '\\lambda': 'λ',
  '\\mu': 'μ',
  '\\nu': 'ν',
  '\\xi': 'ξ',
  '\\pi': 'π',
  '\\rho': 'ρ',
  '\\sigma': 'σ',
  '\\tau': 'τ',
  '\\upsilon': 'υ',
  '\\phi': 'φ',
  '\\varphi': 'φ',
  '\\chi': 'χ',
  '\\psi': 'ψ',
  '\\omega': 'ω',
  '\\Gamma': 'Γ',
  '\\Delta': 'Δ',
  '\\Theta': 'Θ',
  '\\Lambda': 'Λ',
  '\\Xi': 'Ξ',
  '\\Pi': 'Π',
  '\\Sigma': 'Σ',
  '\\Phi': 'Φ',
  '\\Psi': 'Ψ',
  '\\Omega': 'Ω',
  '\\langle': '⟨',
  '\\rangle': '⟩',
  '\\leq': '≤',
  '\\geq': '≥',
  '\\neq': '≠',
  '\\to': '→',
  '\\rightarrow': '→',
  '\\leftarrow': '←',
  '\\cdot': '·',
  '\\times': '×',
  '\\infty': '∞',
};

const SUBSCRIPT_CHARS = {
  '0': '₀',
  '1': '₁',
  '2': '₂',
  '3': '₃',
  '4': '₄',
  '5': '₅',
  '6': '₆',
  '7': '₇',
  '8': '₈',
  '9': '₉',
  '+': '₊',
  '-': '₋',
  '=': '₌',
  '(': '₍',
  ')': '₎',
  'a': 'ₐ',
  'e': 'ₑ',
  'h': 'ₕ',
  'i': 'ᵢ',
  'j': 'ⱼ',
  'k': 'ₖ',
  'l': 'ₗ',
  'm': 'ₘ',
  'n': 'ₙ',
  'o': 'ₒ',
  'p': 'ₚ',
  'r': 'ᵣ',
  's': 'ₛ',
  't': 'ₜ',
  'u': 'ᵤ',
  'v': 'ᵥ',
  'x': 'ₓ',
  'β': 'ᵦ',
  'γ': 'ᵧ',
  'ρ': 'ᵨ',
  'φ': 'ᵩ',
  'χ': 'ᵪ',
};

const SUPERSCRIPT_CHARS = {
  '0': '⁰',
  '1': '¹',
  '2': '²',
  '3': '³',
  '4': '⁴',
  '5': '⁵',
  '6': '⁶',
  '7': '⁷',
  '8': '⁸',
  '9': '⁹',
  '+': '⁺',
  '-': '⁻',
  '=': '⁼',
  '(': '⁽',
  ')': '⁾',
  'i': 'ⁱ',
  'n': 'ⁿ',
};

function convertCharsWithMap(text, mapping) {
  return [...text].map((char) => mapping[char] || char).join('');
}

function unwrapLatexTextCommands(text) {
  let result = text;
  let previous = '';

  while (result !== previous) {
    previous = result;
    result = result.replace(
      /\\(?:mathrm|mathbf|mathit|text|operatorname)\{([^{}]*)\}/g,
      '$1'
    );
  }

  return result;
}

function simplifyInlineLatex(latex) {
  let text = latex.trim();
  text = unwrapLatexTextCommands(text);

  for (const [command, replacement] of Object.entries(INLINE_LATEX_TO_UNICODE)) {
    text = text.split(command).join(replacement);
  }

  text = text
    .replace(/\\left/g, '')
    .replace(/\\right/g, '')
    .replace(/\\,/g, ' ')
    .replace(/\\;/g, ' ')
    .replace(/\\!/g, '')
    .replace(/\\ /g, ' ')
    .replace(/\\\{/g, '{')
    .replace(/\\\}/g, '}');

  text = text
    .replace(/_\{([^{}]+)\}/g, (_, group) => convertCharsWithMap(group, SUBSCRIPT_CHARS))
    .replace(/_([A-Za-z0-9+\-=()α-ωΑ-Ω])/g, (_, group) => convertCharsWithMap(group, SUBSCRIPT_CHARS))
    .replace(/\^\{([^{}]+)\}/g, (_, group) => group === '*' ? '*' : convertCharsWithMap(group, SUPERSCRIPT_CHARS))
    .replace(/\^([A-Za-z0-9+\-=()α-ωΑ-Ω*])/g, (_, group) => group === '*' ? '*' : convertCharsWithMap(group, SUPERSCRIPT_CHARS));

  text = text
    .replace(/[{}]/g, '')
    .replace(/\s+/g, ' ')
    .trim();

  return text;
}

function buildInlineMathRuns(text, options = {}) {
  const {
    bold = false,
    normalEastAsia = 'SimSun',
    normalItalic = false,
    mathItalic = true,
    size = 24,
  } = options;

  const runs = [];
  const pattern = /\$([^$]+)\$/g;
  let lastIndex = 0;
  let match;

  const normalRun = (value) => new TextRun({
    text: value,
    bold,
    italics: normalItalic,
    size,
    font: { ascii: 'Times New Roman', eastAsia: normalEastAsia, hAnsi: 'Times New Roman' },
  });

  const mathRun = (value) => new TextRun({
    text: simplifyInlineLatex(value),
    bold,
    italics: mathItalic,
    size,
    font: { ascii: 'Times New Roman', eastAsia: normalEastAsia, hAnsi: 'Times New Roman' },
  });

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      runs.push(normalRun(text.slice(lastIndex, match.index)));
    }

    if (match[1].trim()) {
      runs.push(mathRun(match[1]));
    }

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    runs.push(normalRun(text.slice(lastIndex)));
  }

  if (runs.length === 0) {
    runs.push(normalRun(text));
  }

  return runs;
}

function plainHeading(level, text, size = 24) {
  return new Paragraph({
    heading: level,
    indent: { firstLine: 0 },
    keepNext: true,
    children: buildInlineMathRuns(text, {
      bold: true,
      normalEastAsia: 'SimSun',
      size,
    }),
  });
}

function centeredText(text, options = {}) {
  const {
    size = 24,
    bold = false,
    spacing = { before: 0, after: 120 },
  } = options;

  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing,
    indent: { firstLine: 0 },
    children: [new TextRun({
      text,
      bold,
      size,
      font: { ascii: 'Times New Roman', eastAsia: 'SimSun', hAnsi: 'Times New Roman' },
    })],
  });
}

function bullet(text) {
  return new Paragraph({
    numbering: { reference: 'bullets', level: 0 },
    children: containsMath(text) || containsCitation(text)
      ? parseInlineContentWithCitations(text)
      : [new TextRun(text)],
  });
}

function parseHtmlTable(html) {
  const rowMatches = [...html.matchAll(/<tr>(.*?)<\/tr>/gsi)];
  const rows = rowMatches.map((rowMatch) => {
    const cellMatches = [...rowMatch[1].matchAll(/<t[dh]>(.*?)<\/t[dh]>/gsi)];
    return cellMatches.map((cellMatch) =>
      cellMatch[1]
        .replace(/<[^>]+>/g, '')
        .replace(/&nbsp;/g, ' ')
        .trim()
    );
  }).filter((row) => row.length);

  if (rows.length < 2) {
    throw new Error('HTML table requires at least one header row and one body row');
  }

  return {
    headers: rows[0],
    rows: rows.slice(1),
  };
}

function normalizeCaptionText(text) {
  return text
    .replace(/^([\u56fe\u8868])(\d)/, '$1 $2')
    .replace(/\s+/g, ' ')
    .trim();
}

function getImageType(imagePath) {
  const ext = path.extname(imagePath).toLowerCase();
  if (ext === '.jpg') return 'jpg';
  if (ext === '.jpeg') return 'jpeg';
  if (ext === '.png') return 'png';
  if (ext === '.gif') return 'gif';
  if (ext === '.bmp') return 'bmp';
  throw new Error(`Unsupported image format: ${imagePath}`);
}

function getImageDimensions(buffer, imagePath) {
  const ext = path.extname(imagePath).toLowerCase();

  if (ext === '.png') {
    return {
      width: buffer.readUInt32BE(16),
      height: buffer.readUInt32BE(20),
    };
  }

  if (ext === '.jpg' || ext === '.jpeg') {
    let offset = 2;
    while (offset < buffer.length) {
      if (buffer[offset] !== 0xFF) {
        offset += 1;
        continue;
      }
      const marker = buffer[offset + 1];
      const length = buffer.readUInt16BE(offset + 2);
      if (marker >= 0xC0 && marker <= 0xC3) {
        return {
          height: buffer.readUInt16BE(offset + 5),
          width: buffer.readUInt16BE(offset + 7),
        };
      }
      offset += 2 + length;
    }
  }

  throw new Error(`Unable to read image dimensions: ${imagePath}`);
}

function imageBlock(imagePath) {
  const data = fs.readFileSync(imagePath);
  const { width, height } = getImageDimensions(data, imagePath);
  const maxWidth = 540;
  const maxHeight = 410;
  const scale = globalThis.Math.min(maxWidth / width, maxHeight / height, 1);

  return new Paragraph({
    alignment: AlignmentType.CENTER,
    indent: { firstLine: 0 },
    spacing: { before: 120, after: 60 },
    keepNext: true,
    children: [new ImageRun({
      type: getImageType(imagePath),
      data,
      transformation: {
        width: globalThis.Math.round(width * scale),
        height: globalThis.Math.round(height * scale),
      },
      altText: {
        title: path.basename(imagePath),
        description: path.basename(imagePath),
        name: path.basename(imagePath),
      },
    })],
  });
}

function parseFormulaBlock(lines, startIndex) {
  const formulaLines = [];
  let i = startIndex + 1;
  while (i < lines.length && lines[i].trim() !== '$$') {
    formulaLines.push(lines[i]);
    i += 1;
  }

  const rawLatex = formulaLines.join(' ').trim();
  const tagMatch = rawLatex.match(/\\tag\{([^}]+)\}\s*$/);
  const number = tagMatch ? tagMatch[1] : '';
  const latex = tagMatch ? rawLatex.slice(0, tagMatch.index).trim() : rawLatex;

  return {
    block: formula(latex, number),
    nextIndex: i,
  };
}

function buildContentFromMarkdown(markdownPath) {
  const raw = fs.readFileSync(markdownPath, 'utf8');
  const lines = raw.split(/\r?\n/);
  const content = [];
  const baseDir = path.dirname(markdownPath);
  let i = 0;
  let inReferences = false;
  let abstractInserted = false;
  let generatedToc = false;
  let mainHeadingCount = 0;

  const flushParagraph = (paragraphLines) => {
    if (!paragraphLines.length) return;
    const rawText = paragraphLines.join(' ').replace(/\s+/g, ' ').trim();
    if (!rawText) return;

    const leadingTabs = (paragraphLines[0].match(/^\t+/) || [''])[0].length;
    const leadingSpaces = (paragraphLines[0].match(/^ +/) || [''])[0].length;
    const left = leadingTabs > 0 ? leadingTabs * 420 : (leadingSpaces >= 4 ? 420 : 0);
    content.push(left > 0 ? bodyIndented(rawText, left) : body(rawText));
  };

  while (i < lines.length) {
    const rawLine = lines[i];
    const line = rawLine.trim();

    if (!line) {
      i += 1;
      continue;
    }

    if (line === '## \u76ee\u5f55') {
      i += 1;
      while (i < lines.length && !lines[i].startsWith('# ')) {
        i += 1;
      }
      continue;
    }

    if (line.startsWith('# ')) {
      content.push(centeredText(line.slice(2).trim(), {
        size: 44,
        bold: true,
        spacing: { before: 0, after: 240 },
      }));
      i += 1;
      continue;
    }

    if (/^##\s+.+\(name\)\s*$/.test(line)) {
      content.push(centeredText(line.replace(/^##\s+/, ''), {
        size: 24,
        spacing: { before: 0, after: 180 },
      }));
      i += 1;
      continue;
    }

    if (/^##\s*\u6458\u8981[:\uff1a]?\s*$/.test(line)) {
      content.push(centeredText('\u6458\u8981', { bold: true, spacing: { before: 0, after: 120 } }));
      i += 1;
      abstractInserted = true;
      continue;
    }

    if (/^\u5173\u952e\u8bcd[:\uff1a]/.test(line)) {
      content.push(new Paragraph({
        indent: { firstLine: 0 },
        children: [
          new TextRun({ text: '\u5173\u952e\u8bcd\uff1a', bold: true }),
          ...parseInlineContentWithCitations(line.replace(/^\u5173\u952e\u8bcd[:\uff1a]\s*/, '')),
        ],
      }));
      if (abstractInserted && !generatedToc) {
        content.push(pageBreak());
        content.push(new TableOfContents('\u76ee\u5f55', { hyperlink: true, headingStyleRange: '1-3' }));
        // \u524d\u7f6e\u90e8\u5206\uff08\u9898\u76ee+\u6458\u8981+\u5173\u952e\u8bcd+\u76ee\u5f55\uff09\u5230\u6b64\u4e3a\u6b62\uff1b\u6b64\u540e\u7684\u5185\u5bb9\u53e6\u8d77\u4e00\u8282\uff0c
        // \u9875\u7801\u91cd\u65b0\u4ece\u963f\u62c9\u4f2f\u6570\u5b57 1 \u5f00\u59cb\u3002\u5206\u8282\u7b26\u672c\u8eab\u4f1a\u53e6\u8d77\u4e00\u9875\uff0c\u6545\u6b64\u5904\u4e0d\u518d\u63d2\u5206\u9875\u7b26\u3002
        _frontMatterSplitAt = content.length;
        generatedToc = true;
      }
      i += 1;
      continue;
    }

    if (line.startsWith('```')) {
      const codeLines = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i]);
        i += 1;
      }
      content.push(codeBlock(codeLines.join('\n')));
      i += 1;
      continue;
    }

    if (line === '$$') {
      const { block, nextIndex } = parseFormulaBlock(lines, i);
      content.push(block);
      i = nextIndex + 1;
      continue;
    }

    const imageMatch = line.match(/^!\[[^\]]*]\(([^)]+)\)$/);
    if (imageMatch) {
      const imagePath = path.resolve(baseDir, imageMatch[1]);
      content.push(imageBlock(imagePath));
      let j = i + 1;
      while (j < lines.length && !lines[j].trim()) {
        j += 1;
      }
      if (j < lines.length && /^\u56fe/.test(lines[j].trim())) {
        content.push(figCaption(normalizeCaptionText(lines[j].trim())));
        i = j + 1;
      } else {
        i += 1;
      }
      continue;
    }

    if (line.startsWith('<table>')) {
      const { headers, rows } = parseHtmlTable(line);
      if (content.length && i > 0 && /^\u8868/.test(lines[i - 1].trim())) {
        content.pop();
        content.push(tableCaption(normalizeCaptionText(lines[i - 1].trim())));
      }
      const columnWidths = headers.length === 2
        ? [1800, CONTENT_W - 1800]
        : Array(headers.length).fill(globalThis.Math.floor(CONTENT_W / headers.length));
      if (headers.length > 2) {
        columnWidths[columnWidths.length - 1] = CONTENT_W - columnWidths.slice(0, -1).reduce((sum, n) => sum + n, 0);
      }
      content.push(threeLineTable(headers, rows, columnWidths));
      i += 1;
      continue;
    }

    if (line === '---') {
      i += 1;
      continue;
    }

    if (/^##\s+\u53c2\u8003\u6587\u732e\s*$/.test(line)) {
      inReferences = true;
      // \u7528 pageBreakBefore \u800c\u975e\u72ec\u7acb\u7684\u5206\u9875\u6bb5\u843d\uff1a\u540e\u8005\u5728\u4e0a\u4e00\u9875\u6070\u597d\u6392\u6ee1\u65f6\u4f1a
      // \u81ea\u5df1\u5360\u636e\u4e00\u6574\u9875\uff0c\u4ea7\u751f\u7a7a\u767d\u9875\uff08\u539f\u811a\u672c\u7684\u5df2\u77e5\u95ee\u9898\uff09
      content.push(new Paragraph({
        heading: HeadingLevel.HEADING_1,
        pageBreakBefore: true,
        indent: { firstLine: 0 },
        keepNext: true,
        children: buildInlineMathRuns('\u53c2\u8003\u6587\u732e',
          { bold: true, normalEastAsia: 'SimSun', size: 32 }),
      }));
      i += 1;
      continue;
    }

    if (/^##\s+\u9644\u5f55\s*$/.test(line)) {
      content.push(new Paragraph({
        heading: HeadingLevel.HEADING_1,
        pageBreakBefore: true,
        indent: { firstLine: 0 },
        keepNext: true,
        children: buildInlineMathRuns('\u9644\u5f55',
          { bold: true, normalEastAsia: 'SimSun', size: 32 }),
      }));
      inReferences = false;
      i += 1;
      continue;
    }

    if (/^##\s+/.test(line)) {
      const text = line.replace(/^##\s+/, '').trim();
      if (/^[\u4e00-\u5341]+\u3001/.test(text)) {
        // \u7ae0\u8282\u4e4b\u95f4\u4e0d\u5f3a\u5236\u5206\u9875\uff1a\u4e0e\u8bfe\u7a0b\u300a\u683c\u5f0f\u53c2\u8003.docx\u300b\u7684\u6392\u7248\u4e00\u81f4\uff0c
        // \u4e5f\u907f\u514d\u77ed\u7ae0\u8282\u4ea7\u751f\u5927\u91cf\u7a7a\u767d\u9875\uff08\u89c1 build \u8bf4\u660e\uff09\u3002
        mainHeadingCount += 1;
      }
      if (CAMPUS_TEMPLATE) {
        content.push(plainHeading(HeadingLevel.HEADING_2, text, 32));
      } else {
        content.push(plainHeading(HeadingLevel.HEADING_1, text, 32));
      }
      inReferences = false;
      i += 1;
      continue;
    }

    if (/^###\s+/.test(line)) {
      const text = line.replace(/^###\s+/, '').trim();
      if (CAMPUS_TEMPLATE) {
        content.push(plainHeading(HeadingLevel.HEADING_3, text, 28));
      } else {
        content.push(plainHeading(HeadingLevel.HEADING_2, text, 28));
      }
      i += 1;
      continue;
    }

    if (/^####\s+/.test(line)) {
      const text = line.replace(/^####\s+/, '').trim();
      if (CAMPUS_TEMPLATE) {
        content.push(plainHeading(HeadingLevel.HEADING_4, text, 24));
      } else {
        content.push(plainHeading(HeadingLevel.HEADING_3, text, 24));
      }
      i += 1;
      continue;
    }

    if (/^\[\d+\]\s+/.test(line) && inReferences) {
      content.push(ref(line.trim()));
      i += 1;
      continue;
    }

    if (/^- /.test(line)) {
      content.push(bullet(line.replace(/^- /, '').trim()));
      i += 1;
      continue;
    }

    const paragraphLines = [rawLine];
    let j = i + 1;
    while (j < lines.length) {
      const nextLine = lines[j];
      const nextTrimmed = nextLine.trim();
      if (
        !nextTrimmed ||
        nextTrimmed === '$$' ||
        nextTrimmed === '---' ||
        nextTrimmed.startsWith('```') ||
        /^#/.test(nextTrimmed) ||
        /^!\[/.test(nextTrimmed) ||
        nextTrimmed.startsWith('<table>') ||
        /^- /.test(nextTrimmed) ||
        (/^\[\d+\]\s+/.test(nextTrimmed) && inReferences)
      ) {
        break;
      }
      paragraphLines.push(nextLine);
      j += 1;
    }
    flushParagraph(paragraphLines);
    i = j;
  }

  return content;
}

// ?????????????????????????????????????????????????????????????????????????????
// ISSUE 3 FIX: Manual heading numbering for synchronized counters
// ?????????????????????????????????????????????????????????????????????????????

/** Reset heading counters (call at start of document) */
function resetHeadingCounters() {
  currentChapter = 0;
  currentSection = 0;
  currentSubsection = 0;
}

/** H1 - Level 1 heading (manual Chinese numbering: 一、二、三) */
function h1Manual(text) {
  currentChapter++;
  currentSection = 0;
  currentSubsection = 0;
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    indent: { firstLine: 0 },
    children: buildInlineMathRuns(text, { bold: true, normalEastAsia: 'SimSun' }),
  });
}

/** H1 with auto-numbering (→ 1  2  3) - use when you want Arabic numerals */
function h1(text) {
  currentChapter++;
  currentSection = 0;
  currentSubsection = 0;
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    indent: { firstLine: 0 },
    children: [
      new TextRun({
        text: `${currentChapter} `,
        bold: true,
        font: { ascii: 'Times New Roman', eastAsia: 'SimSun', hAnsi: 'Times New Roman' },
      }),
      ...buildInlineMathRuns(text, { bold: true, normalEastAsia: 'SimSun' }),
    ],
  });
}

/** H2 - Level 2 heading (manual numbering: chapter.section, e.g., 1.1, 2.3) */
function h2(text) {
  currentSection++;
  currentSubsection = 0;
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    indent: { firstLine: 0 },
    children: [
      new TextRun({
        text: `${currentChapter}.${currentSection} `,
        bold: true,
        font: { ascii: 'Times New Roman', eastAsia: 'SimSun', hAnsi: 'Times New Roman' },
      }),
      ...buildInlineMathRuns(text, { bold: true, normalEastAsia: 'SimSun' }),
    ],
  });
}

/** H3 - Level 3 heading (manual numbering: chapter.section.subsection, e.g., 1.1.1) */
function h3(text) {
  currentSubsection++;
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    indent: { firstLine: 0 },
    children: [
      new TextRun({
        text: `${currentChapter}.${currentSection}.${currentSubsection} `,
        bold: true,
        font: { ascii: 'Times New Roman', eastAsia: 'SimSun', hAnsi: 'Times New Roman' },
      }),
      ...buildInlineMathRuns(text, { bold: true, normalEastAsia: 'SimSun' }),
    ],
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Helper: captions - ISSUE 4 FIX: Mixed fonts for English/numbers
// ─────────────────────────────────────────────────────────────────────────────

/** Figure caption (below figure). label e.g. "图 1-1 系统架构" */
function figCaption(label) {
  return new Paragraph({
    style: 'FigureCaption',
    children: buildInlineMathRuns(label, {
      bold: true,
      normalEastAsia: 'SimSun',
      size: 21,
    }),
  });
}

/** Table caption (above table). label e.g. "表 1-1 符号说明" */
function tableCaption(label) {
  return new Paragraph({
    style: 'TableCaption',
    keepNext: true,
    children: buildInlineMathRuns(label, {
      bold: true,
      normalEastAsia: 'SimSun',
      size: 21,
    }),
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// ISSUE 1 FIX: 三线表 (three-line table) with proper border handling
// Body row borders must be NONE (not just thin), only:
// - Header top: THICK
// - Header bottom: THIN
// - Last row bottom: THICK
// ─────────────────────────────────────────────────────────────────────────────

function threeLineTable(headers, rows, colWidths) {
  const n = headers.length;

  // Default: equal column widths
  if (!colWidths) {
    const w = globalThis.Math.floor(CONTENT_W / n);
    colWidths = Array(n).fill(w);
    colWidths[n - 1] = CONTENT_W - w * (n - 1);
  }

  if (colWidths.length !== n) throw new Error('colWidths length must match headers length');

  // Table cells are rendered as plain text: inline OMML conversion can drop
  // symbols such as · or ≈, leaving visually empty cells.  Unicode text is
  // sufficient for the symbol/complexity tables.
  const cellOf = (text, w, borders, bold = false, align = AlignmentType.CENTER) => {
    const runFont = {
      ascii: 'Times New Roman',
      eastAsia: 'SimSun',
      hAnsi: 'Times New Roman',
    };
    const cellChildren = [new TextRun({
      text,
      bold,
      size: TABLE_FONT_SIZE,
      font: runFont,
    })];

    return new TableCell({
      width:   { size: w, type: WidthType.DXA },
      borders,
      shading: { fill: 'FFFFFF', type: ShadingType.CLEAR },
      margins: { top: 40, bottom: 40, left: 100, right: 100 },
      children: [new Paragraph({
        alignment: align,
        indent:    { firstLine: 0 },
        spacing:   { line: 240, lineRule: LineRuleType.AUTO },
        children:  cellChildren,
      })],
    });
  };

  // Header row: thick top, thin bottom, no sides
  const headerRow = new TableRow({
    tableHeader: true,
    cantSplit: true,
    children: headers.map((h, i) =>
      cellOf(h, colWidths[i], { top: THICK, bottom: THIN, left: NONE, right: NONE }, true)
    ),
  });

  // Body rows: NO borders except last gets thick bottom
  // ISSUE 1 FIX: All body row borders are NONE, only last row bottom is THICK
  const bodyRows = rows.map((row, ri) => {
    const isLast = ri === rows.length - 1;
    return new TableRow({
      cantSplit: true,
      children: row.map((cell, i) =>
        cellOf(
          String(cell),
          colWidths[i],
          {
            top:    NONE,
            bottom: isLast ? THICK : NONE,
            left:   NONE,
            right:  NONE,
          },
          false,
          i === 0 ? AlignmentType.LEFT : AlignmentType.CENTER
        )
      ),
    });
  });

  return new Table({
    width:        { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: colWidths,
    rows:         [headerRow, ...bodyRows],
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Helper: fenced code block (Consolas 9 pt, light grey background)
// ─────────────────────────────────────────────────────────────────────────────

function codeBlock(code) {
  const font = {
    ascii: 'Consolas',
    eastAsia: 'SimSun',
    hAnsi: 'Consolas',
  };
  const paragraphs = code.split(/\r?\n/).map((line) => new Paragraph({
    indent: { firstLine: 0 },
    spacing: { line: 240, lineRule: LineRuleType.AUTO },
    children: [new TextRun({
      text: line || ' ',
      font,
      size: 18,
    })],
  }));
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [CONTENT_W],
    borders: {
      top: THIN,
      bottom: THIN,
      left: THIN,
      right: THIN,
      insideHorizontal: NONE,
      insideVertical: NONE,
    },
    rows: [new TableRow({
      children: [new TableCell({
        width: { size: CONTENT_W, type: WidthType.DXA },
        shading: { fill: 'F7F7F7', type: ShadingType.CLEAR },
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: paragraphs,
      })],
    })],
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Helper: reference entry (GB/T 7714-2015)
// ─────────────────────────────────────────────────────────────────────────────

function ref(text) {
  return new Paragraph({
    style: 'Reference',
    indent: { left: 480, hanging: 480, firstLine: 0 },
    spacing: { line: 240, lineRule: LineRuleType.AUTO },
    children: [new TextRun({
      text,
      size: 21,
      font: {
        ascii: 'Times New Roman',
        eastAsia: 'SimSun',
        hAnsi: 'Times New Roman',
      },
    })],
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Helper: empty paragraph (spacing)
// ─────────────────────────────────────────────────────────────────────────────

function blank() {
  return new Paragraph({ children: [] });
}

// ─────────────────────────────────────────────────────────────────────────────
// ISSUE 10 FIX: Page break helper
// Insert after abstract/keywords, and before references section
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Create a page break paragraph
 * Use after keywords section and before references section
 * @returns {Paragraph} Paragraph containing a page break
 */
function pageBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}


// ─────────────────────────────────────────────────────────────────────────────
// ISSUE 5 FIX: Block formula using temml + mathmlToDocxChildren (Word native math)
// ISSUE 2 FIX: Formula table borders all set to NONE including insideHorizontal/insideVertical
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Convert LaTeX formula to docx Math component
 * @param {string} latex - LaTeX formula string
 * @returns {Math} docx Math object
 */
function latexToMath(latex) {
  try {
    const mathml = temml.renderToString(latex, { displayMode: true, throwOnError: false });
    const children = mathmlToDocxChildren(mathml);
    if (children && children.length) {
      return new Math({ children });
    }
  } catch (e) {
    console.warn(`[formula] LaTeX parse error: ${latex}`, e.message);
  }
  // Fallback: return plain text
  return new Math({ children: [new MathRun(latex)] });
}

/**
 * Block formula layout using 3-column borderless table
 * ISSUE 2 FIX: All borders including insideHorizontal/insideVertical set to NONE
 * @param {string} latex - LaTeX formula string
 * @param {number|string} number - Equation number
 * @returns {Table} Formula table
 */
function formula(latex, number) {
  // Use 3-column borderless table layout: left margin | centered formula | right-aligned number
  const noBorders = { top: NONE, bottom: NONE, left: NONE, right: NONE };
  
  const leftCell = new TableCell({
    width: { size: 567, type: WidthType.DXA },
    borders: noBorders,
    shading: { fill: 'FFFFFF', type: ShadingType.CLEAR },
    verticalAlign: VerticalAlign.CENTER,  // ISSUE 11 FIX: Center content vertically
    children: [new Paragraph({ indent: { firstLine: 0 }, children: [] })],
  });
  
  // Use temml + mathmlToDocxChildren to create Word native formula
  const mathObj = latexToMath(latex);
  const formulaCell = new TableCell({
    width: { size: 7936, type: WidthType.DXA },
    borders: noBorders,
    shading: { fill: 'FFFFFF', type: ShadingType.CLEAR },
    verticalAlign: VerticalAlign.CENTER,  // ISSUE 11 FIX: Center content vertically
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      indent: { firstLine: 0 },
      children: [mathObj],
    })],
  });
  
  const numberCell = new TableCell({
    width: { size: 567, type: WidthType.DXA },
    borders: noBorders,
    shading: { fill: 'FFFFFF', type: ShadingType.CLEAR },
    verticalAlign: VerticalAlign.CENTER,  // ISSUE 11 FIX: Center content vertically
    children: [new Paragraph({
      alignment: AlignmentType.RIGHT,
      indent: { firstLine: 0 },
      children: [new TextRun(`(${number})`)],
    })],
  });
  
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [567, 7936, 567],
    // ISSUE 2 FIX: Include insideHorizontal and insideVertical as NONE
    borders: {
      top: NONE,
      bottom: NONE,
      left: NONE,
      right: NONE,
      insideHorizontal: NONE,
      insideVertical: NONE,
    },
    rows: [new TableRow({
      cantSplit: true,
      children: [leftCell, formulaCell, numberCell],
    })],
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Document structure: styles + numbering
// ISSUE 4/6 FIX: Mixed fonts for headings/captions (Cambria Math for English/numbers)
// ─────────────────────────────────────────────────────────────────────────────

const STYLES = {
  default: {
    document: {
      // English/math: Cambria Math. Substitute "Times New Roman" if preferred.
      run: {
        font: { ascii: 'Times New Roman', hAnsi: 'Times New Roman', eastAsia: 'SimSun' },
        size: 24,  // 12pt (half-points)
      },
      // Line spacing: 1.3x（line=312），与课程《格式参考.docx》正文实测值一致
      // （该文档正文段落实测为 line=360 与 line=312 混用，此处取 312 以兼顾篇幅）
      paragraph: {
        spacing: { line: 360, lineRule: LineRuleType.AUTO },
        indent:  { firstLine: 480 },  // 2-character indent
      },
    },
  },
  paragraphStyles: [
    {
      // ISSUE 4/6 FIX: Heading fonts use Cambria Math for ascii/hAnsi, SimHei for eastAsia
      id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
      run: { font: { ascii: 'Times New Roman', eastAsia: 'SimSun', hAnsi: 'Times New Roman' }, size: 32, bold: true },
      paragraph: {
        alignment:    AlignmentType.CENTER,
        indent:       { firstLine: 0 },
        spacing:      { line: 288, lineRule: LineRuleType.AUTO },
        outlineLevel: 0,
      },
    },
    {
      id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
      run: { font: { ascii: 'Times New Roman', eastAsia: 'SimSun', hAnsi: 'Times New Roman' }, size: 32, bold: true },
      paragraph: {
        alignment:    AlignmentType.CENTER,
        indent:       { firstLine: 0 },
        spacing:      { before: 120, after: 120, line: 360, lineRule: LineRuleType.AUTO },
        outlineLevel: 1,
      },
    },
    {
      id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
      run: { font: { ascii: 'Times New Roman', eastAsia: 'SimSun', hAnsi: 'Times New Roman' }, size: 28, bold: true },
      paragraph: {
        alignment:    AlignmentType.LEFT,
        indent:       { firstLine: 0 },
        spacing:      { before: 120, after: 120, line: 360, lineRule: LineRuleType.AUTO },
        outlineLevel: 2,
      },
    },
    {
      id: 'Heading4', name: 'Heading 4', basedOn: 'Normal', next: 'Normal', quickFormat: true,
      run: { font: { ascii: 'Times New Roman', eastAsia: 'SimSun', hAnsi: 'Times New Roman' }, size: 24, bold: true },
      paragraph: {
        alignment:    AlignmentType.LEFT,
        indent:       { firstLine: 0 },
        spacing:      { before: 120, after: 120, line: 360, lineRule: LineRuleType.AUTO },
        outlineLevel: 3,
      },
    },
    {
      // ISSUE 4 FIX: Figure/Table captions use Cambria Math for English/numbers
      id: 'FigureCaption', name: 'Figure Caption', basedOn: 'Normal',
      run: { font: { ascii: 'Times New Roman', eastAsia: 'SimSun', hAnsi: 'Times New Roman' }, size: 21, bold: true },
      paragraph: {
        alignment: AlignmentType.CENTER,
        indent:    { firstLine: 0 },
        spacing:   { before: 120, after: 60, line: 240, lineRule: LineRuleType.AUTO },
      },
    },
    {
      id: 'TableCaption', name: 'Table Caption', basedOn: 'Normal',
      run: { font: { ascii: 'Times New Roman', eastAsia: 'SimSun', hAnsi: 'Times New Roman' }, size: 21, bold: true },
      paragraph: {
        alignment: AlignmentType.CENTER,
        indent:    { firstLine: 0 },
        spacing:   { before: 120, after: 60, line: 240, lineRule: LineRuleType.AUTO },
      },
    },
    {
      id: 'Reference', name: 'Reference', basedOn: 'Normal',
      run: { font: { ascii: 'Times New Roman', hAnsi: 'Times New Roman', eastAsia: 'SimSun' }, size: 21 },
      paragraph: {
        spacing: { line: 240, lineRule: LineRuleType.AUTO },
        indent:  { left: 480, hanging: 480, firstLine: 0 },
      },
    },
  ],
};

const NUMBERING = {
  config: [
    {
      reference: 'references',
      levels: [
        { level: 0, format: LevelFormat.DECIMAL, text: '[%1]',
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 480, hanging: 480 } } } },
      ],
    },
    {
      reference: 'bullets',
      levels: [
        { level: 0, format: LevelFormat.BULLET, text: '•',
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
      ],
    },
    {
      reference: 'numbers',
      levels: [
        { level: 0, format: LevelFormat.DECIMAL, text: '%1.',
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
      ],
    },
  ],
};

// ─────────────────────────────────────────────────────────────────────────────
// ██  CONTENT SECTION — Edit below this line  ████████████████████████████████
// ─────────────────────────────────────────────────────────────────────────────

// Reset counters before building content
resetHeadingCounters();

const CONTENT = INPUT_MARKDOWN
  ? buildContentFromMarkdown(INPUT_MARKDOWN)
  : [
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing:   { before: 0, after: 240 },
        indent:    { firstLine: 0 },
        children:  [new TextRun({ text: '????', bold: true, size: 36,
                                  font: { ascii: 'Times New Roman', eastAsia: 'SimSun', hAnsi: 'Times New Roman' } })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        indent:    { firstLine: 0 },
        children:  [new TextRun({ text: '??', bold: true })],
      }),
      body('???????????Q-learning????????????????'),
      new Paragraph({
        indent:    { firstLine: 0 },
        children:  [
          new TextRun({ text: '\u5173\u952e\u8bcd\uff1a', bold: true }),
          new TextRun('?????Q-learning?????????'),
        ],
      }),
      pageBreak(),
      h1Manual('????'),
      blank(),
      body('?????Reinforcement Learning??????????????'),
      h2('????'),
      blank(),
      body('??????????????????[1][2]'),
      h3('????'),
      blank(),
      body('?????????????????'),
      blank(),
      body('Q-Learning ??????:'),
      blank(),
      formula('Q_n(x, a) = (1 - \\alpha_n) Q_{n-1}(x, a) + \\alpha_n [r_n + \\gamma V_{n-1}(y_n)]', 1),
      blank(),
      blank(),
      tableCaption('? 1-1 ????'),
      threeLineTable(
        ['??', '??'],
        [
          ['S',   '????????????????'],
          ['A',   '?????????????????'],
          ['Q?(x,a)', 'Q?????n??????x???a???'],
        ],
        [1800, 7270]
      ),
      blank(),
      h1Manual('????'),
      blank(),
      body('????????? Q-learning ???'),
      pageBreak(),
      new Paragraph({
        heading: HeadingLevel.HEADING_1,
        indent:  { firstLine: 0 },
        children: [new TextRun('????')],
      }),
      blank(),
      ref('Watkins C J C H, Dayan P. Q-learning[J]. Machine learning, 1992, 8(3): 279-292.'),
      ref('Sutton R S, Barto A G. Reinforcement Learning: An Introduction[M]. 2nd ed. Cambridge: MIT Press, 2018.'),
    ];

// ?????????????????????????????????????????????????????????????????????????????
// Build & write document
// ─────────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// 封面：按课程《封面--项目管理论文.docx》逐行还原
// 姓名 / 学号 / 专业班级 / 日期 保留占位符，由作者本人填写
// ─────────────────────────────────────────────────────────────────────────────

const COVER_TITLE = '大型公共信息系统的IT项目管理研究';
const COVER_SUB   = '——以铁路12306客票系统架构演进为例';

function coverLine(text, opts = {}) {
  const {
    size = 32,
    font = 'SimSun',
    left = 0,
    bold = false,
    align = null,
    spacing = { before: 0, after: 0, line: 240, lineRule: LineRuleType.AUTO },
  } = opts;
  return new Paragraph({
    alignment: align || (left > 0 ? AlignmentType.LEFT : AlignmentType.CENTER),
    indent: { firstLine: 0, left },
    spacing,
    children: [new TextRun({
      text,
      size,
      bold,
      font: { ascii: 'Times New Roman', eastAsia: font, hAnsi: 'Times New Roman' },
    })],
  });
}

const coverBlank = (n = 1) => Array.from({ length: n }, () => coverLine('', { size: 24 }));

function coverContent() {
  return [
    ...coverBlank(3),
    coverLine('2026 — 2027 学年第 1 学期', { size: 44, font: 'FangSong' }),
    ...coverBlank(3),
    coverLine('河南理工大学物理与电子信息学院', { size: 30 }),
    coverLine('《项目管理》课程论文', { size: 30 }),
    ...coverBlank(4),
    coverLine(COVER_TITLE, { size: 44, font: 'SimSun', bold: true }),
    coverLine(COVER_SUB, { size: 28, font: 'SimSun' }),
    ...coverBlank(5),
    coverLine(`题    目      ${COVER_TITLE}`, { size: 32, left: 900 }),
    coverLine('学生姓名      XXXX', { size: 32, left: 900 }),
    coverLine('学    号      XXXXXXXX', { size: 32, left: 900 }),
    coverLine('专业班级      XXXXXXXX', { size: 32, left: 900 }),
    ...coverBlank(2),
    coverLine('20XX 年 X 月 X 日', { size: 32, left: 900 }),
  ];
}

// ─────────────────────────────────────────────────────────────────────────────
// 封底：课程论文评分标准（按 装订封底--课程论文评分表 原表还原）
// ─────────────────────────────────────────────────────────────────────────────

const RUBRIC_BOX = { style: BorderStyle.SINGLE, size: 6, color: '000000' };
const RUBRIC_BORDERS = {
  top: RUBRIC_BOX, bottom: RUBRIC_BOX, left: RUBRIC_BOX, right: RUBRIC_BOX,
  insideHorizontal: RUBRIC_BOX, insideVertical: RUBRIC_BOX,
};

const RUBRIC_WIDTHS = [1150, 640, 2756, 620, 620, 620, 620, 620, 660];

function rubricCell(text, width, opts = {}) {
  const { span = 1, bold = false, size = 18, align = AlignmentType.CENTER } = opts;
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    columnSpan: span,
    borders: RUBRIC_BORDERS,
    margins: { top: 60, bottom: 60, left: 90, right: 90 },
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({
      alignment: align,
      indent: { firstLine: 0 },
      spacing: { line: 240, lineRule: LineRuleType.AUTO },
      children: [new TextRun({
        text, bold, size,
        font: { ascii: 'Times New Roman', eastAsia: 'SimSun', hAnsi: 'Times New Roman' },
      })],
    })],
  });
}

const RUBRIC_ROWS = [
  ['选题', '10%', '选题符合课程教学大纲要求；有一定深度，难度适宜；能够与专业实际需求相结合，对学生未来从事与管理相关的工作具有较强的指导价值。',
    ['9-10', '8', '7', '6', '0-5']],
  ['格式', '20%', '能按规定的要求排版，图片清晰，形式美观。',
    ['18-20', '16-17', '14-15', '12-13', '0-11']],
  ['内容', '40%', '论文目的明确，思路清晰；设计内容层次合理；论述结果正确、合理；对于论述过程中存在的问题，分析较全面、透彻；论文体现了较强的实践性和综合性。',
    ['36-40', '32-35', '28-31', '24-27', '0-23']],
  ['语言与结构', '20%', '文字精炼、流畅、准确、灵活，逻辑性强。结构严谨规范，条理清晰，布局合理，系统严密。',
    ['18-20', '16-17', '14-15', '12-13', '0-11']],
  ['创新', '10%', '融入了自己对项目管理的理念与观点，有新颖之处。',
    ['9-10', '8', '7', '6', '0-5']],
];

function rubricTable() {
  const rows = [];

  rows.push(new TableRow({
    tableHeader: true,
    children: [
      rubricCell('评价项目', RUBRIC_WIDTHS[0], { bold: true, span: 1 }),
      rubricCell('权重', RUBRIC_WIDTHS[1], { bold: true }),
      rubricCell('评价内容', RUBRIC_WIDTHS[2], { bold: true }),
      rubricCell('评价结果', RUBRIC_WIDTHS[3] * 5, { bold: true, span: 5 }),
      rubricCell('得分', RUBRIC_WIDTHS[8], { bold: true }),
    ],
  }));

  rows.push(new TableRow({
    children: [
      rubricCell('', RUBRIC_WIDTHS[0]),
      rubricCell('', RUBRIC_WIDTHS[1]),
      rubricCell('', RUBRIC_WIDTHS[2]),
      ...['A', 'B', 'C', 'D', 'E'].map((g, i) =>
        rubricCell(g, RUBRIC_WIDTHS[3 + i], { bold: true })),
      rubricCell('', RUBRIC_WIDTHS[8]),
    ],
  }));

  for (const [item, weight, content, grades] of RUBRIC_ROWS) {
    rows.push(new TableRow({
      children: [
        rubricCell(item, RUBRIC_WIDTHS[0]),
        rubricCell(weight, RUBRIC_WIDTHS[1]),
        rubricCell(content, RUBRIC_WIDTHS[2], { align: AlignmentType.LEFT }),
        ...grades.map((g, i) => rubricCell(g, RUBRIC_WIDTHS[3 + i])),
        rubricCell('', RUBRIC_WIDTHS[8]),
      ],
    }));
  }

  rows.push(new TableRow({
    children: [
      rubricCell('总成绩', RUBRIC_WIDTHS[0] + RUBRIC_WIDTHS[1] + RUBRIC_WIDTHS[2],
        { bold: true, span: 3 }),
      rubricCell('', RUBRIC_WIDTHS[3] * 5 + RUBRIC_WIDTHS[8], { span: 6 }),
    ],
  }));

  rows.push(new TableRow({
    children: [
      rubricCell('指导教师签字                  日期：    年   月    日',
        RUBRIC_WIDTHS.reduce((a, b) => a + b, 0), { span: 9, size: 21 }),
    ],
  }));

  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: RUBRIC_WIDTHS,
    borders: RUBRIC_BORDERS,
    rows,
  });
}

function backCoverContent() {
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      pageBreakBefore: true,
      indent: { firstLine: 0 },
      spacing: { before: 0, after: 240, line: 360, lineRule: LineRuleType.AUTO },
      children: [new TextRun({
        text: '课程论文评分标准', bold: true, size: 32,
        font: { ascii: 'Times New Roman', eastAsia: 'SimSun', hAnsi: 'Times New Roman' },
      })],
    }),
    rubricTable(),
  ];
}

// ─────────────────────────────────────────────────────────────────────────────
// 页码编排：封面不编号；摘要与目录用罗马数字（I、II）；正文起用阿拉伯数字
// 并从 1 重新计数。三节结构一次生成，无需事后拆节。
// ─────────────────────────────────────────────────────────────────────────────

const PAGE_PROPS = {
  size:   { width: PAGE_W, height: PAGE_H },
  margin: { top: MARGIN_V, right: MARGIN, bottom: MARGIN_V, left: MARGIN },
};

const centeredPageNumberFooter = () => new Footer({
  children: [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      indent:    { firstLine: 0 },
      children:  [new TextRun({
        children: [PageNumber.CURRENT],
        font: { ascii: 'Times New Roman', hAnsi: 'Times New Roman' },
      })],
    }),
  ],
});

// 按分节点切开：front = 题目+摘要+关键词+目录；body = 正文+参考文献+封底
const hasFrontMatter = _frontMatterSplitAt > 0;
const frontContent = hasFrontMatter ? CONTENT.slice(0, _frontMatterSplitAt) : [];
const bodyContent  = hasFrontMatter ? CONTENT.slice(_frontMatterSplitAt) : CONTENT;

if (!hasFrontMatter) {
  console.warn('警告：未找到前置/正文分节点（缺少「摘要」+「关键词：」），整篇将作为单节处理。');
}

let SECTIONS;

if (BODY_ONLY) {
  // Body-only mode: one section, no cover, no TOC, no page numbers.
  // The course template provides the cover/grading table/TOC and the body
  // section's PAGE field after the merge.
  SECTIONS = [
    {
      properties: { page: PAGE_PROPS },
      children: CONTENT,
    },
  ];
} else {
  SECTIONS = [
    // 第 1 节：封面（不编号）
    {
      properties: { page: PAGE_PROPS },
      children: coverContent(),
    },
  ];

  if (hasFrontMatter) {
    // 第 2 节：摘要 + 目录 —— 罗马数字 I、II
    SECTIONS.push({
      properties: {
        page: {
          ...PAGE_PROPS,
          pageNumbers: { start: 1, formatType: NumberFormat.UPPER_ROMAN },
        },
      },
      footers: { default: centeredPageNumberFooter() },
      children: frontContent,
    });
  }

  // 末节：正文 + 参考文献 + 封底 —— 阿拉伯数字从 1 重新计数
  SECTIONS.push({
    properties: {
      page: {
        ...PAGE_PROPS,
        pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL },
      },
    },
    footers: { default: centeredPageNumberFooter() },
    children: bodyContent.concat(backCoverContent()),
  });
}

const doc = new Document({
  styles:    STYLES,
  numbering: NUMBERING,
  sections:  SECTIONS,
});

Packer.toBuffer(doc).then(buf => {
  const out = path.resolve(OUTPUT_PATH);
  fs.writeFileSync(out, buf);
  console.log(`✓  Written: ${out}`);
}).catch(err => {
  console.error('Error building document:', err.message);
  process.exit(1);
});
