"""Position named controls relative to the slots assigned by their Qt layouts."""
from shiboken6 import isValid
from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QBoxLayout, QGridLayout, QScrollArea, QStackedWidget, QWidget, QWidgetItem


def slot_for(layout, widget):
    if layout is None:
        return None
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is widget:
            if isinstance(layout, (QBoxLayout, QGridLayout)):
                return layout, index
        elif item.layout():
            slot = slot_for(item.layout(), widget)
            if slot:
                return slot
    return None


class OffsetItem(QWidgetItem):
    def __init__(self, widget, alignment):
        super().__init__(widget)
        self.setAlignment(alignment)
        self.offset = QPoint()
        self.slot_rect = None
        self.base = widget.pos()

    def setGeometry(self, rect):
        self.slot_rect = QRect(rect)
        super().setGeometry(rect)
        widget = self.widget()
        self.base = widget.pos()
        if self.offset.isNull() or widget.isHidden():
            return
        parent = widget.parentWidget()
        pos = self.base + self.offset
        widget.move(max(0, min(pos.x(), parent.width() - widget.width())),
                    max(0, min(pos.y(), parent.height() - widget.height())))


class Placements:
    def __init__(self, window):
        self.controls = {}
        self.items = {}
        self.rail = window.rail

        def collect(owner, prefix):
            for name, widget in vars(owner).items():
                if not isinstance(widget, QWidget) or widget is window or not owner.isAncestorOf(widget):
                    continue
                if isinstance(widget, (QStackedWidget, QScrollArea)):
                    continue
                parent = widget.parentWidget()
                if slot_for(parent.layout(), widget):
                    self.controls[f"{prefix}.{name}"] = widget
        for tag, page in window._pages.items():
            collect(page, tag)
            for name, child in vars(page).items():
                if isinstance(child, QWidget) and page.isAncestorOf(child) and type(child).__module__.startswith("netlauncher"):
                    collect(child, f"{tag}.{name}")
        collect(window.rail, "rail")
        self.controls.update({f"rail.buttons.{key}": button for key, button in window.rail.buttons.items()})
        named = {widget: key for key, widget in self.controls.items()}

        def walk(layout, prefix):
            if not isinstance(layout, (QBoxLayout, QGridLayout)):
                return
            for index in range(layout.count()):
                item = layout.itemAt(index)
                key = f"{prefix}.slot{index}"
                widget = item.widget()
                if item.layout():
                    walk(item.layout(), key)
                elif isinstance(widget, QScrollArea):
                    if widget.widget():
                        walk(widget.widget().layout(), key)
                elif isinstance(widget, QStackedWidget):
                    for i in range(widget.count()):
                        page = widget.widget(i)
                        walk(page.layout(), f"{key}.{type(page).__name__}")
                elif widget is not None:
                    # Rows populated from player data are rebuilt while the window is open.
                    if type(widget).__name__ in {"PackRow", "OfficialCard", "FriendRow", "RequestRow", "InviteRow"}:
                        continue
                    key = named.get(widget, key)
                    self.controls.setdefault(key, widget)
                    walk(widget.layout(), key)

        for tag, page in window._pages.items():
            walk(page.layout(), tag)

    def apply(self, positions):
        for key in sorted(self.items.keys() | positions.keys()):
            widget = self.controls.get(key)
            if widget is None or not isValid(widget):
                continue
            item = self.items.get(key)
            if item is None:
                parent = widget.parentWidget()
                slot = slot_for(parent.layout(), widget) if parent else None
                if not slot:
                    continue
                layout, index = slot
                if isinstance(layout, QGridLayout):
                    grid = layout.getItemPosition(index)
                else:
                    stretch = layout.stretch(index)
                old = layout.takeAt(index)
                item = OffsetItem(widget, old.alignment())
                self.items[key] = item
                if isinstance(layout, QGridLayout):
                    layout.addItem(item, *grid, old.alignment())
                else:
                    layout.insertItem(index, item)
                    layout.setStretch(index, stretch)
                widget.parentWidget().layout().activate()
            offset = QPoint(*positions.get(key, (0, 0)))
            if item.offset != offset:
                item.offset = offset
                if item.slot_rect is not None:
                    item.setGeometry(item.slot_rect)
                if not offset.isNull():
                    widget.raise_()
                if key.startswith("rail.") and self.rail.active:
                    self.rail.set_active(self.rail.active, animate=False)
