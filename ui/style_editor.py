import sys
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QLabel, QLineEdit, QColorDialog,
    QFontDialog, QSpinBox, QDialog, QMessageBox, QFormLayout, QDialogButtonBox
)
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtCore import Qt
from modules.style_manager import StyleManager

class StyleEditor(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Typer Tool - Style List System')
        self.resize(700, 400)
        self.manager = StyleManager()
        self.selected_index = None
        self.init_ui()
        self.load_styles()

    def init_ui(self):
        layout = QHBoxLayout(self)

        # Style List
        self.style_list = QListWidget()
        self.style_list.currentRowChanged.connect(self.on_style_selected)
        layout.addWidget(self.style_list, 2)

        # Right panel
        right_panel = QVBoxLayout()

        # Preview
        self.preview_label = QLabel('Preview Text')
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setFixedHeight(80)
        right_panel.addWidget(self.preview_label)

        # Buttons
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton('Add Style')
        self.edit_btn = QPushButton('Edit Style')
        self.delete_btn = QPushButton('Delete Style')
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.delete_btn)
        right_panel.addLayout(btn_layout)

        self.add_btn.clicked.connect(self.add_style)
        self.edit_btn.clicked.connect(self.edit_style)
        self.delete_btn.clicked.connect(self.delete_style)

        layout.addLayout(right_panel, 3)

    def load_styles(self):
        self.style_list.clear()
        for style in self.manager.get_styles():
            self.style_list.addItem(style['name'])
        self.preview_label.setText('Preview Text')
        self.preview_label.setStyleSheet('')

    def on_style_selected(self, index):
        self.selected_index = index
        styles = self.manager.get_styles()
        if 0 <= index < len(styles):
            self.apply_preview(styles[index])
        else:
            self.preview_label.setText('Preview Text')
            self.preview_label.setStyleSheet('')

    def apply_preview(self, style):
        font = QFont(style['font_family'], style['font_size'])
        self.preview_label.setFont(font)
        color = QColor(style['color'])
        self.preview_label.setStyleSheet(f'color: {color.name()};')
        self.preview_label.setText(style.get('preview_text', 'Preview Text'))

    def add_style(self):
        dialog = StyleDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            style = dialog.get_style()
            self.manager.add_ungrouped_style(style)
            self.load_styles()

    def edit_style(self):
        index = self.selected_index
        if index is None or index < 0 or index >= len(self.manager.get_styles()):
            QMessageBox.warning(self, 'No Selection', 'Please select a style to edit.')
            return
        style = self.manager.get_styles()[index]
        dialog = StyleDialog(self, style)
        if dialog.exec_() == QDialog.Accepted:
            new_style = dialog.get_style()
            self.manager.update_ungrouped_style(index, new_style)
            self.load_styles()

    def delete_style(self):
        index = self.selected_index
        if index is None or index < 0 or index >= len(self.manager.get_styles()):
            QMessageBox.warning(self, 'No Selection', 'Please select a style to delete.')
            return
        reply = QMessageBox.question(self, 'Delete Style', 'Are you sure you want to delete this style?', QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.manager.delete_ungrouped_style(index)
            self.load_styles()

class StyleDialog(QDialog):
    def __init__(self, parent=None, style=None):
        super().__init__(parent)
        self.setWindowTitle('Style Editor')
        self.style = style or {}
        self.init_ui()
        if style:
            self.load_style(style)

    def init_ui(self):
        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.font_btn = QPushButton('Choose Font')
        self.font_label = QLabel('')
        self.size_spin = QSpinBox()
        self.size_spin.setRange(6, 100)
        self.color_btn = QPushButton('Choose Color')
        self.color_label = QLabel('')
        self.preview_text_edit = QLineEdit('Preview Text')

        layout.addRow('Name:', self.name_edit)
        layout.addRow('Font:', self.font_btn)
        layout.addRow('', self.font_label)
        layout.addRow('Size:', self.size_spin)
        layout.addRow('Color:', self.color_btn)
        layout.addRow('', self.color_label)
        layout.addRow('Preview Text:', self.preview_text_edit)

        self.font_btn.clicked.connect(self.choose_font)
        self.color_btn.clicked.connect(self.choose_color)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addRow(self.button_box)

        self.selected_font = QFont('Arial', 24)
        self.selected_color = QColor('#000000')
        self.update_font_label()
        self.update_color_label()

    def choose_font(self):
        font, ok = QFontDialog.getFont(self.selected_font, self, 'Select Font')
        if ok:
            self.selected_font = font
            self.size_spin.setValue(font.pointSize())
            self.update_font_label()

    def choose_color(self):
        color = QColorDialog.getColor(self.selected_color, self, 'Select Color')
        if color.isValid():
            self.selected_color = color
            self.update_color_label()

    def update_font_label(self):
        self.font_label.setText(f'{self.selected_font.family()}, {self.selected_font.pointSize()}pt')

    def update_color_label(self):
        self.color_label.setText(self.selected_color.name())
        self.color_label.setStyleSheet(f'background: {self.selected_color.name()};')

    def load_style(self, style):
        self.name_edit.setText(style.get('name', ''))
        self.selected_font = QFont(style.get('font_family', 'Arial'), style.get('font_size', 24))
        self.size_spin.setValue(style.get('font_size', 24))
        self.selected_color = QColor(style.get('color', '#000000'))
        self.preview_text_edit.setText(style.get('preview_text', 'Preview Text'))
        self.update_font_label()
        self.update_color_label()

    def get_style(self):
        return {
            'name': self.name_edit.text(),
            'font_family': self.selected_font.family(),
            'font_size': self.size_spin.value(),
            'color': self.selected_color.name(),
            'preview_text': self.preview_text_edit.text(),
            # Outline, shadow, spacing, etc. can be added here later
        }

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = StyleEditor()
    window.show()
    sys.exit(app.exec_()) 