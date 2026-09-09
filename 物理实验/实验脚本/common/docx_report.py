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


def _text_mode_replace(m: re.Match) -> str:
    """\\mathrm/\\text 回调：内容用双引号包裹，并替换 Unicode 上标。"""
    content = m.group(1)
    for carat, uni in [('^2', '²'), ('^3', '³'), ('^4', '⁴'),
                       ('^5', '⁵'), ('^6', '⁶'), ('^7', '⁷'),
                       ('^8', '⁸'), ('^9', '⁹'), ('^0', '⁰'),
                       ('^+', '⁺'), ('^-', '⁻')]:
        content = content.replace(carat, uni)
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
            self._sel.TypeText(text)
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

    # ── 公开方法 ──────────────────────────────────────────

    def add_title(self, text: str):
        """居中加粗大标题。"""
        self._type_paragraph(text, font_name="黑体", font_size=16, bold=True,
                             alignment=wdAlignParagraphCenter, space_after=12)

    def add_student_info(self):
        """插入学生信息行。从环境变量读取真实值，未设置时用占位符。"""
        name = os.environ.get("LAB_STUDENT_NAME", "").strip() or "■■■"
        sid = os.environ.get("LAB_STUDENT_ID", "").strip() or "■■■■■■"
        sclass = os.environ.get("LAB_STUDENT_CLASS", "").strip() or "■■■"
        date = os.environ.get("LAB_STUDENT_DATE", "").strip() or "■■■■■■"
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
        self._sel.TypeText(text)

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
        # 4. \\overline{...} — BuildUp 原生支持，保留不动
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
                    self._sel.TypeText(part)
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

    def save(self):
        """保存文档。"""
        if self._closed:
            return
        self._doc.SaveAs(self.output_path, FileFormat=wdFormatXMLDocument)
        print(f"Report saved: {self.output_path}")

    def close(self):
        """保存并退出 Word（含孤儿进程兜底清理）。"""
        if self._closed:
            return

        try:
            self._doc.SaveAs(self.output_path, FileFormat=wdFormatXMLDocument)
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
