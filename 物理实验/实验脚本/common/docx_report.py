"""Word 报告生成器 — 基于 win32com 操控 Microsoft Word。

通过 Word COM 接口创建 .docx 文件，利用 OMaths.Add() + BuildUp()
将 UnicodeMath 线性格式转为 Word 原生可编辑数学公式。

要求：Windows + Microsoft Word 2016 或更高版本。

注意：BuildUp() 支持 \\frac、\\sqrt、\\sum、^、_、希腊字母、
\\overline 等 UnicodeMath 命令。\\mathrm 和 \\text 不被支持，
需在 add_math() 中转为双引号文本模式。
"""

import os
import re
import time
import zipfile
import ctypes
import subprocess
import win32com.client


# ── Word COM 常量 ──
wdPaperA4 = 7
wdAlignParagraphCenter = 1
wdAlignParagraphLeft = 0
wdStory = 6
wdWord9TableBehavior = 1
wdAutoFitWindow = 1
wdLineStyleSingle = 1
wdPageBreak = 7
wdFormatXMLDocument = 12
wdDoNotSaveChanges = 0
wdCollapseEnd = 0
wdAlignRowCenter = 1

# ── 宋体缺失的 Unicode 上下标字符 → Word 原生上下标 ──
# 宋体（SimSun）不含 U+2070-207F（²³除外）/U+2080-209F 等字符，直接输出会
# 渲染为 □（豆腐块）。打字时把这些字符转为普通字符 + Font.Subscript/
# Superscript 原生样式：显示效果更好，且不依赖字体覆盖。
_SUBSCRIPT_MAP = {
    '₀': '0', '₁': '1', '₂': '2', '₃': '3', '₄': '4',
    '₅': '5', '₆': '6', '₇': '7', '₈': '8', '₉': '9',
    'ₐ': 'a', 'ₑ': 'e', 'ₒ': 'o', 'ₓ': 'x', 'ₕ': 'h', 'ₖ': 'k',
    'ₗ': 'l', 'ₘ': 'm', 'ₙ': 'n', 'ₚ': 'p', 'ₛ': 's', 'ₜ': 't',
    'ᵢ': 'i', 'ⱼ': 'j',
}
_SUPERSCRIPT_MAP = {
    '⁻': '-', '⁺': '+', '⁰': '0', '¹': '1', '⁴': '4', '⁵': '5',
    '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9', 'ⁿ': 'n', 'ⁱ': 'i',
}
# 宋体缺失且无上下标语义的字符 → 宋体已有的等效写法（防 □ 兜底）
_CHAR_REPLACE = [
    ('≪', '<<'), ('≫', '>>'),      # 远小于/远大于 → ASCII
    ('\u2212', '-'),                 # 数学减号 U+2212 → ASCII 连字符
    ('\u2207', '\u25bd'),            # ∇ → ▽（GB2312 符号区，宋体具备）
    ('\u0304', '\u00af'),            # 组合上横线 → 间距宏符 ¯（兜底；源头应使用 $\bar{x}$）
]


def _normalize_text_chars(text: str) -> str:
    for a, b in _CHAR_REPLACE:
        if a in text:
            text = text.replace(a, b)
    return text


# LaTeX 间距命令字面（Word UnicodeMath 不识别，纯文本中若出现会原样显示）：
# \emsp \ensp \qquad \quad \hspace{...} \, \; \: \  → 全角空格；\! 负空格删除
_LATEX_SPACE_CMD_RE = re.compile(
    r"\\(?:emsp|ensp|qquad|quad|hspace\*?\{[^}]*\}|,|;|:| )")


def _normalize_text(text: str) -> str:
    r"""文本归一化：字符映射 + 清除 LaTeX 间距命令字面（防 \emsp 等原文残留）。"""
    text = _normalize_text_chars(text)
    text = text.replace(r"\!", "")
    return _LATEX_SPACE_CMD_RE.sub("\u3000", text)


def _purge_latex_spaces_in_docx(path: str) -> int:
    r"""兜底：保存完成后扫描报告的 document.xml，清除残留的 LaTeX 间距命令
    字面文本（\emsp、\ensp、\quad、\qquad、\hspace{...}、\,、\;、\:、\!、\ 等），
    统一替换为全角空格。返回清除次数；文件异常时静默返回 0。"""
    if not os.path.exists(path):
        return 0
    try:
        with zipfile.ZipFile(path, "r") as zin:
            items = {n: zin.read(n) for n in zin.namelist()}
    except Exception:
        return 0
    target = "word/document.xml"
    if target not in items:
        return 0
    try:
        xml = items[target].decode("utf-8")
    except Exception:
        return 0
    new_xml, n = _LATEX_SPACE_CMD_RE.subn("\u3000", xml)
    if n == 0:
        return 0
    tmp = path + ".~sweep"
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for name, data in items.items():
                zout.writestr(name, new_xml if name == target else data)
        os.replace(tmp, path)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return 0
    print(f"[提示] 已清除 {n} 处未识别的 LaTeX 间距命令（\\emsp 等）")
    return n


def _needs_safe_typing(text: str) -> bool:
    return any(ch in _SUBSCRIPT_MAP or ch in _SUPERSCRIPT_MAP for ch in text) \
        or any(a in text for a, _ in _CHAR_REPLACE)


_GREEK_MAP = {
    'Alpha': 'Α', 'Beta': 'Β', 'Gamma': 'Γ', 'Delta': 'Δ', 'Epsilon': 'Ε',
    'Zeta': 'Ζ', 'Eta': 'Η', 'Theta': 'Θ', 'Iota': 'Ι', 'Kappa': 'Κ',
    'Lambda': 'Λ', 'Mu': 'Μ', 'Nu': 'Ν', 'Xi': 'Ξ', 'Pi': 'Π', 'Rho': 'Ρ',
    'Sigma': 'Σ', 'Tau': 'Τ', 'Phi': 'Φ', 'Chi': 'Χ', 'Psi': 'Ψ', 'Omega': 'Ω',
    'alpha': 'α', 'beta': 'β', 'gamma': 'γ', 'delta': 'δ', 'epsilon': 'ε',
    'varepsilon': 'ε', 'zeta': 'ζ', 'eta': 'η', 'theta': 'θ', 'vartheta': 'ϑ',
    'iota': 'ι', 'kappa': 'κ', 'lambda': 'λ', 'mu': 'μ', 'nu': 'ν', 'xi': 'ξ',
    'pi': 'π', 'varpi': 'ϖ', 'rho': 'ρ', 'varrho': 'ϱ', 'sigma': 'σ',
    'varsigma': 'ς', 'tau': 'τ', 'upsilon': 'υ', 'phi': 'φ', 'varphi': 'φ',
    'chi': 'χ', 'psi': 'ψ', 'omega': 'ω',
}
_GREEK_RE = re.compile(r"\\(" + "|".join(sorted(_GREEK_MAP, key=len, reverse=True)) + r")(?![A-Za-z])")


def _text_mode_replace(m: re.Match) -> str:
    """\\mathrm/\\text 回调：内容用双引号包裹，并替换 Unicode 上标。"""
    content = m.group(1)
    for carat, uni in [('^2', '²'), ('^3', '³'), ('^4', '⁴'),
                       ('^5', '⁵'), ('^6', '⁶'), ('^7', '⁷'),
                       ('^8', '⁸'), ('^9', '⁹'), ('^0', '⁰'),
                       ('^+', '⁺'), ('^-', '⁻')]:
        content = content.replace(carat, uni)
    # 文本模式内的 LaTeX 命令同样要转为字符，否则引号内会原样显示
    content = _GREEK_RE.sub(lambda mm: _GREEK_MAP[mm.group(1)], content)
    for latex, uni in ((r'\cdot', '·'), (r'\times', '×'), (r'\pm', '±'),
                       (r'\approx', '≈'), (r'\%', '%'), (r'\,', ' ')):
        content = content.replace(latex, uni)
    return '"' + content + '"'


def split_rich_blocks(text: str) -> list[tuple[str, str]]:
    """把富文本（可能含 Markdown 换行）拆为写入操作序列 [(kind, content)]。

    kind='math'：独立公式块（$$...$$），kind='para'：普通段落（可含 $..$ 内联式）。
    段落以换行分隔；段内残留的行中 $$..$$ 降级为 $..$ 内联公式，避免破坏版式。
    单行无 $$ 的文本输出与旧行为完全一致（恰好一个 para 操作）。
    """
    ops = []
    for block in re.split(r"\n+", (text or "").strip()):
        b = block.strip()
        if not b:
            continue
        if (b.startswith("$$") and b.endswith("$$") and len(b) > 4
                and "$$" not in b[2:-2]):
            expr = b[2:-2].strip()
            if expr:
                ops.append(("math", expr))
            continue
        b = re.sub(r"\$\$([^$]*)\$\$", r"$\1$", b)
        if b.strip():
            ops.append(("para", b))
    return ops


def _get_word_pids() -> set:
    """枚举当前所有 WINWORD.EXE 进程 PID（tasklist，纯标准库）。"""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq WINWORD.EXE", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
            encoding="mbcs", errors="replace",  # 中文 Windows 输出为 ANSI/GBK
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = result.stdout
    except Exception:
        return set()
    if not out:
        return set()
    pids = set()
    for line in out.strip().splitlines():
        parts = line.replace('"', "").split(",")
        if len(parts) >= 2 and parts[1].strip().isdigit():
            pids.add(int(parts[1].strip()))
    return pids


def _wait_pid_exit(pid: int, timeout: float = 5.0) -> bool:
    """等待进程退出，超时则强制终止该 PID。返回是否已退出。"""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    PROCESS_TERMINATE = 0x0001
    STILL_ACTIVE = 259
    start = time.time()
    while time.time() - start < timeout:
        h = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return True  # 进程已不存在
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        if code.value != STILL_ACTIVE:
            return True
        time.sleep(0.1)
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if h:
        ctypes.windll.kernel32.TerminateProcess(h, 0)
        ctypes.windll.kernel32.CloseHandle(h)
    return False


class DocxReportWriter:
    """封装 Word COM 操作，生成物理实验报告。

    注意：使用 DispatchEx + Selection 全程操作，避免 Range 对象
    在 Python 3.14 下的 RPC 兼容问题。
    """

    def __init__(self, output_path: str, visible: bool = False):
        self.output_path = os.path.abspath(output_path)
        # 先写入同目录临时文件、Word 退出后再原子替换到目标路径：
        # 直接 SaveAs 目标文件时，若该报告正被用户的 Word 打开，会产生文件冲突，
        # 隐藏的自动化实例会弹出对话框并把窗口抢到前台（批量生成时打断用户查看）。
        # 临时名以 ".~saving<pid>.docx" 结尾，排序在正式报告之后，且被应用扫描过滤。
        self._tmp_path = self.output_path + ".~saving" + str(os.getpid()) + ".docx"
        self._closed = False

        # 记录启动 Word 前的已有 WINWORD 进程（close 时只清理本次新增的实例）
        self._word_pids_before = _get_word_pids()

        self._word = win32com.client.DispatchEx("Word.Application")
        self._word.Visible = visible
        self._word.DisplayAlerts = False
        time.sleep(2)  # 等待 Word 完全初始化

        self._word.Documents.Add()
        time.sleep(0.5)
        self._doc = self._word.ActiveDocument

        # 页面设置 A4
        page = self._doc.PageSetup
        page.PaperSize = wdPaperA4
        page.TopMargin = 72.0
        page.BottomMargin = 72.0
        page.LeftMargin = 90.0
        page.RightMargin = 90.0

        self._sel = self._word.Selection
        self._body_font_size = 12

    # ── 内部工具 ──────────────────────────────────────────

    def _goto_end(self):
        """将光标移到文档末尾。"""
        self._sel.EndKey(Unit=wdStory)

    def _type_paragraph(self, text: str = "", font_name: str = "宋体",
                        font_size: float = 12, bold: bool = False,
                        alignment: int = wdAlignParagraphLeft,
                        space_after: float = 0, space_before: float = 0,
                        first_line_indent: float = 0):
        """用 Selection 插入一个段落并设置格式。"""
        self._goto_end()
        self._sel.TypeParagraph()
        if text:
            self._type_text_safe(text)
        # 选中刚输入的段落
        self._sel.Paragraphs.Last.Range.Select()
        pf = self._sel.ParagraphFormat
        pf.Alignment = alignment
        pf.SpaceAfter = space_after
        pf.SpaceBefore = space_before
        if first_line_indent:
            pf.FirstLineIndent = first_line_indent
        self._sel.Font.Name = font_name
        self._sel.Font.Size = font_size
        self._sel.Font.Bold = bold
        self._sel.Collapse(Direction=wdCollapseEnd)
        self._sel.Font.Reset()

    def _set_last_run_font(self, font_name: str, font_size: float, bold: bool):
        """设置最后插入文本的字体。"""
        # 选中最后插入的内容并设置字体
        self._sel.Font.Name = font_name
        self._sel.Font.Size = font_size
        self._sel.Font.Bold = bold

    def _type_text_safe(self, text: str):
        """打字输出文本：宋体缺失的 Unicode 上下标自动转为 Word 原生上下标。

        普通文本直接 TypeText；遇到 ₀₁₂/⁻⁵ 等字符时切换
        Font.Subscript/Superscript 打出等效的普通字符，避免渲染为 □。
        """
        if not text:
            return
        text = _normalize_text(text)
        if not _needs_safe_typing(text):
            self._sel.TypeText(text)
            return
        segments = []  # [mode, str]  mode: 0 普通 / 1 下标 / 2 上标
        for ch in text:
            if ch in _SUBSCRIPT_MAP:
                mode, c = 1, _SUBSCRIPT_MAP[ch]
            elif ch in _SUPERSCRIPT_MAP:
                mode, c = 2, _SUPERSCRIPT_MAP[ch]
            else:
                mode, c = 0, ch
            if segments and segments[-1][0] == mode:
                segments[-1][1] += c
            else:
                segments.append([mode, c])
        for mode, s in segments:
            if mode == 1:
                self._sel.Font.Subscript = True
            elif mode == 2:
                self._sel.Font.Superscript = True
            self._sel.TypeText(s)
            if mode:
                self._sel.Font.Subscript = False
                self._sel.Font.Superscript = False

    # ── 公开方法 ──────────────────────────────────────────

    def add_title(self, text: str):
        """居中加粗大标题。"""
        self._type_paragraph(text, font_name="黑体", font_size=16, bold=True,
                             alignment=wdAlignParagraphCenter, space_after=12)

    def add_student_info(self):
        """插入学生信息行。从环境变量读取真实值，未设置时用（未填写）占位。"""
        name = os.environ.get("LAB_STUDENT_NAME", "").strip() or "（未填写）"
        sid = os.environ.get("LAB_STUDENT_ID", "").strip() or "（未填写）"
        sclass = os.environ.get("LAB_STUDENT_CLASS", "").strip() or "（未填写）"
        date = os.environ.get("LAB_STUDENT_DATE", "").strip() or "（未填写）"
        fields = f"姓名：{name}    学号：{sid}    班级：{sclass}    实验日期：{date}"
        self._type_paragraph(fields, font_name="宋体", font_size=self._body_font_size,
                             space_after=6)

    def add_heading(self, text: str, level: int = 1):
        """章节标题。level 1=一级，level 2=二级。"""
        if level == 1:
            self._type_paragraph(text, font_name="黑体", font_size=14, bold=True,
                                 space_before=12, space_after=6)
        else:
            self._type_paragraph(text, font_name="黑体", font_size=12, bold=True,
                                 space_before=6, space_after=3)

    def add_paragraph(self, text: str):
        """正文段落（首行缩进）。"""
        self._type_paragraph(text, font_name="宋体", font_size=self._body_font_size,
                             first_line_indent=21.0)

    def _begin_rich_paragraph(self):
        """另起一个富文本段落（左对齐、首行缩进），光标留在段尾。"""
        self._goto_end()
        self._sel.TypeParagraph()
        self._sel.Paragraphs.Last.Range.Select()
        pf = self._sel.ParagraphFormat
        pf.Alignment = wdAlignParagraphLeft
        pf.SpaceAfter = 6
        pf.SpaceBefore = 0
        pf.FirstLineIndent = 21.0
        self._sel.Collapse(Direction=wdCollapseEnd)

    def add_paragraph_rich(self, text: str):
        """富文本正文（Markdown 兼容）：自动分段并解析 $...$ 内联公式。

        变体/AI 润色章节整段文字的统一入口：按换行拆段，$$...$$ 独立公式块
        转为居中显示公式（add_math），$...$ 内联公式随文字流动（add_inline_math），
        普通文字宋体正文（首行缩进）。单行纯文本时与 add_paragraph 等价。
        """
        for kind, content in split_rich_blocks(text):
            if kind == "math":
                self.add_math(content)
                continue
            self._begin_rich_paragraph()
            for part in re.split(r"(\$[^$]*\$)", content):
                if not part:
                    continue
                if part.startswith("$") and part.endswith("$") and len(part) > 2:
                    self.add_inline_math(part)
                else:
                    self.add_run(part)
            self._sel.Collapse(Direction=wdCollapseEnd)
            self._goto_end()

    def add_math(self, latex: str):
        """插入 LaTeX 公式并转为 Word 原生数学公式（display 模式）。

        latex: LaTeX 字符串，可以带 $...$ 定界符（会自动剥除）。
        自动将 Word BuildUp() 不支持的 LaTeX 命令转为 UnicodeMath 等效格式：
          - \\mathrm{...} / \\text{...} → "..."（双引号文本模式）
        \\overline、\\frac、\\sqrt 等命令 BuildUp 原生支持，保留不动。
        使用 OMaths.Add() + BuildUp() 将线性格式转为专业格式。
        """
        formula = latex.strip()
        if formula.startswith("$"):
            formula = formula[1:]
        if formula.endswith("$"):
            formula = formula[:-1]
        formula = formula.strip()

        if not formula:
            return

        # ── LaTeX → UnicodeMath 预处理 ──
        formula = self._preprocess_latex(formula)

        self._goto_end()
        self._sel.TypeParagraph()

        # OMaths.Add 在当前 Selection 位置插入空公式
        self._doc.OMaths.Add(self._sel.Range)
        idx = self._doc.OMaths.Count
        om = self._doc.OMaths(idx)
        # 注意：不要读取 om.Range.Text（Python 3.14 GBK 编码问题）
        om.Range.Text = formula
        om.BuildUp()

        # 光标移出公式区域
        self._sel.Collapse(Direction=wdCollapseEnd)
        self._goto_end()

        self._sel.Collapse(Direction=wdCollapseEnd)
        self._goto_end()

    def add_run(self, text: str):
        """在当前段落末尾追加文字（不另起段落）。

        用于与 add_inline_math() 配合，在同一段落内交替输出文字和公式。
        """
        if not text:
            return
        self._goto_end()
        self._sel.Font.Name = "宋体"
        self._sel.Font.Size = self._body_font_size
        self._type_text_safe(text)

    def add_inline_math(self, latex: str):
        """在当前段落内插入内联公式（不换行，随文字流动）。

        与 add_math() 的区别：不调用 TypeParagraph()，公式嵌在当前段落内部，
        与前后 add_run() 的文字处于同一个 <w:p> 中，基线对齐，自动换行。
        """
        formula = latex.strip()
        if formula.startswith("$"):
            formula = formula[1:]
        if formula.endswith("$"):
            formula = formula[:-1]
        formula = formula.strip()

        if not formula:
            return

        formula = self._preprocess_latex(formula)

        self._goto_end()
        # 注意：不调 TypeParagraph()，直接在当前光标插入 OMath
        self._doc.OMaths.Add(self._sel.Range)
        idx = self._doc.OMaths.Count
        om = self._doc.OMaths(idx)
        om.Range.Text = formula
        om.BuildUp()

        # 光标移出公式，停留在同一段落内
        self._sel.Collapse(Direction=wdCollapseEnd)
        self._goto_end()

    @staticmethod
    def _preprocess_latex(formula: str) -> str:
        """将 LaTeX 公式转为 Word BuildUp() 兼容的 UnicodeMath 线性格式。

        Word BuildUp 支持的常用命令：\\frac、\\sqrt、\\sum、^、_、
        希腊字母（\\Delta、\\lambda 等）、\\cdot、\\pm、\\times、
        \\approx、\\left、\\right、\\overline。

        需要转换的：
          - \\mathrm{...} → "..."（UnicodeMath 双引号 = 文本/正体模式）
          - \\text{...}   → "..."（同上）
        """
        # 1. \\mathrm{...} → "..."（双引号文本模式）
        #    文本模式中 ^ 不起上标作用，替换为 Unicode 上标字符
        formula = re.sub(r'\\mathrm\{([^}]*)\}', _text_mode_replace, formula)
        # 2. \\text{...} → "..."（同上）
        formula = re.sub(r'\\text\{([^}]*)\}', _text_mode_replace, formula)
        # 3. \\% → %（Word UnicodeMath 百分号不需要转义）
        formula = formula.replace(r'\%', '%')
        # 4. LaTeX 间距命令（\, \; \: \! \emsp \ensp \quad \qquad \hspace{...}
        #    及反斜杠空格）UnicodeMath 不识别，会导致 BuildUp 失败、
        #    公式以线性文本残留，统一替换为普通空格
        for sp in (r'\,', r'\;', r'\:', r'\ ', r'\emsp', r'\ensp', r'\qquad', r'\quad'):
            formula = formula.replace(sp, ' ')
        formula = formula.replace(r'\!', '')
        formula = re.sub(r'\\hspace\*?\{[^}]*\}', ' ', formula)
        # 5. 希腊字母命令 → Unicode 希腊字符（\Omega 等部分名称 Word UnicodeMath
        #    不识别，会导致整条公式 BuildUp 失败并残留为线性文本）
        formula = _GREEK_RE.sub(lambda m: _GREEK_MAP[m.group(1)], formula)
        # 6. \\dfrac / \\tfrac / \\cfrac → \\frac（UnicodeMath 只认 \\frac）
        formula = re.sub(r"\\(?:d|t|c)frac(?![A-Za-z])", r"\\frac", formula)
        # 7. 括号尺寸命令 \\Big \\big \\Bigg 等 → 去掉（UnicodeMath 不识别，
        #    残留会导致整条公式 BuildUp 失败）
        formula = re.sub(r"\\(?:Big|big|Bigg|bigg)[lrm]?(?![A-Za-z])", "", formula)
        # 8. 绝对值竖线：裸 |...| 在含 \frac / 下标 / 上标时 Word BuildUp 会失败
        #    （\frac 以 ⍁ U+2341、\left/\right 以 ├ ┤ 字面残留，渲染为方框），
        #    统一改为 \\left|...\\right|（原生支持、必能构建）；简单 |x| 不动
        formula = re.sub(r"(?<!\\left)\|([^|]*(?:\\frac|[_^])[^|]*)\|",
                         r"\\left|\1\\right|", formula)
        # 9. \\overline{...} — BuildUp 原生支持，保留不动
        return formula

    def _set_cell_content(self, cell, text, bold=False):
        """设置单元格内容，支持 $...$ 公式标记（可与普通文本混合）。"""
        text = str(text) if text is not None else ""
        # 检测是否包含 $...$ 公式
        if "$" in text:
            # 分割公式和普通文本（保留分隔符）
            parts = re.split(r'(\$[^$]+\$)', text)
            # 清空单元格并定位到开头
            cell.Range.Text = ""
            cell.Range.Select()
            self._sel.Collapse(Direction=1)  # wdCollapseStart=1
            for part in parts:
                if not part:
                    continue
                if part.startswith("$") and part.endswith("$") and len(part) > 2:
                    # 公式段
                    formula = part[1:-1].strip()
                    formula = self._preprocess_latex(formula)
                    self._doc.OMaths.Add(self._sel.Range)
                    idx = self._doc.OMaths.Count
                    om = self._doc.OMaths(idx)
                    om.Range.Text = formula
                    om.BuildUp()
                    # 把光标移出公式区域：选中公式末尾 → 右移一个字符
                    om.Range.Select()
                    self._sel.Collapse(Direction=wdCollapseEnd)
                    self._sel.MoveRight(Unit=1, Count=1)  # wdCharacter=1
                else:
                    # 普通文本段
                    self._sel.Font.Name = "宋体"
                    self._sel.Font.Size = 10
                    self._sel.Font.Bold = bold
                    self._type_text_safe(part)
            cell.Range.ParagraphFormat.Alignment = wdAlignParagraphCenter
        elif _needs_safe_typing(text):
            # 含宋体缺失字符：改用打字路径以套用原生上下标
            cell.Range.Text = ""
            cell.Range.Select()
            self._sel.Collapse(Direction=1)  # wdCollapseStart=1
            self._sel.Font.Name = "宋体"
            self._sel.Font.Size = 10
            self._sel.Font.Bold = bold
            self._type_text_safe(text)
            cell.Range.ParagraphFormat.Alignment = wdAlignParagraphCenter
        else:
            cell.Range.Text = text
            cell.Range.Font.Bold = bold
            cell.Range.Font.Size = 10
            cell.Range.Font.Name = "宋体"
            cell.Range.ParagraphFormat.Alignment = wdAlignParagraphCenter

    def add_table(self, headers: list[str], rows: list[list[str]],
                  col_widths: list[float] | None = None):
        """插入带边框的数据表格。表头和数据单元格均支持 $...$ 公式标记。"""
        ncols = len(headers)
        nrows = 1 + len(rows)

        self._goto_end()
        self._sel.TypeParagraph()

        table = self._doc.Tables.Add(
            self._sel.Range, NumRows=nrows, NumColumns=ncols,
            DefaultTableBehavior=wdWord9TableBehavior,
            AutoFitBehavior=wdAutoFitWindow
        )

        table.Borders.Enable = True
        table.Borders.InsideLineStyle = wdLineStyleSingle
        table.Borders.OutsideLineStyle = wdLineStyleSingle
        table.Rows.Alignment = wdAlignRowCenter  # 表格整体居中

        for j, h in enumerate(headers):
            cell = table.Cell(1, j + 1)
            self._set_cell_content(cell, h, bold=True)

        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                cell = table.Cell(i + 2, j + 1)
                self._set_cell_content(cell, val, bold=False)

        if col_widths:
            for j, w in enumerate(col_widths[:ncols]):
                # 注：AutoFitWindow 状态下直接设置 Column.Width 会报"数值超出范围"
                # （新版 Word 行为），改用 PreferredWidth 精确生效
                table.Columns(j + 1).PreferredWidth = w * 28.35

        self._sel.Collapse(Direction=wdCollapseEnd)
        self._goto_end()
        self._sel.TypeParagraph()

    def add_image(self, image_path: str, width_cm: float | None = None):
        """插入图片并居中。width_cm 为可选宽度（cm），不指定则原尺寸。"""
        abs_path = os.path.abspath(image_path)
        if not os.path.exists(abs_path):
            print(f"  [WARNING] Image not found: {abs_path}")
            return
        self._goto_end()
        self._sel.TypeParagraph()
        inline = self._sel.InlineShapes.AddPicture(
            FileName=abs_path, LinkToFile=False, SaveWithDocument=True
        )
        if width_cm is not None:
            inline.Width = width_cm * 28.35  # cm → pt
        # 居中图片段落
        self._sel.Paragraphs.Last.Range.Select()
        self._sel.ParagraphFormat.Alignment = wdAlignParagraphCenter
        self._sel.Collapse(Direction=wdCollapseEnd)
        self._goto_end()

    def add_page_break(self):
        """插入分页符。"""
        self._goto_end()
        self._sel.InsertBreak(Type=wdPageBreak)

    def _save_tmp(self):
        """保存到临时文件（保存前再次确认实例不可见，防止任何弹窗抢焦点）。"""
        try:
            self._word.Visible = False
        except Exception:
            pass
        self._doc.SaveAs(self._tmp_path, FileFormat=wdFormatXMLDocument)

    def save(self):
        """保存文档（写入临时文件，close() 时原子替换到目标路径）。"""
        if self._closed:
            return
        self._save_tmp()

    def close(self):
        """保存并退出 Word（含孤儿进程兜底清理），随后把临时文件替换为目标报告。"""
        if self._closed:
            return

        try:
            self._save_tmp()
        except Exception:
            pass
        try:
            self._doc.Close(SaveChanges=wdDoNotSaveChanges)
        except Exception:
            pass
        try:
            self._word.Quit()
        except Exception:
            pass

        # 显式释放 COM 引用，避免 Word 进程（/Automation）残留
        self._sel = None
        self._doc = None
        self._word = None
        self._closed = True

        # Word 完全退出后再替换目标文件：即使目标被用户 Word 打开也只是替换失败，
        # 不会让自动化实例弹窗抢前台；本次结果保留在临时文件中供恢复。
        try:
            os.replace(self._tmp_path, self.output_path)
            _purge_latex_spaces_in_docx(self.output_path)
            print(f"Report saved: {self.output_path}")
        except PermissionError:
            print(f"[错误] 目标报告文件正被占用（可能已在 Word 中打开）：{self.output_path}")
            print(f"[提示] 本次生成结果已保留为：{self._tmp_path}")
            print("[提示] 请关闭 Word 中的旧报告后重新生成，或将上述文件重命名使用")
        except FileNotFoundError:
            pass  # 保存阶段失败时无临时文件可替换

        # 兜底：Quit 之后重新枚举"本次新增"的 WINWORD 进程（Quit 前快照可能
        # 错过尚未登记完成的实例；Quit 后即使 tasklist 短暂失败也能重试到）
        time.sleep(1)
        for _ in range(3):
            try:
                my_pids = _get_word_pids() - self._word_pids_before
            except Exception:
                my_pids = set()
            if not my_pids:
                break
            for pid in list(my_pids):
                _wait_pid_exit(pid)
            time.sleep(0.5)
            if not (_get_word_pids() & my_pids):
                break
