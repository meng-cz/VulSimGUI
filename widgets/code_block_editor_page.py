from __future__ import annotations

import copy
import re

from PyQt6.QtCore import Qt, pyqtSignal, QRegularExpression, QStringListModel
from PyQt6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QTextCharFormat,
    QTextCursor,
    QSyntaxHighlighter,
)
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QMessageBox,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QListWidget,
    QListWidgetItem,
    QCompleter,
)


_CPP_KEYWORDS = {
    "alignas", "alignof", "auto", "bool", "break", "case", "catch", "char", "class", "const",
    "constexpr", "continue", "default", "delete", "do", "double", "else", "enum", "explicit",
    "export", "extern", "false", "float", "for", "friend", "goto", "if", "inline", "int",
    "long", "namespace", "new", "noexcept", "nullptr", "operator", "private", "protected",
    "public", "register", "return", "short", "signed", "sizeof", "static", "struct", "switch",
    "template", "this", "throw", "true", "try", "typedef", "typename", "union", "unsigned",
    "using", "virtual", "void", "volatile", "while",
}

_CPP_COMMON_IDENTIFIERS = {
    "std", "size_t", "uint8_t", "uint16_t", "uint32_t", "uint64_t", "int8_t", "int16_t", "int32_t", "int64_t",
}


def _strip(value: str) -> str:
    return (value or "").strip()


def _safe_list(value):
    return value if isinstance(value, list) else []


def _normalized_text(value) -> str:
    if isinstance(value, list):
        return "\n".join(str(line) for line in value)
    return str(value or "")


class _CppSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)

        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []

        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#60a5fa"))
        keyword_format.setFontWeight(QFont.Weight.Bold)
        for word in sorted(_CPP_KEYWORDS):
            self._rules.append((QRegularExpression(rf"\b{word}\b"), keyword_format))

        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#f59e0b"))
        self._rules.append((QRegularExpression(r"\b\d+([uUlLfF]|ll|LL)?\b"), number_format))
        self._rules.append((QRegularExpression(r"\b0x[0-9a-fA-F]+\b"), number_format))

        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#34d399"))
        self._rules.append((QRegularExpression(r'"([^"\\]|\\.)*"'), string_format))
        self._rules.append((QRegularExpression(r"'([^'\\]|\\.)*'"), string_format))

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#94a3b8"))
        self._rules.append((QRegularExpression(r"//[^\n]*"), comment_format))

        preproc_format = QTextCharFormat()
        preproc_format.setForeground(QColor("#f472b6"))
        self._rules.append((QRegularExpression(r"^\s*#[^\n]*"), preproc_format))

        call_format = QTextCharFormat()
        call_format.setForeground(QColor("#c084fc"))
        self._rules.append((QRegularExpression(r"\b[A-Za-z_]\w*(?=\s*\()"), call_format))

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                match = it.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)


class _CodeEditor(QPlainTextEdit):
    completionRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._completer: QCompleter | None = None
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))

    def set_completion_words(self, words: list[str]):
        model = QStringListModel(sorted({w for w in words if w}, key=str.lower), self)
        if self._completer is None:
            completer = QCompleter(self)
            completer.setWidget(self)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            completer.activated.connect(self._insert_completion)
            self._completer = completer
        self._completer.setModel(model)

    def keyPressEvent(self, event: QKeyEvent):
        if self._completer and self._completer.popup().isVisible():
            if event.key() in {
                Qt.Key.Key_Return,
                Qt.Key.Key_Enter,
                Qt.Key.Key_Tab,
                Qt.Key.Key_Backtab,
                Qt.Key.Key_Escape,
            }:
                event.ignore()
                return

        if event.key() == Qt.Key.Key_Space and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.completionRequested.emit()
            self._show_completion_popup(force=True)
            event.accept()
            return

        super().keyPressEvent(event)

        if event.text() or event.key() in {Qt.Key.Key_Backspace, Qt.Key.Key_Delete}:
            self._show_completion_popup(force=False)

    def _text_under_cursor(self) -> str:
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        return cursor.selectedText()

    def _insert_completion(self, completion: str):
        cursor = self.textCursor()
        prefix = self._text_under_cursor()
        if prefix:
            for _ in range(len(prefix)):
                cursor.deletePreviousChar()
        cursor.insertText(completion)
        self.setTextCursor(cursor)

    def _show_completion_popup(self, force: bool):
        if not self._completer:
            return
        prefix = self._text_under_cursor()
        if not force and len(prefix) < 2:
            self._completer.popup().hide()
            return
        self._completer.setCompletionPrefix(prefix)
        popup = self._completer.popup()
        popup.setCurrentIndex(self._completer.completionModel().index(0, 0))
        rect = self.cursorRect()
        rect.setWidth(max(260, popup.sizeHintForColumn(0) + 24))
        self._completer.complete(rect)


class CodeBlockEditorPage(QWidget):
    saveRequested = pyqtSignal(str, str, str, dict)

    def __init__(self, module_name: str, block_kind: str, block_data: dict | None = None, analysis_context: dict | None = None, parent=None):
        super().__init__(parent)
        self.module_name = module_name
        self.block_kind = block_kind
        self.block_name = ""
        self.original_name = ""
        self._saved_snapshot: dict = {}
        self._analysis_context: dict = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        self.title_label = QLabel()
        self.title_label.setObjectName("pageTitle")

        self.analysis_hint = QLabel("前端预览声明与符号列表，真实声明以后端分析结果为准。")
        self.analysis_hint.setStyleSheet("color: #94a3b8;")

        self.btn_save = QPushButton("保存")
        self.btn_reload = QPushButton("重新载入")

        top_row.addWidget(self.title_label)
        top_row.addStretch(1)
        top_row.addWidget(self.analysis_hint)
        top_row.addWidget(self.btn_reload)
        top_row.addWidget(self.btn_save)
        root.addLayout(top_row)

        info_group = QGroupBox("代码块信息")
        info_form = QFormLayout(info_group)
        info_form.setContentsMargins(12, 12, 12, 12)
        info_form.setSpacing(8)

        self.module_edit = QLineEdit()
        self.module_edit.setReadOnly(True)

        self.kind_edit = QLineEdit()
        self.kind_edit.setReadOnly(True)

        self.target_a_label = QLabel("代码块名：")
        self.target_b_label = QLabel("附加目标：")
        self.comment_label = QLabel("注释：")
        self.name_edit = QLineEdit()
        self.target_b_edit = QLineEdit()
        self.target_b_edit.setReadOnly(True)
        self.comment_edit = QTextEdit()
        self.comment_edit.setFixedHeight(90)

        info_form.addRow("所属模块：", self.module_edit)
        info_form.addRow("代码块类型：", self.kind_edit)
        info_form.addRow(self.target_a_label, self.name_edit)
        info_form.addRow(self.target_b_label, self.target_b_edit)
        info_form.addRow(self.comment_label, self.comment_edit)
        root.addWidget(info_group)

        editor_group = QGroupBox("代码工作台")
        editor_layout = QVBoxLayout(editor_group)
        editor_layout.setContentsMargins(12, 12, 12, 12)
        editor_layout.setSpacing(8)

        work_splitter = QSplitter(Qt.Orientation.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self.completion_hint_label = QLabel("Ctrl+Space 打开补全，双击右侧符号可插入。")
        self.completion_hint_label.setStyleSheet("color: #94a3b8;")
        left_layout.addWidget(self.completion_hint_label)

        self.code_edit = _CodeEditor()
        self.code_edit.setPlaceholderText("在这里编辑 C++ 代码块内容")
        self.code_edit.setProperty("class", "mono")
        self._highlighter = _CppSyntaxHighlighter(self.code_edit.document())
        left_layout.addWidget(self.code_edit, 1)
        work_splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        declaration_group = QGroupBox("声明预览")
        declaration_layout = QVBoxLayout(declaration_group)
        declaration_layout.setContentsMargins(10, 10, 10, 10)
        declaration_layout.setSpacing(6)

        before_label = QLabel("前置声明")
        before_label.setStyleSheet("font-weight: 600;")
        self.before_preview = QPlainTextEdit()
        self.before_preview.setReadOnly(True)
        self.before_preview.setProperty("class", "mono")
        self.before_preview.setMaximumHeight(140)

        after_label = QLabel("后置声明")
        after_label.setStyleSheet("font-weight: 600;")
        self.after_preview = QPlainTextEdit()
        self.after_preview.setReadOnly(True)
        self.after_preview.setProperty("class", "mono")
        self.after_preview.setMaximumHeight(100)

        declaration_layout.addWidget(before_label)
        declaration_layout.addWidget(self.before_preview)
        declaration_layout.addWidget(after_label)
        declaration_layout.addWidget(self.after_preview)
        right_layout.addWidget(declaration_group)

        symbol_group = QGroupBox("可用符号与函数")
        symbol_layout = QVBoxLayout(symbol_group)
        symbol_layout.setContentsMargins(10, 10, 10, 10)
        symbol_layout.setSpacing(6)

        self.symbol_filter_edit = QLineEdit()
        self.symbol_filter_edit.setPlaceholderText("筛选名称、类型或说明")
        self.symbol_tree = QTreeWidget()
        self.symbol_tree.setColumnCount(3)
        self.symbol_tree.setHeaderLabels(["名称", "类型", "说明"])
        self.symbol_tree.setRootIsDecorated(True)
        self.symbol_tree.setAlternatingRowColors(True)

        symbol_layout.addWidget(self.symbol_filter_edit)
        symbol_layout.addWidget(self.symbol_tree, 1)
        right_layout.addWidget(symbol_group, 1)

        diag_group = QGroupBox("基础诊断")
        diag_layout = QVBoxLayout(diag_group)
        diag_layout.setContentsMargins(10, 10, 10, 10)
        diag_layout.setSpacing(6)

        self.diag_list = QListWidget()
        diag_layout.addWidget(self.diag_list, 1)
        right_layout.addWidget(diag_group, 1)

        work_splitter.addWidget(right_panel)
        work_splitter.setStretchFactor(0, 3)
        work_splitter.setStretchFactor(1, 2)
        editor_layout.addWidget(work_splitter, 1)

        root.addWidget(editor_group, 1)

        self.btn_save.clicked.connect(self._on_save_clicked)
        self.btn_reload.clicked.connect(self._reload_saved_snapshot)
        self.code_edit.textChanged.connect(self._refresh_diagnostics)
        self.code_edit.completionRequested.connect(self._sync_completion_hint)
        self.symbol_filter_edit.textChanged.connect(self._refresh_symbol_tree)
        self.symbol_tree.itemDoubleClicked.connect(self._insert_symbol_from_item)

        self.reload(module_name, block_kind, block_data or {}, analysis_context=analysis_context or {})

    def _kind_label(self) -> str:
        if self.block_kind == "clock":
            return "时钟代码块"
        if self.block_kind == "service":
            return "服务代码块"
        if self.block_kind == "subreq":
            return "子实例请求代码块"
        if self.block_kind == "helper":
            return "帮助函数代码"
        return self.block_kind or "未知代码块"

    def _current_block_name(self, data: dict) -> str:
        if self.block_kind == "clock":
            return _strip(data.get("name", ""))
        if self.block_kind == "service":
            return _strip(data.get("port", ""))
        if self.block_kind == "subreq":
            inst = _strip(data.get("inst", ""))
            port = _strip(data.get("port", ""))
            return f"{inst}.{port}" if inst and port else inst or port
        if self.block_kind == "helper":
            return "helper_code"
        return _strip(data.get("name", ""))

    def _current_original_name(self, data: dict) -> str:
        if self.block_kind == "subreq":
            inst = _strip(data.get("inst", ""))
            port = _strip(data.get("port", ""))
            return f"{inst}|{port}"
        if self.block_kind == "service":
            return _strip(data.get("port", ""))
        if self.block_kind == "helper":
            return "helper_code"
        return _strip(data.get("name", ""))

    def _apply_kind_layout(self, data: dict):
        if self.block_kind == "clock":
            self.target_a_label.setText("代码块名：")
            self.name_edit.setReadOnly(False)
            self.target_b_label.setVisible(False)
            self.target_b_edit.setVisible(False)
            self.comment_label.setVisible(True)
            self.comment_edit.setVisible(True)
            return

        if self.block_kind == "service":
            self.target_a_label.setText("服务端口：")
            self.name_edit.setReadOnly(True)
            self.target_b_label.setVisible(False)
            self.target_b_edit.setVisible(False)
            self.comment_label.setVisible(False)
            self.comment_edit.setVisible(False)
            return

        if self.block_kind == "subreq":
            self.target_a_label.setText("子实例：")
            self.name_edit.setReadOnly(True)
            self.target_b_label.setText("请求端口：")
            self.target_b_label.setVisible(True)
            self.target_b_edit.setVisible(True)
            self.comment_label.setVisible(False)
            self.comment_edit.setVisible(False)
            return

        if self.block_kind == "helper":
            self.target_a_label.setText("代码段：")
            self.name_edit.setReadOnly(True)
            self.target_b_label.setVisible(False)
            self.target_b_edit.setVisible(False)
            self.comment_label.setVisible(False)
            self.comment_edit.setVisible(False)
            return

        self.target_a_label.setText("代码块名：")
        self.name_edit.setReadOnly(False)
        self.target_b_label.setVisible(False)
        self.target_b_edit.setVisible(False)
        self.comment_label.setVisible(True)
        self.comment_edit.setVisible(True)

    def _set_editor_values(self, data: dict):
        self.module_edit.setText(self.module_name)
        self.kind_edit.setText(self._kind_label())
        if self.block_kind == "clock":
            self.name_edit.setText(_strip(data.get("name", "")))
            self.target_b_edit.clear()
            self.comment_edit.setPlainText(_strip(data.get("comment", "")))
        elif self.block_kind == "service":
            self.name_edit.setText(_strip(data.get("port", "")))
            self.target_b_edit.clear()
            self.comment_edit.clear()
        elif self.block_kind == "subreq":
            self.name_edit.setText(_strip(data.get("inst", "")))
            self.target_b_edit.setText(_strip(data.get("port", "")))
            self.comment_edit.clear()
        elif self.block_kind == "helper":
            self.name_edit.setText("helper_code")
            self.target_b_edit.clear()
            self.comment_edit.clear()
        else:
            self.name_edit.setText(_strip(data.get("name", "")))
            self.target_b_edit.clear()
            self.comment_edit.setPlainText(_strip(data.get("comment", "")))
        self.code_edit.setPlainText(data.get("code", "") or "")

    def reload(self, module_name: str, block_kind: str, block_data: dict, analysis_context: dict | None = None):
        self.module_name = module_name
        self.block_kind = block_kind
        self.block_name = self._current_block_name(block_data)
        self.original_name = self._current_original_name(block_data)
        self._saved_snapshot = dict(block_data)

        self.title_label.setText(f"{self._kind_label()}：{self.block_name or '未命名'}")
        self._apply_kind_layout(block_data)
        self._set_editor_values(block_data)
        if analysis_context is not None:
            self.set_analysis_context(analysis_context)
        else:
            self._refresh_diagnostics()

    def set_analysis_context(self, context: dict | None):
        self._analysis_context = copy.deepcopy(context or {})
        self.before_preview.setPlainText(_normalized_text(self._analysis_context.get("prologue", "")))
        self.after_preview.setPlainText(_normalized_text(self._analysis_context.get("epilogue", "")))
        self._refresh_symbol_tree()
        self._sync_completion_hint()
        self._refresh_diagnostics()

    def _symbol_entries(self) -> list[dict]:
        return [copy.deepcopy(row) for row in _safe_list(self._analysis_context.get("symbols", []))]

    def _completion_words(self) -> list[str]:
        words: list[str] = []
        for row in self._symbol_entries():
            insert_text = _strip(row.get("insert", ""))
            name = _strip(row.get("name", ""))
            if insert_text:
                words.append(insert_text)
            if name:
                base_name = name[:-2] if name.endswith("()") else name
                words.append(base_name)
        return words

    def _sync_completion_hint(self):
        count = len({w for w in self._completion_words() if w})
        self.code_edit.set_completion_words(self._completion_words())
        self.completion_hint_label.setText(f"Ctrl+Space 打开补全，双击右侧符号可插入。当前可补全 {count} 项。")

    def _refresh_symbol_tree(self):
        filter_text = self.symbol_filter_edit.text().strip().lower()
        self.symbol_tree.clear()

        groups: dict[str, QTreeWidgetItem] = {}
        for row in self._symbol_entries():
            name = _strip(row.get("name", ""))
            category = _strip(row.get("category", "")) or "其他"
            detail = _strip(row.get("detail", ""))
            haystack = " ".join([name, category, detail]).lower()
            if filter_text and filter_text not in haystack:
                continue

            parent = groups.get(category)
            if parent is None:
                parent = QTreeWidgetItem([category, "", ""])
                font = QFont(parent.font(0))
                font.setBold(True)
                parent.setFont(0, font)
                groups[category] = parent
                self.symbol_tree.addTopLevelItem(parent)

            item = QTreeWidgetItem([name, _strip(row.get("kind", "")), detail])
            item.setData(0, Qt.ItemDataRole.UserRole, copy.deepcopy(row))
            if detail:
                item.setToolTip(0, detail)
                item.setToolTip(2, detail)
            parent.addChild(item)

        for parent in groups.values():
            parent.setExpanded(True)
        self.symbol_tree.resizeColumnToContents(0)
        self.symbol_tree.resizeColumnToContents(1)

    def _insert_symbol_from_item(self, item: QTreeWidgetItem, column: int):
        payload = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(payload, dict):
            return
        insert_text = _strip(payload.get("insert", "")) or _strip(payload.get("name", ""))
        if not insert_text:
            return
        cursor = self.code_edit.textCursor()
        cursor.insertText(insert_text)
        self.code_edit.setTextCursor(cursor)
        self.code_edit.setFocus()

    def _diagnostic_records(self) -> list[tuple[str, str]]:
        code = self.code_edit.toPlainText()
        diagnostics: list[tuple[str, str]] = []

        non_empty_lines = [line for line in code.splitlines() if line.strip()]
        if not non_empty_lines:
            diagnostics.append(("警告", "当前代码块内容为空，前端预览可保存，但生成时可能没有有效逻辑。"))

        braces = code.count("{") - code.count("}")
        if braces != 0:
            diagnostics.append(("错误", f"花括号数量不平衡：当前相差 {braces:+d}。"))

        parens = code.count("(") - code.count(")")
        if parens != 0:
            diagnostics.append(("错误", f"圆括号数量不平衡：当前相差 {parens:+d}。"))

        brackets = code.count("[") - code.count("]")
        if brackets != 0:
            diagnostics.append(("错误", f"方括号数量不平衡：当前相差 {brackets:+d}。"))

        if code.count('"') % 2 != 0:
            diagnostics.append(("错误", "检测到未闭合的双引号字符串。"))

        if "TODO" in code:
            diagnostics.append(("提示", "代码中包含 TODO 标记，保存前可以再确认是否需要补完。"))
        if "FIXME" in code:
            diagnostics.append(("警告", "代码中包含 FIXME 标记，建议在构建前处理。"))

        for note in _safe_list(self._analysis_context.get("notes", [])):
            note_text = _strip(note)
            if note_text:
                diagnostics.append(("提示", note_text))

        known_symbols = {
            word for word in self._completion_words()
            if word and re.fullmatch(r"[A-Za-z_]\w*", word)
        }
        known_symbols.update(_CPP_KEYWORDS)
        known_symbols.update(_CPP_COMMON_IDENTIFIERS)

        local_defs = {
            match.group(2)
            for match in re.finditer(
                r"\b(?:auto|bool|char|const|double|float|int|long|short|signed|unsigned|void|size_t|uint\d+_t|int\d+_t)\s+([*&\s]*)([A-Za-z_]\w*)",
                code,
            )
        }
        known_symbols.update(local_defs)

        unknown_tokens: set[str] = set()
        for token in re.findall(r"\b[A-Za-z_]\w*\b", code):
            if token in known_symbols:
                continue
            if len(token) <= 1:
                continue
            if token[0].isupper():
                unknown_tokens.add(token)
        if unknown_tokens:
            preview = "、".join(sorted(unknown_tokens)[:6])
            diagnostics.append(("提示", f"检测到一些未在当前前端符号表中声明的标识符：{preview}。"))

        if not diagnostics:
            diagnostics.append(("通过", "基础诊断未发现明显括号或字符串闭合问题。"))
        return diagnostics

    def _refresh_diagnostics(self):
        self.diag_list.clear()
        for level, message in self._diagnostic_records():
            item = QListWidgetItem(f"[{level}] {message}")
            color = {
                "错误": QColor("#ef4444"),
                "警告": QColor("#f59e0b"),
                "提示": QColor("#60a5fa"),
                "通过": QColor("#10b981"),
            }.get(level, QColor("#cbd5e1"))
            item.setForeground(color)
            self.diag_list.addItem(item)

    def _collect_data(self) -> dict | None:
        if self.block_kind == "clock":
            name = self.name_edit.text().strip()
            if not name:
                QMessageBox.warning(self, "输入无效", "代码块名不能为空。")
                return None
            return {
                "name": name,
                "comment": self.comment_edit.toPlainText().strip(),
                "code": self.code_edit.toPlainText(),
            }

        if self.block_kind == "service":
            port = self.name_edit.text().strip()
            if not port:
                QMessageBox.warning(self, "输入无效", "服务端口不能为空。")
                return None
            return {
                "port": port,
                "code": self.code_edit.toPlainText(),
            }

        if self.block_kind == "subreq":
            inst = self.name_edit.text().strip()
            port = self.target_b_edit.text().strip()
            if not inst or not port:
                QMessageBox.warning(self, "输入无效", "子实例名和请求端口名不能为空。")
                return None
            return {
                "inst": inst,
                "port": port,
                "code": self.code_edit.toPlainText(),
            }

        if self.block_kind == "helper":
            return {
                "name": "helper_code",
                "code": self.code_edit.toPlainText(),
            }

        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "输入无效", "代码块名不能为空。")
            return None
        return {
            "name": name,
            "comment": self.comment_edit.toPlainText().strip(),
            "code": self.code_edit.toPlainText(),
        }

    def _reload_saved_snapshot(self):
        self._set_editor_values(self._saved_snapshot)
        self._refresh_diagnostics()

    def _on_save_clicked(self):
        payload = self._collect_data()
        if payload is None:
            return
        self.saveRequested.emit(self.module_name, self.block_kind, self.original_name, payload)
