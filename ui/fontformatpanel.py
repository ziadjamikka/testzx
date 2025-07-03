import copy
import sys
from typing import List
import random
import json
import os

from qtpy.QtWidgets import QMenu, QMessageBox, QStackedLayout, QGraphicsDropShadowEffect, QLineEdit, QScrollArea, QSizePolicy, QHBoxLayout, QVBoxLayout, QFrame, QFontComboBox, QApplication, QPushButton, QCheckBox, QLabel, QWidget, QListWidget, QComboBox, QToolButton, QDialog, QSpinBox, QColorDialog, QDialogButtonBox, QInputDialog, QListWidgetItem, QDoubleSpinBox, QGridLayout
from qtpy.QtCore import Signal, Qt, QRectF
from qtpy.QtGui import QMouseEvent, QTextCursor, QFontMetrics, QIcon, QColor, QPixmap, QPainter, QContextMenuEvent

from utils.fontformat import FontFormat, dict_to_fontformat, fontformat_to_dict
from utils import shared
from utils.config import pcfg, save_text_styles, text_styles
from utils import config as C
from .stylewidgets import Widget, ColorPicker, ClickableLabel, CheckableLabel, TextChecker, FlowLayout, ScrollBar
from .textitem import TextBlkItem
from .text_graphical_effect import TextEffectPanel
from .combobox import SizeComboBox
from . import funcmaps as FM
from modules.style_manager import StyleManager


class IncrementalBtn(QPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFixedSize(13, 13)
        
class QFontChecker(QCheckBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if sys.platform == 'darwin':
            self.setStyleSheet("min-width: 45px")

class AlignmentChecker(QCheckBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if sys.platform == 'darwin':
            self.setStyleSheet("min-width: 15px")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.isChecked():
            return event.accept()
        return super().mousePressEvent(event)


class AlignmentBtnGroup(QFrame):
    param_changed = Signal(str, int)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.alignLeftChecker = AlignmentChecker(self)
        self.alignLeftChecker.clicked.connect(self.alignBtnPressed)
        self.alignCenterChecker = AlignmentChecker(self)
        self.alignCenterChecker.clicked.connect(self.alignBtnPressed)
        self.alignRightChecker = AlignmentChecker(self)
        self.alignRightChecker.clicked.connect(self.alignBtnPressed)
        self.alignLeftChecker.setObjectName("AlignLeftChecker")
        self.alignRightChecker.setObjectName("AlignRightChecker")
        self.alignCenterChecker.setObjectName("AlignCenterChecker")

        hlayout = QHBoxLayout(self)
        hlayout.addWidget(self.alignLeftChecker)
        hlayout.addWidget(self.alignCenterChecker)
        hlayout.addWidget(self.alignRightChecker)
        hlayout.setSpacing(0)

    def alignBtnPressed(self):
        btn = self.sender()
        if btn == self.alignLeftChecker:
            self.alignLeftChecker.setChecked(True)
            self.alignCenterChecker.setChecked(False)
            self.alignRightChecker.setChecked(False)
            self.param_changed.emit('alignment', 0)
        elif btn == self.alignRightChecker:
            self.alignRightChecker.setChecked(True)
            self.alignCenterChecker.setChecked(False)
            self.alignLeftChecker.setChecked(False)
            self.param_changed.emit('alignment', 2)
        else:
            self.alignCenterChecker.setChecked(True)
            self.alignLeftChecker.setChecked(False)
            self.alignRightChecker.setChecked(False)
            self.param_changed.emit('alignment', 1)
    
    def setAlignment(self, alignment: int):
        if alignment == 0:
            self.alignLeftChecker.setChecked(True)
            self.alignCenterChecker.setChecked(False)
            self.alignRightChecker.setChecked(False)
        elif alignment == 1:
            self.alignLeftChecker.setChecked(False)
            self.alignCenterChecker.setChecked(True)
            self.alignRightChecker.setChecked(False)
        else:
            self.alignLeftChecker.setChecked(False)
            self.alignCenterChecker.setChecked(False)
            self.alignRightChecker.setChecked(True)


class FormatGroupBtn(QFrame):
    param_changed = Signal(str, bool)
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.boldBtn = QFontChecker(self)
        self.boldBtn.setObjectName("FontBoldChecker")
        self.boldBtn.clicked.connect(self.setBold)
        self.italicBtn = QFontChecker(self)
        self.italicBtn.setObjectName("FontItalicChecker")
        self.italicBtn.clicked.connect(self.setItalic)
        self.underlineBtn = QFontChecker(self)
        self.underlineBtn.setObjectName("FontUnderlineChecker")
        self.underlineBtn.clicked.connect(self.setUnderline)
        hlayout = QHBoxLayout(self)
        hlayout.addWidget(self.boldBtn)
        hlayout.addWidget(self.italicBtn)
        hlayout.addWidget(self.underlineBtn)
        hlayout.setSpacing(0)

    def setBold(self):
        self.param_changed.emit('bold', self.boldBtn.isChecked())

    def setItalic(self):
        self.param_changed.emit('italic', self.italicBtn.isChecked())

    def setUnderline(self):
        self.param_changed.emit('underline', self.underlineBtn.isChecked())
    

class FontSizeBox(QFrame):
    param_changed = Signal(str, float)
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.upBtn = IncrementalBtn(self)
        self.upBtn.setObjectName("FsizeIncrementUp")
        self.downBtn = IncrementalBtn(self)
        self.downBtn.setObjectName("FsizeIncrementDown")
        self.upBtn.clicked.connect(self.onUpBtnClicked)
        self.downBtn.clicked.connect(self.onDownBtnClicked)
        self.fcombobox = SizeComboBox([1, 1000], 'size', self)
        self.fcombobox.addItems([
            "5", "5.5", "6.5", "7.5", "8", "9", "10", "10.5",
            "11", "12", "14", "16", "18", "20", '22', "26", "28", 
            "36", "48", "56", "72"
        ])
        self.fcombobox.param_changed.connect(self.param_changed)

        hlayout = QHBoxLayout(self)
        vlayout = QVBoxLayout()
        vlayout.addWidget(self.upBtn)
        vlayout.addWidget(self.downBtn)
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.setSpacing(0)
        hlayout.addLayout(vlayout)
        hlayout.addWidget(self.fcombobox)
        hlayout.setSpacing(3)
        hlayout.setContentsMargins(0, 0, 0, 0)

    def getFontSize(self) -> float:
        return self.fcombobox.value()

    def onUpBtnClicked(self):
        size = self.getFontSize()
        newsize = int(round(size * 1.25))
        if newsize == size:
            newsize += 1
        newsize = min(1000, newsize)
        if newsize != size:
            self.param_changed.emit('size', newsize)
            self.fcombobox.setCurrentText(str(newsize))
        
    def onDownBtnClicked(self):
        size = self.getFontSize()
        newsize = int(round(size * 0.75))
        if newsize == size:
            newsize -= 1
        newsize = max(1, newsize)
        if newsize != size:
            self.param_changed.emit('size', newsize)
            self.fcombobox.text_changed_by_user = False
            self.fcombobox.setCurrentText(str(newsize))



class SizeControlLabel(QLabel):
    
    btn_released = Signal()
    size_ctrl_changed = Signal(int)
    
    def __init__(self, parent=None, direction=0, text=''):
        super().__init__(parent)
        if text:
            self.setText(text)
        if direction == 0:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.cur_pos = 0
        self.direction = direction
        self.mouse_pressed = False

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.mouse_pressed = True
            if shared.FLAG_QT6:
                g_pos = e.globalPosition().toPoint()
            else:
                g_pos = e.globalPos()
            self.cur_pos = g_pos.x() if self.direction == 0 else g_pos.y()
        return super().mousePressEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.mouse_pressed = False
            self.btn_released.emit()
        return super().mouseReleaseEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self.mouse_pressed:
            if shared.FLAG_QT6:
                g_pos = e.globalPosition().toPoint()
            else:
                g_pos = e.globalPos()
            if self.direction == 0:
                new_pos = g_pos.x()
                self.size_ctrl_changed.emit(new_pos - self.cur_pos)
            else:
                new_pos = g_pos.y()
                self.size_ctrl_changed.emit(self.cur_pos - new_pos)
            self.cur_pos = new_pos
        return super().mouseMoveEvent(e)
    

class FontFamilyComboBox(QFontComboBox):
    param_changed = Signal(str, object)
    def __init__(self, emit_if_focused=True, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.currentFontChanged.connect(self.on_fontfamily_changed)
        self.emit_if_focused = emit_if_focused

    def on_fontfamily_changed(self):
        if self.emit_if_focused and not self.hasFocus():
            return
        self.param_changed.emit('family', self.currentText())

CHEVRON_SIZE = 20
def chevron_down():
    return QIcon(r'icons/chevron-down.svg').pixmap(CHEVRON_SIZE, CHEVRON_SIZE, mode=QIcon.Mode.Normal)

def chevron_right():
    return QIcon(r'icons/chevron-right.svg').pixmap(CHEVRON_SIZE, CHEVRON_SIZE, mode=QIcon.Mode.Normal)


class StyleLabel(QLineEdit):

    edit_finished = Signal()

    def __init__(self, style_name: str = None, parent = None):
        super().__init__(parent=parent)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0); border: none")
        self.setTextMargins(0, 0, 0, 0)
        self.setContentsMargins(0, 0, 0, 0)

        self.editingFinished.connect(self.edit_finished)
        self.setEnabled(False)
        
        if style_name is not None:
            self.setText(style_name)

        self.resizeToContent()
        self.edit_finished.connect(self.resizeToContent)

    def focusOutEvent(self, e) -> None:
        super().focusOutEvent(e)
        self.edit_finished.emit()

    def resizeToContent(self):
        fm = QFontMetrics(self.font())
        text = self.text()
        w = fm.boundingRect(text).width() + 5

        self.setFixedWidth(max(w, 32))


class ArrowLeftButton(QPushButton):
    pass


class ArrowRightButton(QPushButton):
    pass

class DeleteStyleButton(QPushButton):
    pass


class TextStyleLabel(Widget):

    style_name_edited = Signal()
    delete_btn_clicked = Signal()
    stylelabel_activated = Signal(bool)
    apply_fontfmt = Signal(FontFormat)

    def __init__(self, style_name: str = '', parent: Widget = None, fontfmt: FontFormat = None, active_stylename_edited: Signal = None):
        super().__init__(parent=parent)
        self._double_clicked = False
        self.active = False
        if fontfmt is None:
            if C.active_format is None:
                self.fontfmt = FontFormat()
            else:
                self.fontfmt = C.active_format.copy()
            self.fontfmt._style_name = style_name
        else:
            self.fontfmt = fontfmt
            style_name = fontfmt._style_name

        # following subwidgets must have parents, otherwise they kinda of pop up when creating it
        self.active_stylename_edited = active_stylename_edited
        self.stylelabel = StyleLabel(style_name, parent=self)
        self.stylelabel.edit_finished.connect(self.on_style_name_edited)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)

        self.setToolTip(self.tr('Click to set as Global format. Double click to edit name.'))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        BTN_SIZE = 14
        self.colorw = colorw = QLabel(parent=self)
        self.colorw.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.colorw.setStyleSheet("border-radius: 7px; border: none; background-color: rgba(0, 0, 0, 0);")
        d = int(BTN_SIZE * 2)
        self.colorw.setFixedSize(d, d)
        
        self.apply_btn = ArrowLeftButton(parent=self)
        self.apply_btn.setFixedSize(d, BTN_SIZE)
        self.apply_btn.setToolTip(self.tr('Apply Text Style'))
        self.apply_btn.clicked.connect(self.on_applybtn_clicked)
        self.update_btn = ArrowRightButton(parent=self)
        self.update_btn.setFixedSize(d, BTN_SIZE)
        self.update_btn.clicked.connect(self.on_updatebtn_clicked)
        self.update_btn.setToolTip(self.tr('Update from active style'))
        applyw = Widget(parent=self)
        applyw.setStyleSheet("border-radius: 7px; border: none")
        applylayout = QVBoxLayout(applyw)
        applylayout.setSpacing(0)
        applylayout.setContentsMargins(0, 0, 0, 0)
        applylayout.addWidget(self.apply_btn)
        applylayout.addWidget(self.update_btn)

        self.leftstack = QStackedLayout()
        self.leftstack.setContentsMargins(0, 0, 0, 0)
        self.leftstack.addWidget(colorw)
        self.leftstack.addWidget(applyw)

        self.delete_btn = DeleteStyleButton(parent=self)
        dsize = BTN_SIZE // 3 * 2
        self.delete_btn.setFixedSize(dsize, dsize)
        self.delete_btn.setToolTip(self.tr("Delete Style"))
        self.delete_btn.clicked.connect(self.on_delete_btn_clicked)
        self.delete_btn.setStyleSheet("border: none")
        
        hlayout = QHBoxLayout(self)
        hlayout.setContentsMargins(0, 0, 3, 0)
        hlayout.setSpacing(0)
        hlayout.addLayout(self.leftstack)
        hlayout.addWidget(self.stylelabel)
        hlayout.addWidget(self.delete_btn)

        self.updatePreview()

    def on_delete_btn_clicked(self, *args, **kwargs):
        self.delete_btn_clicked.emit()

    def on_updatebtn_clicked(self, *args, **kwargs):
        self.update_style()

    def on_applybtn_clicked(self, *args, **kwargs):
        self.apply_fontfmt.emit(self.fontfmt)

    def update_style(self, fontfmt: FontFormat = None):
        if fontfmt is None:
            fontfmt = C.active_format
        if fontfmt is None:
            return
        updated_keys = self.fontfmt.merge(fontfmt)
        if len(updated_keys) > 0:
            save_text_styles()
        
        preview_keys = {'family', 'frgb', 'srgb', 'stroke_width'}
        for k in updated_keys:
            if k in preview_keys:
                self.updatePreview()
                break
            
    def setActive(self, active: bool):
        self.active = active
        if active:
            self.setStyleSheet("border: 2px solid rgb(30, 147, 229)")
        else:
            self.setStyleSheet("")

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self._double_clicked:
                self._double_clicked = False
            else:
                active = not self.active
                self.setActive(active)
                self.stylelabel_activated.emit(active)
        return super().mouseReleaseEvent(event)

    def updatePreview(self):
        font = self.stylelabel.font()
        font.setFamily(self.fontfmt.family)
        self.stylelabel.setFont(font)

        d = int(self.colorw.width() * 0.66)
        radius = d / 2
        pixmap = QPixmap(d, d)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHints(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        draw_rect, draw_radius = QRectF(0, 0, d, d), radius
        if self.fontfmt.stroke_width > 0:
            r, g, b = self.fontfmt.srgb
            color = QColor(r, g, b, 255)
            painter.setBrush(color)
            painter.drawRoundedRect(draw_rect, draw_radius, draw_radius)
            draw_radius = draw_radius * 0.66
            offset = d / 2 - draw_radius
            draw_rect = QRectF(offset, offset, draw_radius*2, draw_radius*2)

        r, g, b = self.fontfmt.frgb
        color = QColor(r, g, b, 255)
        painter.setBrush(color)
        painter.drawRoundedRect(draw_rect, draw_radius, draw_radius)
        painter.end()
        self.colorw.setPixmap(pixmap)

        self.stylelabel.resizeToContent()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self._double_clicked = True
        self.startEdit()
        return super().mouseDoubleClickEvent(event)
    
    def startEdit(self, select_all=False):
        self.stylelabel.setEnabled(True)
        self.stylelabel.setFocus()
        self.setCursor(Qt.CursorShape.IBeamCursor)
        if select_all:
            self.stylelabel.selectAll()

    def setHoverEffect(self, hover: bool):
        try:
            if hover:
                se = QGraphicsDropShadowEffect()
                se.setBlurRadius(6)
                se.setOffset(0, 0)
                se.setColor(QColor(30, 147, 229))
                self.setGraphicsEffect(se)
            else:
                self.setGraphicsEffect(None)
        except RuntimeError:
            pass

    def enterEvent(self, event) -> None:
        self.setHoverEffect(True)
        self.leftstack.setCurrentIndex(1)
        self.delete_btn.setStyleSheet("image: url(icons/titlebar_close.svg); border: none")
        return super().enterEvent(event)
    
    def leaveEvent(self, event) -> None:
        self.setHoverEffect(False)
        self.leftstack.setCurrentIndex(0)
        self.delete_btn.setStyleSheet("image: \"none\"; border: none")
        return super().leaveEvent(event)
    
    def on_style_name_edited(self):
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stylelabel.setEnabled(False)
        new_name = self.stylelabel.text()
        if self.fontfmt._style_name != new_name:
            self.fontfmt._style_name = new_name
            save_text_styles()

        if self.active and self.active_stylename_edited is not None:
            self.active_stylename_edited.emit()

        self._double_clicked = False



class TextAreaStyleButton(QPushButton):
    pass



class TextStyleArea(QScrollArea):

    entered = False
    active_text_style_label_changed = Signal()
    apply_fontfmt = Signal(FontFormat)
    active_stylename_edited = Signal()
    export_style = Signal()
    import_style = Signal()

    def __init__(self, parent: Widget = None):
        super().__init__(parent)

        self.active_text_style_label: TextStyleLabel = None
        self.scrollContent = Widget()
        self.scrollContent.setObjectName("TextStyleAreaContent")
        self.setWidget(self.scrollContent)
        self.flayout = FlowLayout(self.scrollContent)
        # margin = 7
        # self.flayout.setVerticalSpacing(7)
        # self.flayout.setHorizontalSpacing(7)
        # self.flayout.setContentsMargins(margin, margin, margin, margin)
        self.setWidgetResizable(True)
        self.default_preset_name = self.tr('Style')
        
        self.new_btn = TextAreaStyleButton()
        self.new_btn.setObjectName("NewTextStyleButton")
        self.new_btn.setToolTip(self.tr("New Text Style"))
        self.new_btn.clicked.connect(self.on_newbtn_clicked)

        self.clear_btn = TextAreaStyleButton()
        self.clear_btn.setObjectName("ClearTextStyleButton")
        self.clear_btn.setToolTip(self.tr("Remove All"))
        self.clear_btn.clicked.connect(self.on_clearbtn_clicked)

        self.flayout.addWidget(self.new_btn)
        self.flayout.addWidget(self.clear_btn)

        # self.scrollContent.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)

        ScrollBar(Qt.Orientation.Vertical, self)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        ScrollBar(Qt.Orientation.Horizontal, self)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def on_newbtn_clicked(self, clicked = None):
        textstylelabel = self.new_textstyle_label()
        textstylelabel.startEdit(select_all=True)
        self.resizeToContent()

    def on_clearbtn_clicked(self, clicked = None):
        msg = QMessageBox()
        msg.setText(self.tr('Remove all styles?'))
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        ret = msg.exec_()
        if ret == QMessageBox.StandardButton.Yes:
            self.clearStyles()

    def count(self):
        return self.flayout.count() - 2
    
    def isEmpty(self):
        return self.count() < 1

    def new_textstyle_label(self, preset_name: str = None):
        if preset_name is None:
            sno = str(self.count() + 1)
            if len(sno) < 2:
                preset_name = self.default_preset_name + ' ' + sno
            else:
                preset_name = self.default_preset_name + sno
        textstylelabel = TextStyleLabel(preset_name, active_stylename_edited=self.active_stylename_edited)
        textstylelabel.stylelabel_activated.connect(self.on_stylelabel_activated)
        textstylelabel.delete_btn_clicked.connect(self.on_deletebtn_clicked)
        textstylelabel.apply_fontfmt.connect(self.apply_fontfmt)
        self.flayout.insertWidget(self.count(), textstylelabel)
        text_styles.append(textstylelabel.fontfmt)
        save_text_styles()
        return textstylelabel

    def resizeToContent(self):
        TEXTSTYLEAREA_MAXH = 200
        self.setFixedHeight(min(TEXTSTYLEAREA_MAXH, self.flayout.heightForWidth(self.width())))

    def resizeEvent(self, e):
        self.resizeToContent()
        return super().resizeEvent(e)
    
    def showNewBtn(self):
        if not self.new_btn.isVisible():
            self.new_btn.show()
            self.clear_btn.show()
            self.resizeToContent()

    def hideNewBtn(self):
        if self.new_btn.isVisible():
            self.new_btn.hide()
            self.clear_btn.hide()
            self.resizeToContent()

    def updateNewBtnVisibility(self):
        if self.isEmpty() or self.entered:
            self.showNewBtn()
        else:
            self.hideNewBtn()

    def enterEvent(self, event) -> None:
        self.entered = True
        self.showNewBtn()
        return super().enterEvent(event)
    
    def leaveEvent(self, event) -> None:
        self.entered = False
        if not self.isEmpty():
            self.hideNewBtn()
        return super().leaveEvent(event)

    def _clear_styles(self):
        self.active_text_style_label = None
        for _ in range(self.count()):
            w: TextStyleLabel = self.flayout.takeAt(0)
            if w is not None:
                if w.active:
                    w.setActive(False)
                    self.active_text_style_label_changed.emit()
                w.deleteLater()

    def _add_style_label(self, fontfmt: FontFormat):
        textstylelabel = TextStyleLabel(fontfmt=fontfmt, active_stylename_edited=self.active_stylename_edited)
        textstylelabel.delete_btn_clicked.connect(self.on_deletebtn_clicked)
        textstylelabel.stylelabel_activated.connect(self.on_stylelabel_activated)
        textstylelabel.apply_fontfmt.connect(self.apply_fontfmt)
        self.flayout.insertWidget(self.count(), textstylelabel)

    def on_deletebtn_clicked(self):
        w: TextStyleLabel = self.sender()
        self.removeStyleLabel(w)

    def on_stylelabel_activated(self, active: bool):
        if self.active_text_style_label is not None:
            self.active_text_style_label.setActive(False)
            self.active_text_style_label = None
        if active:
            self.active_text_style_label = self.sender()
        self.active_text_style_label_changed.emit()

    def clearStyles(self):
        if self.isEmpty():
            return
        self._clear_styles()
        self.updateNewBtnVisibility()
        text_styles.clear()
        save_text_styles()

    def removeStyleLabel(self, w: TextStyleLabel):
        for i, item in enumerate(self.flayout._items):
            if item.widget() is w:
                if w is self.active_text_style_label:
                    w.setActive(False)
                    self.active_text_style_label = None
                    self.active_text_style_label_changed.emit()
                self.flayout.takeAt(i)
                self.flayout.update()
                self.updateNewBtnVisibility()
                text_styles.pop(i)
                save_text_styles()
                w.deleteLater()
                break
        
    def initStyles(self, styles: List[FontFormat]):
        assert self.isEmpty()
        for style in styles:
            self._add_style_label(style)
        if not self.isEmpty():
            self.new_btn.hide()
            self.clear_btn.hide()
            self.resizeToContent()

    def setStyles(self, styles: List[FontFormat], save_styles = False):
        self._clear_styles()
        for style in styles:
            self._add_style_label(style)
        
        self.updateNewBtnVisibility()
        self.resizeToContent()
        if save_styles:
            save_text_styles()

    def contextMenuEvent(self, e: QContextMenuEvent):
        menu = QMenu()

        new_act = menu.addAction(self.tr('New Text Style'))
        removeall_act = menu.addAction(self.tr('Remove all'))
        menu.addSeparator()
        import_act = menu.addAction(self.tr('Import Text Styles'))
        export_act = menu.addAction(self.tr('Export Text Styles'))
        
        rst = menu.exec_(e.globalPos())

        if rst == new_act:
            self.on_newbtn_clicked()
        elif rst == removeall_act:
            self.on_clearbtn_clicked()
        elif rst == import_act:
            self.import_style.emit()
        elif rst == export_act:
            self.export_style.emit()

        return super().contextMenuEvent(e)


class ExpandLabel(Widget):

    clicked = Signal()

    def __init__(self, text=None, parent=None, expanded=False, *args, **kwargs):
        super().__init__(parent=parent, *args, **kwargs)
        self.textlabel = QLabel(self)
        self.textlabel.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        font = self.textlabel.font()
        if shared.ON_MACOS:
            font.setPointSize(13)
        else:
            font.setPointSizeF(10)
        self.textlabel.setFont(font)
        self.arrowlabel = QLabel(self)
        self.arrowlabel.setFixedSize(CHEVRON_SIZE, CHEVRON_SIZE)
        self.arrowlabel.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        if text is not None:
            self.textlabel.setText(text)
        layout = QHBoxLayout(self)
        layout.addWidget(self.arrowlabel)
        layout.addWidget(self.textlabel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        layout.addStretch(-1)
    
        self.expanded = False
        self.setExpand(expanded)
        self.setFixedHeight(26)

    def setExpand(self, expand: bool):
        self.expanded = expand
        if expand:
            self.arrowlabel.setPixmap(chevron_down())
        else:
            self.arrowlabel.setPixmap(chevron_right())

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.setExpand(not self.expanded)
            pcfg.expand_tstyle_panel = self.expanded
            self.clicked.emit()
        return super().mousePressEvent(e)


class TextStylePanel(Widget):

    def __init__(self, text=None, parent=None, expanded=True, *args, **kwargs):
        super().__init__(parent=parent, *args, **kwargs)
        
        self.title_label = ExpandLabel(text, self, expanded=expanded)
        self.style_area = TextStyleArea(self)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title_label)
        layout.addWidget(self.style_area)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        if not expanded:
            self.style_area.hide()
        
        self.title_label.clicked.connect(self.on_title_label_clicked)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)

    def expand(self):
        if not self.title_label.expanded:
            self.title_label.setExpand(True)
        if self.style_area.isHidden():
            self.style_area.show()

    def on_title_label_clicked(self):
        if self.title_label.expanded:
            self.style_area.show()
        else:
            self.style_area.hide()

    def setTitle(self, text: str):
        self.title_label.textlabel.setText(text)

    def elidedText(self, text: str):
        fm = QFontMetrics(self.title_label.font())
        return fm.elidedText(text, Qt.TextElideMode.ElideRight, self.style_area.width() - 40)

    def title(self) -> str:
        return self.title_label.textlabel.text()


class CollapsiblePanel(QFrame):
    def __init__(self, title, content_widget, parent=None):
        super().__init__(parent)
        self.toggle_button = QToolButton(text=title, checkable=True, checked=True)
        self.toggle_button.setStyleSheet("QToolButton { font-weight: bold; }")
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.DownArrow)
        self.toggle_button.clicked.connect(self.toggle_panel)
        self.content_widget = content_widget
        self.content_widget.setVisible(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toggle_button)
        layout.addWidget(self.content_widget)
    def toggle_panel(self):
        visible = not self.content_widget.isVisible()
        self.content_widget.setVisible(visible)
        self.toggle_button.setArrowType(Qt.DownArrow if visible else Qt.RightArrow)


class StyleEditDialog(QDialog):
    def __init__(self, parent=None, style=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Style" if style else "Add Style")
        layout = QVBoxLayout(self)
        grid = QGridLayout()
        row = 0
        # الصف الأول: الاسم، الخط، الحجم
        grid.addWidget(QLabel("Name:"), row, 0)
        self.name_edit = QLineEdit()
        grid.addWidget(self.name_edit, row, 1)
        grid.addWidget(QLabel("Font:"), row, 2)
        self.font_combo = QFontComboBox()
        grid.addWidget(self.font_combo, row, 3)
        grid.addWidget(QLabel("Size:"), row, 4)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(1, 200)
        grid.addWidget(self.size_spin, row, 5)
        row += 1
        # الصف الثاني: اللون، بولد، مائل، تحته خط، محاذاة
        grid.addWidget(QLabel("Color:"), row, 0)
        self.color_btn = QPushButton()
        self.color_btn.clicked.connect(self.choose_color)
        grid.addWidget(self.color_btn, row, 1)
        self.bold_chk = QCheckBox("Bold")
        grid.addWidget(self.bold_chk, row, 2)
        self.italic_chk = QCheckBox("Italic")
        grid.addWidget(self.italic_chk, row, 3)
        self.underline_chk = QCheckBox("Underline")
        grid.addWidget(self.underline_chk, row, 4)
        grid.addWidget(QLabel("Align:"), row, 5)
        self.align_combo = QComboBox()
        self.align_combo.addItems(["left", "center", "right"])
        grid.addWidget(self.align_combo, row, 6)
        row += 1
        # الصف الثالث: تباعد الحروف، تباعد الأسطر، نوع الحروف، دوران
        grid.addWidget(QLabel("Letter Spacing:"), row, 0)
        self.letter_spacing_spin = QDoubleSpinBox()
        self.letter_spacing_spin.setRange(-10.0, 20.0)
        self.letter_spacing_spin.setSingleStep(0.1)
        grid.addWidget(self.letter_spacing_spin, row, 1)
        grid.addWidget(QLabel("Line Height:"), row, 2)
        self.line_height_spin = QDoubleSpinBox()
        self.line_height_spin.setRange(0.5, 5.0)
        self.line_height_spin.setSingleStep(0.1)
        grid.addWidget(self.line_height_spin, row, 3)
        grid.addWidget(QLabel("Case:"), row, 4)
        self.case_combo = QComboBox()
        self.case_combo.addItems(["none", "upper", "lower"])
        grid.addWidget(self.case_combo, row, 5)
        grid.addWidget(QLabel("Rotation:"), row, 6)
        self.rotation_spin = QSpinBox()
        self.rotation_spin.setRange(-180, 180)
        grid.addWidget(self.rotation_spin, row, 7)
        row += 1
        # الصف الرابع: لون وسمك الحدود، خصائص الظل
        grid.addWidget(QLabel("Stroke Color:"), row, 0)
        self.stroke_color_btn = QPushButton()
        self.stroke_color_btn.clicked.connect(self.choose_stroke_color)
        grid.addWidget(self.stroke_color_btn, row, 1)
        grid.addWidget(QLabel("Stroke Width:"), row, 2)
        self.stroke_width_spin = QDoubleSpinBox()
        self.stroke_width_spin.setRange(0.0, 20.0)
        self.stroke_width_spin.setSingleStep(0.1)
        grid.addWidget(self.stroke_width_spin, row, 3)
        grid.addWidget(QLabel("Shadow Color:"), row, 4)
        self.shadow_color_btn = QPushButton()
        self.shadow_color_btn.clicked.connect(self.choose_shadow_color)
        grid.addWidget(self.shadow_color_btn, row, 5)
        grid.addWidget(QLabel("Shadow Blur:"), row, 6)
        self.shadow_blur_spin = QDoubleSpinBox()
        self.shadow_blur_spin.setRange(0.0, 20.0)
        self.shadow_blur_spin.setSingleStep(0.1)
        grid.addWidget(self.shadow_blur_spin, row, 7)
        row += 1
        # الصف الخامس: shadow offset x/y، نص المعاينة
        grid.addWidget(QLabel("Shadow Offset X:"), row, 0)
        self.shadow_offset_x_spin = QSpinBox()
        self.shadow_offset_x_spin.setRange(-100, 100)
        grid.addWidget(self.shadow_offset_x_spin, row, 1)
        grid.addWidget(QLabel("Shadow Offset Y:"), row, 2)
        self.shadow_offset_y_spin = QSpinBox()
        self.shadow_offset_y_spin.setRange(-100, 100)
        grid.addWidget(self.shadow_offset_y_spin, row, 3)
        grid.addWidget(QLabel("Preview Text:"), row, 4)
        self.preview_text_edit = QLineEdit("Preview Text")
        grid.addWidget(self.preview_text_edit, row, 5, 1, 3)
        layout.addLayout(grid)
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        self.color = QColor("#000000")
        self.stroke_color = QColor("#000000")
        self.shadow_color = QColor("#000000")
        if style is not None:
            self.name_edit.setText(getattr(style, "name", ""))
            self.font_combo.setCurrentText(getattr(style, "font", "Arial"))
            self.size_spin.setValue(getattr(style, "size", 24))
            self.color = QColor(getattr(style, "color", "#000000"))
            self.bold_chk.setChecked(getattr(style, "bold", False))
            self.italic_chk.setChecked(getattr(style, "italic", False))
            self.underline_chk.setChecked(getattr(style, "underline", False))
            self.align_combo.setCurrentText(getattr(style, "align", "left"))
            self.letter_spacing_spin.setValue(float(getattr(style, "letter_spacing", 0.0)))
            self.line_height_spin.setValue(float(getattr(style, "line_height", 1.0)))
            self.stroke_color = QColor(getattr(style, "stroke_color", "#000000"))
            self.stroke_width_spin.setValue(float(getattr(style, "stroke_width", 0.0)))
            self.shadow_color = QColor(getattr(style, "shadow_color", "#000000"))
            self.shadow_blur_spin.setValue(float(getattr(style, "shadow_blur", 0.0)))
            self.shadow_offset_x_spin.setValue(int(getattr(style, "shadow_offset_x", 0)))
            self.shadow_offset_y_spin.setValue(int(getattr(style, "shadow_offset_y", 0)))
            self.case_combo.setCurrentText(getattr(style, "case", "none"))
            self.rotation_spin.setValue(int(getattr(style, "rotation", 0)))
            self.preview_text_edit.setText(getattr(style, "preview_text", "Preview Text"))
        self.update_color_btn()
        self.update_stroke_color_btn()
        self.update_shadow_color_btn()
    def choose_color(self):
        color = QColorDialog.getColor(self.color, self)
        if color.isValid():
            self.color = color
            self.update_color_btn()
    def choose_stroke_color(self):
        color = QColorDialog.getColor(self.stroke_color, self)
        if color.isValid():
            self.stroke_color = color
            self.update_stroke_color_btn()
    def choose_shadow_color(self):
        color = QColorDialog.getColor(self.shadow_color, self)
        if color.isValid():
            self.shadow_color = color
            self.update_shadow_color_btn()
    def update_color_btn(self):
        self.color_btn.setStyleSheet(f"background: {self.color.name()};")
    def update_stroke_color_btn(self):
        self.stroke_color_btn.setStyleSheet(f"background: {self.stroke_color.name()};")
    def update_shadow_color_btn(self):
        self.shadow_color_btn.setStyleSheet(f"background: {self.shadow_color.name()};")
    def get_style(self):
        return {
            "name": self.name_edit.text(),
            "font": self.font_combo.currentText(),
            "size": self.size_spin.value(),
            "color": self.color.name(),
            "bold": self.bold_chk.isChecked(),
            "italic": self.italic_chk.isChecked(),
            "underline": self.underline_chk.isChecked(),
            "align": self.align_combo.currentText(),
            "letter_spacing": self.letter_spacing_spin.value(),
            "line_height": self.line_height_spin.value(),
            "stroke_color": self.stroke_color.name(),
            "stroke_width": self.stroke_width_spin.value(),
            "shadow_color": self.shadow_color.name(),
            "shadow_blur": self.shadow_blur_spin.value(),
            "shadow_offset_x": self.shadow_offset_x_spin.value(),
            "shadow_offset_y": self.shadow_offset_y_spin.value(),
            "case": self.case_combo.currentText(),
            "rotation": self.rotation_spin.value(),
            "preview_text": self.preview_text_edit.text()
        }

STYLES_FILE = 'config/textstyles/styles.json'

class StyleListPanel(QWidget):
    style_applied = Signal(object)  # FontFormat
    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = StyleManager()
        self._filtered_styles = []
        self.init_ui()
        self.load_groups()
        self.add_group_btn.clicked.connect(self.add_new_group)
        self.delete_group_btn.clicked.connect(self.delete_selected_group)
        self.groups_combo.currentIndexChanged.connect(self.on_group_changed)
        self.btn_add.clicked.connect(self.add_style)
        self.btn_edit.clicked.connect(self.edit_style)
        self.btn_delete.clicked.connect(self.delete_style)
        self.btn_up.clicked.connect(lambda: self.move_style(-1))
        self.btn_down.clicked.connect(lambda: self.move_style(1))
        self.btn_duplicate = QPushButton("Duplicate")
        self.btn_duplicate.setToolTip("Duplicate selected style")
        self.btn_duplicate.clicked.connect(self.duplicate_style)
        self.layout().addWidget(self.btn_duplicate)
        self.btn_apply = QPushButton("Apply")
        self.btn_apply.setToolTip("Apply selected style to selected text")
        self.btn_apply.clicked.connect(self.apply_style)
        self.layout().addWidget(self.btn_apply)
        self.btn_import = QPushButton("Import")
        self.btn_import.setToolTip("Import styles from file")
        self.btn_import.clicked.connect(self.import_styles)
        self.layout().addWidget(self.btn_import)
        self.btn_export = QPushButton("Export")
        self.btn_export.setToolTip("Export styles to file")
        self.btn_export.clicked.connect(self.export_styles)
        self.layout().addWidget(self.btn_export)

    def init_ui(self):
        layout = QVBoxLayout(self)
        self.groups_combo = QComboBox()
        layout.addWidget(self.groups_combo)
        group_btn_layout = QHBoxLayout()
        self.add_group_btn = QPushButton("+")
        self.delete_group_btn = QPushButton("-")
        group_btn_layout.addWidget(self.add_group_btn)
        group_btn_layout.addWidget(self.delete_group_btn)
        layout.addLayout(group_btn_layout)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("search style...")
        self.search_box.setStyleSheet('QLineEdit { color: white; } QLineEdit::placeholder { color: white; }')
        self.search_box.textChanged.connect(self.load_styles)
        layout.addWidget(self.search_box)

        self.style_list = QListWidget()
        self.style_list.currentRowChanged.connect(self.update_preview)
        self.style_list.setDragDropMode(QListWidget.InternalMove)
        self.style_list.model().rowsMoved.connect(self.on_styles_reordered)
        layout.addWidget(self.style_list)

        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Add")
        self.btn_edit = QPushButton("Edit")
        self.btn_delete = QPushButton("Delete")
        self.btn_up = QPushButton("↑")
        self.btn_down = QPushButton("↓")
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addWidget(self.btn_up)
        btn_layout.addWidget(self.btn_down)
        layout.addLayout(btn_layout)

        self.preview = QLabel("Preview")
        self.preview.setFixedHeight(40)
        layout.addWidget(self.preview)

    def load_groups(self):
        self.groups_combo.clear()
        self.groups_combo.addItem("Default")
        for group in self.manager.get_groups():
            if group.get("name") != "Default":
                self.groups_combo.addItem(group["name"])
        self.on_group_changed()

    def add_new_group(self):
        group_name, ok = QInputDialog.getText(self, "Add Group", "Enter group name:")
        if ok and group_name.strip():
            self.manager.add_group(group_name.strip())
            self.load_groups()
            idx = self.groups_combo.findText(group_name.strip())
            if idx != -1:
                self.groups_combo.setCurrentIndex(idx)
            self.on_group_changed()

    def delete_selected_group(self):
        group_name = self.groups_combo.currentText()
        if group_name == "Default":
            QMessageBox.warning(self, "Error", "Cannot delete Default group.")
            return
        reply = QMessageBox.question(self, "Delete Group", f"Delete group '{group_name}'?")
        if reply == QMessageBox.Yes:
            groups = self.manager.get_groups()
            idx = next((i for i, g in enumerate(groups) if g.get("name") == group_name), -1)
            if idx != -1:
                self.manager.remove_group(idx)
            self.load_groups()
            idx = self.groups_combo.findText("Default")
            if idx != -1:
                self.groups_combo.setCurrentIndex(idx)
            self.on_group_changed()

    def on_group_changed(self):
        group = self.groups_combo.currentText()
        self.load_styles(group)

    def load_styles(self, group=None):
        if group is None:
            group = self.groups_combo.currentText()
        self.style_list.clear()
        if group == "Default":
            styles = self.manager.get_ungrouped_styles()
        else:
            groups = self.manager.get_groups()
            idx = next((i for i, g in enumerate(groups) if g.get("name") == group), -1)
            styles = self.manager.get_group_styles(idx) if idx != -1 else []
        search = self.search_box.text().strip().lower()
        if search:
            self._filtered_styles = [s for s in styles if search in getattr(s, '_style_name', s.get('name', '')).lower()]
        else:
            self._filtered_styles = styles
        for style in self._filtered_styles:
            name = getattr(style, '_style_name', style.get('name', ''))
            if not name or name.strip() == "":
                name = f"Style_{random.randint(1000,9999)}"
                if hasattr(style, 'name'):
                    style.name = name
            item = QListWidgetItem(name)
            item.setForeground(QColor('white'))
            self.style_list.addItem(item)
        self.update_preview()

    def update_preview(self):
        idx = self.style_list.currentRow()
        group = self.groups_combo.currentText()
        styles = self._filtered_styles if hasattr(self, '_filtered_styles') and self._filtered_styles else self.manager.get_styles_by_group(group)
        if 0 <= idx < len(styles):
            style = styles[idx]
            font = getattr(style, "family", "Arial")
            size = getattr(style, "size", 24)
            color = getattr(style, "frgb", (0,0,0))
            bold = getattr(style, "bold", False)
            italic = getattr(style, "italic", False)
            qfont = self.preview.font()
            qfont.setFamily(font)
            qfont.setPointSize(size)
            qfont.setBold(bold)
            qfont.setItalic(italic)
            self.preview.setFont(qfont)
            self.preview.setStyleSheet(f"color: rgb({color[0]}, {color[1]}, {color[2]});")
            # نص معاينة فعلي
            preview_text = "The quick brown fox jumps over the lazy dog. 1234567890\nالنص العربي التجريبي" 
            self.preview.setText(preview_text)
        else:
            self.preview.setText("Preview")

    def add_style(self):
        from utils.fontformat import dict_to_fontformat, fontformat_to_dict
        dlg = StyleEditDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            style = dlg.get_style()
            style = fontformat_to_dict(dict_to_fontformat(style))
            group = self.groups_combo.currentText()
            if group == "Default":
                self.manager.add_ungrouped_style(style)
            else:
                groups = self.manager.get_groups()
                idx = next((i for i, g in enumerate(groups) if g.get("name") == group), -1)
                if idx != -1:
                    self.manager.add_style_to_group(idx, style)
            self.load_styles()

    def edit_style(self):
        from utils.fontformat import dict_to_fontformat, fontformat_to_dict
        group = self.groups_combo.currentText()
        idx = self.style_list.currentRow()
        if group == "Default":
            if 0 <= idx < len(self.manager.get_ungrouped_styles()):
                style = self.manager.get_ungrouped_styles()[idx]
                dlg = StyleEditDialog(self, style)
                if dlg.exec_() == QDialog.Accepted:
                    new_style = dlg.get_style()
                    new_style = fontformat_to_dict(dict_to_fontformat(new_style))
                    self.manager.update_ungrouped_style(idx, new_style)
        else:
            groups = self.manager.get_groups()
            gidx = next((i for i, g in enumerate(groups) if g.get("name") == group), -1)
            if gidx != -1:
                styles = self.manager.get_group_styles(gidx)
                if 0 <= idx < len(styles):
                    style = styles[idx]
                    dlg = StyleEditDialog(self, style)
                    if dlg.exec_() == QDialog.Accepted:
                        new_style = dlg.get_style()
                        new_style = fontformat_to_dict(dict_to_fontformat(new_style))
                        self.manager.update_group_style(gidx, idx, new_style)
        self.load_styles()

    def delete_style(self):
        group = self.groups_combo.currentText()
        idx = self.style_list.currentRow()
        if group == "Default":
            if 0 <= idx < len(self.manager.get_ungrouped_styles()):
                reply = QMessageBox.question(self, "Delete", "Are you sure?")
                if reply == QMessageBox.Yes:
                    self.manager.delete_ungrouped_style(idx)
        else:
            groups = self.manager.get_groups()
            gidx = next((i for i, g in enumerate(groups) if g.get("name") == group), -1)
            if gidx != -1:
                styles = self.manager.get_group_styles(gidx)
                if 0 <= idx < len(styles):
                    reply = QMessageBox.question(self, "Delete", "Are you sure?")
                    if reply == QMessageBox.Yes:
                        self.manager.delete_group_style(gidx, idx)
        self.load_styles()

    def duplicate_style(self):
        data = self.load_styles_from_file()
        group = self.groups_combo.currentText()
        idx = self.style_list.currentRow()
        if group == "Default":
            styles = data.get("ungrouped", [])
        else:
            group_obj = next((g for g in data.get("groups", []) if g["name"] == group), None)
            styles = group_obj["styles"] if group_obj else []
        if 0 <= idx < len(styles):
            import copy
            new_style = copy.deepcopy(styles[idx])
            new_style["name"] = f"{new_style.get('name', 'Style')} Copy"
            styles.append(new_style)
            with open(STYLES_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.update_styles_list()

    def apply_style(self):
        group = self.groups_combo.currentText()
        idx = self.style_list.currentRow()
        styles = self._filtered_styles if hasattr(self, '_filtered_styles') and self._filtered_styles else self.manager.get_styles_by_group(group)
        if 0 <= idx < len(styles):
            self.apply_current_style_to_selection(styles[idx])

    def filter_styles(self, text):
        self.load_styles()

    def on_styles_reordered(self, parent, start, end, dest, row):
        group = self.groups_combo.currentText()
        styles = self.manager.get_styles_by_group(group)
        # styles هنا هي القائمة الأصلية (FontFormat)
        # احسب الترتيب الجديد بناءً على مواضع العناصر في QListWidget
        new_order = []
        for i in range(self.style_list.count()):
            name = self.style_list.item(i).text()
            for s in styles:
                if getattr(s, '_style_name', getattr(s, 'name', '')) == name:
                    new_order.append(s)
                    break
        self.manager.styles[group] = new_order
        self.manager.save_styles()

    def import_styles(self):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        import json
        fname, _ = QFileDialog.getOpenFileName(self, "Import Styles", "", "JSON Files (*.json)")
        if fname:
            try:
                with open(fname, 'r', encoding='utf-8') as f:
                    imported = json.load(f)
                reply = QMessageBox.question(self, "Import", "Replace current styles or merge?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                data = self.load_styles_from_file()
                if reply == QMessageBox.Yes:
                    data["ungrouped"] = imported.get("ungrouped", [])
                    data["groups"] = imported.get("groups", [])
                else:
                    data["ungrouped"].extend(imported.get("ungrouped", []))
                    # دمج الجروبات
                    imported_groups = imported.get("groups", [])
                    for ig in imported_groups:
                        existing = next((g for g in data["groups"] if g["name"] == ig["name"]), None)
                        if existing:
                            existing["styles"].extend(ig["styles"])
                        else:
                            data["groups"].append(ig)
                with open(STYLES_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                self.update_styles_list()
            except Exception as e:
                QMessageBox.warning(self, "Import Error", str(e))

    def export_styles(self):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        import json
        fname, _ = QFileDialog.getSaveFileName(self, "Export Styles", "", "JSON Files (*.json)")
        if fname:
            try:
                data = self.load_styles_from_file()
                to_save = {"ungrouped": data.get("ungrouped", []), "groups": data.get("groups", [])}
                with open(fname, 'w', encoding='utf-8') as f:
                    json.dump(to_save, f, ensure_ascii=False, indent=2)
            except Exception as e:
                QMessageBox.warning(self, "Export Error", str(e))

    def apply_current_style_to_selection(self, fontfmt=None):
        # إذا لم يُحدد ستايل، استخدم الحالي
        if fontfmt is None:
            group = self.groups_combo.currentText()
            idx = self.style_list.currentRow()
            styles = self._filtered_styles if hasattr(self, '_filtered_styles') and self._filtered_styles else self.manager.get_styles_by_group(group)
            if 0 <= idx < len(styles):
                fontfmt = styles[idx]
            else:
                return
        # إذا كان fontfmt dict (من styles.json)، حوله إلى FontFormat
        from utils.fontformat import dict_to_fontformat, FontFormat
        if isinstance(fontfmt, dict):
            fontfmt = dict_to_fontformat(fontfmt)
        # استدعي دالة التطبيق المركزية في MainWindow عبر st_manager
        mainwindow = self.parent()
        while mainwindow is not None and not hasattr(mainwindow, 'st_manager'):
            mainwindow = mainwindow.parent()
        if mainwindow is not None and hasattr(mainwindow, 'st_manager'):
            mainwindow.st_manager.apply_fontformat(fontfmt)

    def load_styles_from_file(self):
        try:
            if not os.path.exists(STYLES_FILE):
                return {"groups": [], "ungrouped": []}
            with open(STYLES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading styles: {e}")
            return {"groups": [], "ungrouped": []}

    def save_style(self, style_name, style_properties):
        try:
            styles_data = self.load_styles_from_file()
            styles_data[style_name] = style_properties
            with open(STYLES_FILE, 'w', encoding='utf-8') as f:
                json.dump(styles_data, f, indent=2, ensure_ascii=False)
            self.update_styles_list()
            return True
        except Exception as e:
            print(f"Error saving style: {e}")
            return False

    def update_styles_list(self):
        self.style_list.clear()
        data = self.load_styles_from_file()
        group = self.groups_combo.currentText()
        if group == "Default":
            styles = data.get("ungrouped", [])
        else:
            # ابحث عن الجروب بالاسم
            group_obj = next((g for g in data.get("groups", []) if g["name"] == group), None)
            styles = group_obj["styles"] if group_obj else []
        for style in styles:
            item = QListWidgetItem(style.get("name", ""))
            item.setForeground(QColor('white'))
            self.style_list.addItem(item)
        if self.style_list.count() > 0:
            self.style_list.setCurrentRow(0)
            self.update_preview()

    def update_preview(self):
        current_item = self.style_list.currentItem()
        if not current_item:
            return
        style_name = current_item.text()
        data = self.load_styles_from_file()
        group = self.groups_combo.currentText()
        if group == "Default":
            styles = data.get("ungrouped", [])
        else:
            group_obj = next((g for g in data.get("groups", []) if g["name"] == group), None)
            styles = group_obj["styles"] if group_obj else []
        for style in styles:
            if style.get("name", "") == style_name:
                # إعداد CSS للمعاينة
                css = f"""
                QLabel {{
                    font-family: {style.get('font', style.get('font_family', 'Arial'))};
                    font-size: {style.get('size', style.get('font_size', 12))}px;
                    color: {style.get('color', '#000000')};
                    font-weight: {'bold' if style.get('bold', False) else 'normal'};
                    font-style: {'italic' if style.get('italic', False) else 'normal'};
                    text-decoration: {'underline' if style.get('underline', False) else 'none'};
                    letter-spacing: {style.get('letter_spacing', 0.0)}px;
                    line-height: {style.get('line_height', 1.0)};
                    text-transform: {style.get('case', 'none') if style.get('case', 'none') in ['uppercase','lowercase'] else 'none'};
                """
                align = style.get('align', 'left')
                if align == 'center':
                    css += "text-align: center;"
                elif align == 'right':
                    css += "text-align: right;"
                else:
                    css += "text-align: left;"
                if style.get('stroke_width', 0.0) > 0.0:
                    css += f"text-shadow: 1px 0 {style.get('stroke_color', '#000')}, 0 1px {style.get('stroke_color', '#000')}, -1px 0 {style.get('stroke_color', '#000')}, 0 -1px {style.get('stroke_color', '#000')};"
                if style.get('shadow_blur', 0.0) > 0.0:
                    css += f"box-shadow: {style.get('shadow_offset_x', 0)}px {style.get('shadow_offset_y', 0)}px {style.get('shadow_blur', 0)}px {style.get('shadow_color', '#000')};"
                css += "}"
                self.preview.setStyleSheet(css)
                preview_text = style.get("preview_text", style_name)
                if style.get('case', 'none') == 'upper':
                    preview_text = preview_text.upper()
                elif style.get('case', 'none') == 'lower':
                    preview_text = preview_text.lower()
                rotation = style.get('rotation', 0)
                if rotation:
                    self.preview.setText(f"<span style='display:inline-block; transform:rotate({rotation}deg);'>{preview_text}</span>")
                else:
                    self.preview.setText(preview_text)
                break

    def add_new_style(self):
        style_name, ok = QInputDialog.getText(self, "Add Style", "Enter style name:")
        if ok and style_name.strip():
            dialog = StyleEditDialog(style_name, {}, self)
            if dialog.exec_() == QDialog.Accepted:
                properties = dialog.get_style_properties()
                properties["name"] = style_name.strip()
                self.add_ungrouped_style(properties)

    def edit_selected_style(self):
        current_item = self.style_list.currentItem()
        if current_item:
            style_name = current_item.text()
            data = self.load_styles_from_file()
            for idx, style in enumerate(data["ungrouped"]):
                if style.get("name", "") == style_name:
                    dialog = StyleEditDialog(style_name, style, self)
                    if dialog.exec_() == QDialog.Accepted:
                        new_properties = dialog.get_style_properties()
                        new_properties["name"] = style_name
                        self.update_ungrouped_style(idx, new_properties)
                    break

    def delete_selected_style(self):
        current_item = self.style_list.currentItem()
        if current_item:
            style_name = current_item.text()
            data = self.load_styles_from_file()
            for idx, style in enumerate(data["ungrouped"]):
                if style.get("name", "") == style_name:
                    reply = QMessageBox.question(self, "Delete Style", f"Are you sure you want to delete '{style_name}'?", QMessageBox.Yes | QMessageBox.No)
                    if reply == QMessageBox.Yes:
                        self.delete_ungrouped_style(idx)
                    break

    def add_ungrouped_style(self, style):
        from utils.fontformat import dict_to_fontformat, fontformat_to_dict
        style = fontformat_to_dict(dict_to_fontformat(style))
        data = self.load_styles_from_file()
        data["ungrouped"].append(style)
        self.save_styles_data(data)
        self.update_styles_list()

    def update_ungrouped_style(self, index, new_style):
        from utils.fontformat import dict_to_fontformat, fontformat_to_dict
        new_style = fontformat_to_dict(dict_to_fontformat(new_style))
        data = self.load_styles_from_file()
        data["ungrouped"][index] = new_style
        self.save_styles_data(data)
        self.update_styles_list()

    def delete_ungrouped_style(self, index):
        data = self.load_styles_from_file()
        del data["ungrouped"][index]
        self.save_styles_data(data)
        self.update_styles_list()

    def save_styles_data(self, data):
        from utils.fontformat import dict_to_fontformat, fontformat_to_dict
        # تأكد أن كل ستايل في ungrouped والجروبات تم تحويله
        data["ungrouped"] = [fontformat_to_dict(dict_to_fontformat(s)) for s in data.get("ungrouped", [])]
        for group in data.get("groups", []):
            group["styles"] = [fontformat_to_dict(dict_to_fontformat(s)) for s in group.get("styles", [])]
        import json
        with open(STYLES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


class FontFormatPanel(Widget):
    
    textblk_item: TextBlkItem = None
    text_cursor: QTextCursor = None
    global_format: FontFormat = None
    restoring_textblk: bool = False

    def __init__(self, app: QApplication, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.app = app

        self.vlayout = QVBoxLayout(self)
        self.vlayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.familybox = FontFamilyComboBox(emit_if_focused=True, parent=self)
        self.familybox.setContentsMargins(0, 0, 0, 0)
        self.familybox.setObjectName("FontFamilyBox")
        self.familybox.setToolTip(self.tr("Font Family"))
        self.familybox.param_changed.connect(self.on_param_changed)
        self.familybox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.fontsizebox = FontSizeBox(self)
        self.fontsizebox.setToolTip(self.tr("Font Size"))
        self.fontsizebox.setObjectName("FontSizeBox")
        self.fontsizebox.fcombobox.setToolTip(self.tr("Change font size"))
        self.fontsizebox.param_changed.connect(self.on_param_changed)
        
        self.lineSpacingLabel = SizeControlLabel(self, direction=1)
        self.lineSpacingLabel.setObjectName("lineSpacingLabel")
        self.lineSpacingLabel.size_ctrl_changed.connect(self.onLineSpacingCtrlChanged)
        self.lineSpacingLabel.btn_released.connect(lambda : self.on_param_changed('line_spacing', self.lineSpacingBox.value()))

        self.lineSpacingBox = SizeComboBox([0, 10], 'line_spacing', self)
        self.lineSpacingBox.addItems(["1.0", "1.1", "1.2"])
        self.lineSpacingBox.setToolTip(self.tr("Change line spacing"))
        self.lineSpacingBox.param_changed.connect(self.on_param_changed)
        self.lineSpacingBox.editTextChanged.connect(self.onLineSpacingEditorChanged)
        
        self.colorPicker = ColorPicker(self)
        self.colorPicker.setObjectName("FontColorPicker")
        self.colorPicker.setToolTip(self.tr("Change font color"))
        self.colorPicker.changingColor.connect(self.changingColor)
        self.colorPicker.colorChanged.connect(self.onColorChanged)

        self.alignBtnGroup = AlignmentBtnGroup(self)
        self.alignBtnGroup.param_changed.connect(self.on_param_changed)

        self.formatBtnGroup = FormatGroupBtn(self)
        self.formatBtnGroup.param_changed.connect(self.on_param_changed)

        self.verticalChecker = QFontChecker(self)
        self.verticalChecker.setObjectName("FontVerticalChecker")
        self.verticalChecker.clicked.connect(lambda : self.on_param_changed('vertical', self.verticalChecker.isChecked()))

        self.fontStrokeLabel = SizeControlLabel(self, 0, self.tr("Stroke"))
        self.fontStrokeLabel.setObjectName("fontStrokeLabel")
        font = self.fontStrokeLabel.font()
        font.setPointSizeF(shared.CONFIG_FONTSIZE_CONTENT * 0.95)
        self.fontStrokeLabel.setFont(font)
        self.fontStrokeLabel.size_ctrl_changed.connect(self.onStrokeCtrlChanged)
        self.fontStrokeLabel.btn_released.connect(lambda : self.on_param_changed('stroke_width', self.strokeWidthBox.value()))
        
        self.strokeColorPicker = ColorPicker(self)
        self.strokeColorPicker.setToolTip(self.tr("Change stroke color"))
        self.strokeColorPicker.changingColor.connect(self.changingColor)
        self.strokeColorPicker.colorChanged.connect(self.onStrokeColorChanged)
        self.strokeColorPicker.setObjectName("StrokeColorPicker")

        self.strokeWidthBox = SizeComboBox([0, 10], 'stroke_width', self)
        self.strokeWidthBox.addItems(["0.1"])
        self.strokeWidthBox.setToolTip(self.tr("Change stroke width"))
        self.strokeWidthBox.param_changed.connect(self.on_param_changed)

        stroke_hlayout = QHBoxLayout()
        stroke_hlayout.addWidget(self.fontStrokeLabel)
        stroke_hlayout.addWidget(self.strokeWidthBox)
        stroke_hlayout.addWidget(self.strokeColorPicker)
        stroke_hlayout.setSpacing(shared.WIDGET_SPACING_CLOSE)

        self.letterSpacingLabel = SizeControlLabel(self, direction=0)
        self.letterSpacingLabel.setObjectName("letterSpacingLabel")
        self.letterSpacingLabel.size_ctrl_changed.connect(self.onLetterSpacingCtrlChanged)
        self.letterSpacingLabel.btn_released.connect(lambda : self.on_param_changed('letter_spacing', self.letterSpacingBox.value()))

        self.letterSpacingBox = SizeComboBox([0, 10], "letter_spacing", self)
        self.letterSpacingBox.addItems(["0.0"])
        self.letterSpacingBox.setToolTip(self.tr("Change letter spacing"))
        self.letterSpacingBox.setMinimumWidth(int(self.letterSpacingBox.height() * 2.5))
        self.letterSpacingBox.param_changed.connect(self.on_param_changed)

        lettersp_hlayout = QHBoxLayout()
        lettersp_hlayout.addWidget(self.letterSpacingLabel)
        lettersp_hlayout.addWidget(self.letterSpacingBox)
        lettersp_hlayout.setSpacing(shared.WIDGET_SPACING_CLOSE)
        
        self.global_fontfmt_str = self.tr("Global Font Format")
        self.textstyle_panel = TextStylePanel(self.global_fontfmt_str, parent=self, expanded=pcfg.expand_tstyle_panel)
        self.textstyle_panel.style_area.active_text_style_label_changed.connect(self.on_active_textstyle_label_changed)
        self.textstyle_panel.style_area.active_stylename_edited.connect(self.on_active_stylename_edited)

        self.effectBtn = ClickableLabel(self.tr("Effect"), self)
        self.effectBtn.clicked.connect(self.on_effectbtn_clicked)
        self.effect_panel = TextEffectPanel()
        self.effect_panel.hide()

        self.foldTextBtn = CheckableLabel(self.tr("Unfold"), self.tr("Fold"), False)
        self.sourceBtn = TextChecker(self.tr("Source"))
        self.transBtn = TextChecker(self.tr("Translation"))

        self.style_list_panel = StyleListPanel(self)
        self.collapsible_stylelist = CollapsiblePanel("Style List", self.style_list_panel, self)
        self.vlayout.insertWidget(0, self.collapsible_stylelist)

        FONTFORMAT_SPACING = 6

        vl0 = QVBoxLayout()
        vl0.addWidget(self.textstyle_panel)
        vl0.setSpacing(0)
        vl0.setContentsMargins(0, 0, 0, 0)
        hl1 = QHBoxLayout()
        hl1.addWidget(self.familybox)
        hl1.addWidget(self.fontsizebox)
        hl1.addWidget(self.lineSpacingLabel)
        hl1.addWidget(self.lineSpacingBox)
        hl1.setSpacing(4)
        hl1.setContentsMargins(0, 12, 0, 0)
        hl2 = QHBoxLayout()
        hl2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hl2.addWidget(self.colorPicker)
        hl2.addWidget(self.alignBtnGroup)
        hl2.addWidget(self.formatBtnGroup)
        hl2.addWidget(self.verticalChecker)
        hl2.setSpacing(FONTFORMAT_SPACING)
        hl2.setContentsMargins(0, 0, 0, 0)
        hl3 = QHBoxLayout()
        hl3.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hl3.addLayout(stroke_hlayout)
        hl3.addLayout(lettersp_hlayout)
        hl3.addWidget(self.effectBtn)
        hl3.setContentsMargins(3, 0, 3, 0)
        hl3.setSpacing(13)
        hl4 = QHBoxLayout()
        hl4.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hl4.addWidget(self.foldTextBtn)
        hl4.addWidget(self.sourceBtn)
        hl4.addWidget(self.transBtn)
        hl4.setContentsMargins(0, 12, 0, 0)
        hl4.setSpacing(8)
        self.vlayout.addLayout(vl0)
        self.vlayout.addLayout(hl1)
        self.vlayout.addLayout(hl2)
        self.vlayout.addLayout(hl3)
        self.vlayout.addLayout(hl4)
        self.vlayout.setContentsMargins(7, 0, 7, 0)
        self.vlayout.setSpacing(0)

        self.focusOnColorDialog = False
        C.active_format = self.global_format

    def global_mode(self):
        return id(C.active_format) == id(self.global_format)
    
    def active_text_style_label(self):
        return self.textstyle_panel.style_area.active_text_style_label

    def on_param_changed(self, param_name: str, value):
        func = FM.handle_ffmt_change.get(param_name)
        if self.global_mode():
            func(param_name, value, self.global_format, is_global=True)
            active_text_style_label = self.active_text_style_label()
            if active_text_style_label is not None:
                active_text_style_label.update_style(self.global_format)
        else:
            func(param_name, value, C.active_format, is_global=False, blkitems=self.textblk_item, set_focus=True)

    def changingColor(self):
        self.focusOnColorDialog = True

    def onColorChanged(self, is_valid=True):
        self.focusOnColorDialog = False
        if is_valid:
            frgb = self.colorPicker.rgb()
            self.on_param_changed('frgb', frgb)

    def onStrokeColorChanged(self, is_valid=True):
        self.focusOnColorDialog = False
        if is_valid:
            srgb = self.strokeColorPicker.rgb()
            self.on_param_changed('srgb', srgb)

    def onLineSpacingEditorChanged(self):
        if self.lineSpacingBox.hasFocus() and C.active_format == self.global_format:
            self.global_format.line_spacing = self.lineSpacingBox.value()

    def onStrokeCtrlChanged(self, delta: int):
        self.strokeWidthBox.setValue(self.strokeWidthBox.value() + delta * 0.01)

    def onLetterSpacingCtrlChanged(self, delta: int):
        self.letterSpacingBox.setValue(self.letterSpacingBox.value() + delta * 0.01)

    def onLineSpacingCtrlChanged(self, delta: int):
        self.lineSpacingBox.setValue(self.lineSpacingBox.value() + delta * 0.01)
            
    def set_active_format(self, font_format: FontFormat):
        C.active_format = font_format
        self.fontsizebox.fcombobox.setCurrentText(str(int(font_format.size)))
        self.familybox.setCurrentText(font_format.family)
        self.colorPicker.setPickerColor(font_format.frgb)
        self.strokeColorPicker.setPickerColor(font_format.srgb)
        self.strokeWidthBox.setValue(font_format.stroke_width)
        self.lineSpacingBox.setValue(font_format.line_spacing)
        self.letterSpacingBox.setValue(font_format.letter_spacing)
        self.verticalChecker.setChecked(font_format.vertical)
        self.formatBtnGroup.boldBtn.setChecked(font_format.bold)
        self.formatBtnGroup.underlineBtn.setChecked(font_format.underline)
        self.formatBtnGroup.italicBtn.setChecked(font_format.italic)
        self.alignBtnGroup.setAlignment(font_format.alignment)

    def set_globalfmt_title(self):
        active_text_style_label = self.active_text_style_label()
        if active_text_style_label is None:
            self.textstyle_panel.setTitle(self.global_fontfmt_str)
        else:
            title = self.global_fontfmt_str + ' - ' + active_text_style_label.fontfmt._style_name
            valid_title = self.textstyle_panel.elidedText(title)
            self.textstyle_panel.setTitle(valid_title)

    def on_active_textstyle_label_changed(self):
        active_text_style_label = self.active_text_style_label()
        if active_text_style_label is not None:
            updated_keys = self.global_format.merge(active_text_style_label.fontfmt)
            if self.global_mode() and len(updated_keys) > 0:
                self.set_active_format(self.global_format)
            self.set_globalfmt_title()
        else:
            if self.global_mode():
                self.set_globalfmt_title()

    def on_active_stylename_edited(self):
        if self.global_mode():
            self.set_globalfmt_title()

    def set_textblk_item(self, textblk_item: TextBlkItem = None):
        if textblk_item is None:
            focus_w = self.app.focusWidget()
            focus_p = None if focus_w is None else focus_w.parentWidget()
            focus_on_fmtoptions = False
            if self.focusOnColorDialog:
                focus_on_fmtoptions = True
            elif focus_p:
                if focus_p == self or focus_p.parentWidget() == self:
                    focus_on_fmtoptions = True
            if not focus_on_fmtoptions:
                self.textblk_item = None
                self.set_active_format(self.global_format)
                self.set_globalfmt_title()
        else:
            if not self.restoring_textblk:
                blk_fmt = textblk_item.get_fontformat()
                self.textblk_item = textblk_item
                self.set_active_format(blk_fmt)
                self.textstyle_panel.setTitle(f'TextBlock #{textblk_item.idx}')

    def on_effectbtn_clicked(self):
        self.effect_panel.active_fontfmt = C.active_format
        self.effect_panel.fontfmt = copy.deepcopy(C.active_format)
        self.effect_panel.updatePanels()
        self.effect_panel.show()
        