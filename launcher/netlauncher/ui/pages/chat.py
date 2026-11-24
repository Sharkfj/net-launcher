"""Direct and group chat, opened from Friends or from a pack screenshot."""
from __future__ import annotations

import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

import shiboken6
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox,
                               QFileDialog, QLabel, QLineEdit, QListWidget, QMenu,
                               QFrame, QScrollArea, QToolButton, QWidget)

from netlauncher import chat_files, chat_packs, localpacks
from netlauncher.i18n import t
from netlauncher.net import HttpError
from netlauncher.ui import anim, jobs
from netlauncher.ui.chat_stream import ChatStream, tray_count
from netlauncher.ui.pages.common import hbox, human_date, human_size, label, vbox
from netlauncher.ui.supporter import display_name
from netlauncher.ui.widgets import AccentButton, CompactCombo, GhostButton, GlassCard


def title(room):
    return room["peer"] if room["direct"] else room["title"]


def plain(text, size=10.5, weight=400, role=None):
    widget = label(text,size,weight,role=role,wrap=True)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return widget


def pack_summary(card):
    version = card.get("version") or "—"
    loader = " ".join(part for part in (card.get("loader"), card.get("loader_version")) if part)
    details = f'Minecraft {card.get("mc", "—")} · {loader or "Vanilla"} · v{version}'
    if "files" in card:
        count = len(card["files"])
        mods = sum(f["path"].startswith("mods/") for f in card["files"])
        sizes = [f.get("size") for f in card["files"]]
        size = human_size(sum(sizes)) if all(type(value) is int for value in sizes) else t("размер неизвестен")
        details += "\n" + t("Модов: {mods} · Файлов: {count} · {size}", mods=mods, count=count, size=size)
    return details


def error_text(error):
    if isinstance(error,HttpError):
        if error.status==429:
            return t("Лимит на сегодня исчерпан. Можно отправлять до 200 МБ в день.")
        if error.status==413:
            return t("Файл или карточка сборки слишком велики.")
        if error.status==410:
            return t("Срок хранения файла истёк.")
        if error.status==403:
            return t("У тебя нет доступа к этому действию.")
    return t("Не удалось выполнить действие: {error}",error=str(error))


class Compose(QLineEdit):
    pasted = Signal(object)
    def keyPressEvent(self, event):
        mime = QGuiApplication.clipboard().mimeData()
        if event.matches(QKeySequence.StandardKey.Paste) and mime and mime.hasImage():
            self.pasted.emit(QGuiApplication.clipboard().image())
            return
        super().keyPressEvent(event)


def chat_sheet(parent, caption):
    dialog = QDialog(parent, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
    dialog.setWindowTitle(caption)
    dialog.finished.connect(dialog.deleteLater)
    dialog.setMinimumWidth(330)
    dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    panel = QWidget()
    panel.setObjectName("chatSheet")
    vbox(dialog).addWidget(panel)
    layout = vbox(panel, (18, 14, 18, 18), 10)
    header = hbox()
    header.addWidget(plain(caption, 15, 650), 1)
    close = GhostButton(t("Закрыть"))
    close.clicked.connect(dialog.reject)
    header.addWidget(close)
    layout.addLayout(header)
    return dialog, layout


class Chats:
    def __init__(self, page):
        self.page = page
        self.ctx, self.window = page.ctx,page.window
        self.client = self.inbox = self.dialog = None
        self.rooms = []
        self.names = []
        self.me = ""
        self.serial = 0
        self.requested_room = None
        self.last_notification = None
        self.tray_hooked = False

    def reset(self):
        self.serial += 1
        self.requested_room = None
        if self.inbox:
            self.inbox.stop()
        if self.dialog:
            self.leave()
            self.page.views.removeWidget(self.dialog)
            self.dialog.deleteLater()
        self.client = self.inbox = self.dialog = self.last_notification = None
        self.me, self.rooms, self.names = "", [], []
        tray_count(self.window,0)

    def start(self,client,me,names):
        self.client, self.me, self.names = client, me, names
        if not self.inbox:
            self.refresh(connect=True)

    def _wait_for_client(self, action):
        client = self.page.client()
        if self.client is client:
            return False
        if self.window:
            self.window.open_page("friends")
        if self.page._update_notice():
            self.page._run(lambda c: c.state(), on_done=action)
        return True

    def run(self, fn, done=None, fail=None):
        client = self.client
        if client is None:
            return
        def current():
            if not shiboken6.isValid(self.page) or self.client is not client:
                return False
            acc = self.ctx.accounts.load()
            return bool(acc and not getattr(acc,"offline",False) and acc.uuid==client.identity and
                        self.ctx.friends_url().rstrip("/")==client.base)
        def completed(value):
            if current() and done:
                done(value)
        def failed(error):
            if current():
                (fail or self.error)(error)
        jobs.run(lambda progress:fn(client),on_done=completed,on_error=failed)

    def error(self, error):
        dest = self.dialog.status if self.dialog and self.dialog.isVisible() else self.page.notice
        dest.setText(error_text(error))

    def refresh(self, connect=False, select=None):
        self.serial += 1
        seq = self.serial
        if select:
            self.requested_room = select
        def done(result):
            if seq != self.serial:
                return
            self.rooms = result["rooms"]
            count = sum(r["unread"] for r in self.rooms)
            tray_count(self.window,count)
            self.page.chat_btn.setText(t("Чаты ({n})",n=count) if count else t("Чаты"))
            if self.dialog:
                self.dialog.set_rooms(self.rooms, self.requested_room)
            self.requested_room = None
            if not self.inbox:
                self.inbox = ChatStream(self.client,parent=self.page)
                self.inbox.event.connect(self.event)
                self.inbox.connected.connect(self.refresh)
                self.inbox.open()
            tray = getattr(self.window,"tray",None)
            if tray and not self.tray_hooked:
                tray.messageClicked.connect(self.follow_notification)
                self.tray_hooked = True
        self.run(lambda c:c.chat("list"),done, (lambda e:None) if connect else None)

    def follow_notification(self):
        if self.last_notification and self.window:
            self.window.restore_from_tray()
            self.open(self.last_notification)

    def event(self,event):
        room = event.get("room")
        if not room:
            return
        if event.get("event")=="message" and event.get("sender")!=self.me:
            if self.window and (self.window.isMinimized() or not self.window.isVisible()):
                tray = getattr(self.window,"tray",None)
                if tray:
                    self.last_notification = room
                    tray.showMessage(event["sender"],str(event.get("text",""))[:200])
        self.refresh()
        if self.dialog and self.dialog.active==room and event.get("removed","").lower()==self.me.lower():
            self.dialog.select(None)

    def open(self,select=None):
        if self._wait_for_client(lambda: self.open(select)):
            return
        if not self.dialog:
            self.dialog = ChatPage(self)
            self.page.views.addWidget(self.dialog)
        if self.window and not self.page.isVisible():
            self.window.open_page("friends")
        if self.page.views.currentWidget() is not self.dialog:
            self.page.views.setCurrentWidget(self.dialog)
            anim.fade_slide_in(self.dialog, dx=0, dy=8, ms=220)
        self.refresh(select=select)
        return self.dialog

    def leave(self):
        self.dialog.select(None)
        self.page.views.setCurrentIndex(0)
        self.page.chat_btn.setFocus()

    def direct(self,name):
        self.run(lambda c:c.chat("create",names=[name],title=""),lambda r:self.open(r["id"]))

    def group(self,parent):
        dialog, layout = chat_sheet(parent, t("Новая группа"))
        name = QLineEdit()
        name.setPlaceholderText(t("Название группы"))
        name.setMaxLength(80)
        layout.addWidget(name)
        friends = QListWidget()
        friends.addItems(self.names)
        friends.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        friends.setAccessibleName(t("Друзья"))
        layout.addWidget(friends)
        btn = AccentButton(t("Создать группу"))
        btn.setEnabled(False)
        update = lambda:btn.setEnabled(bool(name.text().strip() and 1 <= len(friends.selectedItems()) <= 19))
        name.textChanged.connect(update)
        friends.itemSelectionChanged.connect(update)
        layout.addWidget(btn)
        btn.clicked.connect(dialog.accept)
        if dialog.exec():
            names = [n.text() for n in friends.selectedItems()]
            group_name = name.text().strip()
            nonce = uuid.uuid4().hex
            self.run(lambda c:c.chat("create",names=names,title=group_name,nonce=nonce),lambda r:self.open(r["id"]))

    def share_screenshot(self,path):
        if self._wait_for_client(lambda: self.share_screenshot(path)):
            return
        def choose(result):
            options = [(title(r),r["id"],None) for r in result["rooms"]]
            direct_peers = {r["peer"] for r in result["rooms"] if r["direct"]}
            options += [(n,None,n) for n in self.names if n not in direct_peers]
            if not options:
                self.open()
                return
            dialog, layout = chat_sheet(self.window or self.page, t("Отправить в чат"))
            box = CompactCombo()
            for name,_,_ in options:
                box.addItem(name)
            layout.addWidget(box)
            send = AccentButton(t("Отправить"))
            layout.addWidget(send)
            send.clicked.connect(dialog.accept)
            if dialog.exec():
                _, room, name = options[box.currentIndex()]
                def work(c):
                    dest = room or c.chat("create",names=[name],title="")["id"]
                    chat_files.send_file(c,dest,chat_files.attachment(path))
                    return dest
                self.run(work,self.open)
        self.run(lambda c:c.chat("list"),choose)


class ChatPage(QWidget):
    def __init__(self,chats):
        super().__init__(chats.page)
        self.chats = chats
        self.active = self.stream = None
        self.serial = 0
        self.messages = {}
        self.members = []
        self.loaded_more = False
        self.pending = set()
        outer = vbox(self, (8, 4, 18, 0), 10)
        header = hbox()
        header.addWidget(label(t("Чаты"), 22, 650, display=True), 1)
        self.back = GhostButton(t("К друзьям"))
        self.back.clicked.connect(chats.leave)
        escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escape.activated.connect(chats.leave)
        header.addWidget(self.back)
        outer.addLayout(header)
        top = hbox()
        self.rooms = CompactCombo()
        self.rooms.setAccessibleName(t("Чат"))
        top.addWidget(self.rooms,1)
        group = GhostButton(t("Новая группа"))
        group.clicked.connect(lambda:chats.group(self))
        top.addWidget(group)
        self.manage = GhostButton(t("Участники"))
        self.manage.clicked.connect(self.manage_members)
        top.addWidget(self.manage)
        outer.addLayout(top)
        self.rooms.currentIndexChanged.connect(lambda:self.select(self.rooms.currentData()))
        self.older = GhostButton(t("Предыдущие сообщения"))
        self.older.clicked.connect(lambda:self.history(older=True))
        self.older.hide()
        outer.addWidget(self.older)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        history_panel = GlassCard(radius=14)
        vbox(history_panel, (8, 6, 8, 6)).addWidget(self.scroll)
        outer.addWidget(history_panel, 1)
        self.status = plain("",10,role="muted")
        outer.addWidget(self.status)
        bar = hbox()
        self.attach = GhostButton(t("Вложение"))
        self.attach.clicked.connect(self.choose_attachment)
        bar.addWidget(self.attach)
        self.editor = Compose()
        self.editor.setMaxLength(4000)
        self.editor.setPlaceholderText(t("Сообщение"))
        self.editor.returnPressed.connect(self.send)
        self.editor.pasted.connect(self.paste)
        bar.addWidget(self.editor,1)
        self.send_btn = AccentButton(t("Отправить"))
        self.send_btn.clicked.connect(self.send)
        bar.addWidget(self.send_btn)
        outer.addLayout(bar)
        self.select(None)

    def set_rooms(self,rooms,select=None):
        current = select or self.active
        self.rooms.blockSignals(True)
        self.rooms.clear()
        for rec in rooms:
            caption = title(rec)
            if rec["unread"]:
                caption += " ("+str(rec["unread"])+")"
            self.rooms.addItem(caption,rec["id"])
        n = self.rooms.findData(current)
        self.rooms.setCurrentIndex(n if n>=0 else (0 if rooms else -1))
        self.rooms.blockSignals(False)
        if self.isVisible():
            self.select(self.rooms.currentData())

    def select(self,room):
        if room==self.active and self.stream:
            return
        if self.stream:
            self.stream.stop()
        self.active, self.stream, self.messages, self.members = room,None,{},[]
        self.serial += 1
        self.loaded_more = False
        self.editor.clear()
        self.older.hide()
        self.status.clear()
        self.render()
        rec = next((x for x in self.chats.rooms if x["id"]==room),{})
        self.manage.setVisible(bool(rec and not rec["direct"]))
        for w in (self.attach,self.editor,self.send_btn):
            w.setEnabled(bool(room))
        if room:
            self.editor.setFocus()
            self.stream = ChatStream(self.chats.client,room,self)
            self.stream.event.connect(self.room_event)
            self.stream.connected.connect(self.history)
            self.stream.open()
            self.history()
        else:
            self.status.setText(t("Нажми «Написать» рядом с другом или создай группу."))

    def room_event(self,event):
        if event.get("room") != self.active:
            return
        if event.get("event")=="deleted":
            self.messages.pop(event.get("id"),None)
            self.render()
        self.history()

    def history(self,older=False):
        room = self.active
        if not room:
            return
        self.serial += 1
        seq = self.serial
        before = min(self.messages) if older and self.messages else 0
        def done(result):
            if self.active!=room or seq!=self.serial:
                return
            page = result["messages"]
            previous = self.messages.copy()
            if not older and page:
                # Keep earlier pages, replace the latest page to reflect deletions after reconnecting.
                self.messages = {i:m for i,m in self.messages.items() if i<page[0]["id"] and result["more"]}
            elif not older:
                self.messages.clear()
            self.messages.update({m["id"]:m for m in page})
            self.members = result["members"]
            self.older.setVisible(bool(result["more"]) if older or not self.loaded_more else self.older.isVisible())
            self.loaded_more = self.loaded_more or older
            if previous != self.messages:
                newest = max(previous, default=0)
                arriving = [mid for mid in self.messages if newest and mid > newest]
                self.render(prepend=older, arriving=arriving)
            if self.messages and self.isActiveWindow() and self.isVisible() and not self.window().isMinimized():
                mid = max(self.messages)
                rec = next((r for r in self.chats.rooms if r["id"]==room),{})
                if (rec.get("seen") or 0)<mid:
                    self.chats.run(lambda c:c.chat("read",room=room,id=mid),lambda _:self.chats.refresh())
        self.chats.run(lambda c:c.chat("history",room=room,before=before),done)

    def render(self, prepend=False, arriving=()):
        bar = self.scroll.verticalScrollBar()
        position, maximum = bar.value(), bar.maximum()
        old = self.scroll.takeWidget()
        if old:
            old.deleteLater()
        body = QWidget()
        thread = vbox(body,(6,6,6,6),8)
        thread.addStretch(1)
        animated = []
        for mid,msg in sorted(self.messages.items()):
            own = msg["sender"] == self.chats.me
            bubble = QFrame()
            bubble.setObjectName("outgoingMessage" if own else "incomingMessage")
            bubble.setMaximumWidth(560)
            layout = vbox(bubble, (12, 7, 12, 9), 3)
            line = hbox()
            if own:
                line.addStretch(1)
            line.addWidget(bubble)
            if not own:
                line.addStretch(1)
            thread.addLayout(line)
            if mid in arriving:
                animated.append(bubble)
            row = hbox()
            stamp = human_date(datetime.fromtimestamp(msg["created"]))
            author = QToolButton()
            author.setObjectName("chatAuthor")
            author.setText(display_name(msg["sender"], msg.get("supporter")))
            author.setToolTip(t("Профиль игрока {name}", name=msg["sender"]))
            author.setAccessibleName(author.toolTip())
            author.setCursor(Qt.CursorShape.PointingHandCursor)
            if self.chats.window:
                author.clicked.connect(lambda _, name=msg["sender"]: self.chats.window.open_profile(name))
            row.addWidget(author)
            row.addWidget(plain(stamp,9,role="muted"))
            row.addStretch(1)
            if own:
                btn = QToolButton()
                btn.setText("×")
                btn.setToolTip(t("Удалить сообщение"))
                btn.setAccessibleName(t("Удалить сообщение"))
                btn.clicked.connect(lambda _,m=mid:self.delete(m))
                row.addWidget(btn)
            layout.addLayout(row)
            kind = msg["kind"]
            if kind in ("pack", "official"):
                name, _, info = msg["text"].partition("\n")
                layout.addWidget(plain(name, 12, 650))
                if info:
                    layout.addWidget(plain(info, 9.5, role="muted"))
            else:
                layout.addWidget(plain(msg["text"]))
            if kind in ("image","file"):
                if (msg.get("expires") or 0)<=time.time():
                    layout.addWidget(plain(t("Срок хранения файла истёк."),9,role="muted"))
                else:
                    actions = hbox()
                    if kind=="image":
                        preview = GhostButton(t("Открыть изображение"))
                        preview.clicked.connect(lambda _,m=msg:self.preview(m))
                        actions.addWidget(preview)
                    save = GhostButton(t("Сохранить файл ({size})",size=human_size(msg["size"])))
                    save.clicked.connect(lambda _,m=msg:self.save_file(m))
                    actions.addWidget(save)
                    actions.addStretch(1)
                    layout.addLayout(actions)
            if kind in ("pack","official"):
                btn = GhostButton(t("Открыть сборку") if kind=="official" else t("Установить сборку"))
                btn.clicked.connect(lambda _,m=msg:self.open_card(m))
                layout.addWidget(btn,0,Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(body)
        body.adjustSize()
        if prepend:
            bar.setValue(position + bar.maximum() - maximum)
        else:
            bar.setValue(bar.maximum() if maximum - position <= 3 else position)
        if self.isVisible() and animated:
            anim.fade_slide_in(animated[-1], dx=0, dy=5, ms=160)

    def post(self,fn,clear=None):
        room = self.active
        if not room or room in self.pending:
            return
        self.pending.add(room)
        self.status.setText(t("Отправка…"))
        def done(_):
            self.pending.discard(room)
            if self.active==room:
                if clear is not None and self.editor.text()==clear:
                    self.editor.clear()
                self.status.clear()
                self.history()
        def failed(e):
            self.pending.discard(room)
            self.chats.error(e)
        self.chats.run(lambda c:fn(c,room),done,failed)

    def send(self):
        text = self.editor.text()
        if text.strip():
            nonce = uuid.uuid4().hex
            self.post(lambda c,r:c.chat("post",room=r,kind="text",text=text.strip(),nonce=nonce),text)

    def paste(self,image):
        self.post(lambda c,r:chat_files.send_file(c,r,chat_files.image_attachment(image,"clipboard")))

    def choose_attachment(self):
        menu = QMenu(self)
        menu.addAction(t("Выбрать файл"),self.pick_file)
        menu.addAction(t("Скриншоты игры"),self.pick_shot)
        menu.addAction(t("Поделиться сборкой"),self.pick_pack)
        menu.exec(self.attach.mapToGlobal(self.attach.rect().topLeft()))

    def pick_file(self):
        path,_ = QFileDialog.getOpenFileName(self,t("Выбрать файл"))
        if path:
            self.post(lambda c,r:chat_files.send_file(c,r,chat_files.attachment(path)))

    def pick_shot(self):
        from netlauncher.ui.pages.screenshots import list_shots
        shots = [(p.name,path) for p in localpacks.list_installed(self.chats.ctx.lay)
                 for path in list_shots(localpacks.game_dir(self.chats.ctx.lay,p.id))]
        if not shots:
            self.status.setText(t("Скриншотов пока нет. Нажми F2 в игре, и скриншот появится здесь."))
            return
        path = self.pick(t("Скриншоты игры"),[(name+" / "+p.name,p) for name,p in shots])
        if path:
            self.post(lambda c,r:chat_files.send_file(c,r,chat_files.attachment(path)))

    def pick(self,caption,options):
        dialog, layout = chat_sheet(self, caption)
        box = CompactCombo()
        for name,_ in options:
            box.addItem(name)
        layout.addWidget(box)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        return options[box.currentIndex()][1] if options and dialog.exec() else None

    def pick_pack(self):
        ctx = self.chats.ctx
        options = [(p.name+" · "+p.version,p) for p in localpacks.list_installed(ctx.lay)]
        if not options:
            self.status.setText(t("Сначала создай или установи сборку."))
            return
        pack = self.pick(t("Поделиться сборкой"),options)
        if not pack or not self.active:
            return
        room = self.active
        self.status.setText(t("Готовлю карточку сборки…"))

        def ready(result):
            if self.active != room:
                return
            kind, card = result
            dialog, layout = chat_sheet(self, card["name"])
            layout.addWidget(plain(pack_summary(card), role="muted"))
            send = AccentButton(t("Отправить сборку"))
            send.clicked.connect(dialog.accept)
            layout.addWidget(send, 0, Qt.AlignmentFlag.AlignLeft)
            self.status.clear()
            if dialog.exec() and self.active == room:
                text = card["name"] + "\n" + pack_summary(card)
                self.post(lambda c, r: c.chat("post", room=r, kind=kind, card=card, text=text,
                                              nonce=uuid.uuid4().hex))

        self.chats.run(lambda _: chat_packs.make_card(ctx, pack), ready)

    def manage_members(self):
        rec = next((r for r in self.chats.rooms if r["id"]==self.active),None)
        if not rec:
            return
        room = self.active
        menu = QMenu(self)
        add = menu.addMenu(t("Добавить участника"))
        for name in self.chats.names:
            if name not in self.members:
                add.addAction(name,lambda n=name:self.chats.run(lambda c:c.chat("add",room=room,name=n),lambda _:self.history()))
        add.setEnabled(bool(add.actions()))
        for name in self.members:
            if self.chats.me==rec["owner"] and name!=self.chats.me:
                menu.addAction(t("Убрать {name}",name=name),lambda n=name:self.chats.run(lambda c:c.chat("remove",room=room,name=n),lambda _:self.history()))
            else:
                menu.addAction(name).setEnabled(False)
        menu.exec(self.manage.mapToGlobal(self.manage.rect().bottomLeft()))

    def delete(self,mid):
        room = self.active
        dialog, layout = chat_sheet(self, t("Удалить сообщение"))
        layout.addWidget(plain(t("Удалить сообщение у всех участников?")))
        remove = GhostButton(t("Удалить"), danger=True)
        remove.clicked.connect(dialog.accept)
        layout.addWidget(remove)
        if dialog.exec():
            self.chats.run(lambda c:c.chat("delete",room=room,id=mid),lambda _:self.room_event({"event":"deleted","room":room,"id":mid}))

    def save_file(self,msg):
        room = self.active
        name = Path(msg.get("filename") or "download").name
        path,_ = QFileDialog.getSaveFileName(self,t("Сохранить файл"),name)
        if path:
            self.chats.run(lambda c:chat_files.receive_file(c,room,msg,path),lambda p:self.status.setText(t("Сохранено: {path}",path=p)))

    def preview(self,msg):
        room = self.active
        def work(c):
            with tempfile.TemporaryDirectory() as temp:
                return chat_files.receive_file(c,room,msg,Path(temp)/"image").read_bytes()
        def show(data):
            pix = QPixmap()
            if not pix.loadFromData(data,"JPG"):
                self.status.setText(t("Не удалось открыть изображение."))
                return
            dialog, layout = chat_sheet(self, msg["text"])
            panel = QLabel()
            panel.setPixmap(pix.scaled(860,600,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            layout.addWidget(panel)
            dialog.exec()
        self.chats.run(work,show)

    def open_card(self,msg):
        room = self.active
        self.chats.run(lambda c:c.chat("card",room=room,id=msg["id"]),lambda r:self.review_card(msg["kind"],r["card"]))

    def review_card(self,kind,card):
        ctx = self.chats.ctx
        if kind=="official":
            entry = ctx.catalog.get(card.get("id")) if ctx.catalog else None
            if entry and self.chats.window:
                self.chats.leave()
                self.chats.window.open_page("official")
                page = self.chats.window.page("official")
                target = next((c for c in page.cards if c.entry.id==entry.id),None)
                if target:
                    target.action_btn.setFocus()
                    page.findChild(QScrollArea).ensureWidgetVisible(target)
            else:
                self.status.setText(t("Этой сборки нет в официальном каталоге."))
            return
        try:
            settings = chat_packs.validate(card)
        except ValueError as e:
            self.chats.error(e)
            return
        self.status.setText(t("Проверяю файлы сборки…"))
        room = self.active
        self.chats.run(lambda _: chat_packs.plan_card(ctx, card),
                       lambda sources: self._confirm_pack(card, settings, sources) if self.active == room else None)

    def _confirm_pack(self, card, settings, sources):
        ctx = self.chats.ctx
        self.status.clear()
        dialog, layout = chat_sheet(self, card["name"])
        layout.addWidget(plain(pack_summary(card), role="muted"))
        manual = [chat_packs.manual_file(f) for f in card["files"] if f["path"] not in sources]
        sizes = [entry[2] for entry in sources.values()]
        amount = (human_size(sum(sizes)) if sum(sizes) else "0 MB") if all(type(value) is int for value in sizes) else t("размер неизвестен")
        layout.addWidget(plain(t("Автоматическая загрузка: {count} · {size}", count=len(sources), size=amount)))
        if manual:
            layout.addWidget(plain(t("Скачать вручную: {count}", count=len(manual)), weight=600))
        files = QListWidget()
        files.addItems([t("Вручную · {file}", file=file.path) for file in manual]
                       + [f["path"] for f in card["files"] if f["path"] in sources] + sorted(settings))
        for row, file in enumerate(manual):
            item = files.item(row)
            item.setData(Qt.ItemDataRole.UserRole, file.page_url)
            item.setToolTip(t("Открыть страницу файла"))

        def open_file(item):
            url = item.data(Qt.ItemDataRole.UserRole)
            if url:
                QDesktopServices.openUrl(QUrl(url))

        files.itemActivated.connect(open_file)
        files.setAccessibleName(t("Моды и настройки сборки"))
        layout.addWidget(files)
        install = AccentButton(t("Установить"))
        install.clicked.connect(dialog.accept)
        layout.addWidget(install, 0, Qt.AlignmentFlag.AlignLeft)
        dialog.resize(500, 430)
        room = self.active
        if dialog.exec() and self.active == room:
            self.status.setText(t("Устанавливаю сборку…"))

            def installed(result):
                lp, index, missing = result
                ctx.settings.selected_pack = lp.id
                ctx.save()
                if self.chats.window:
                    self.chats.leave()
                    self.chats.window.open_page("home")
                    home = self.chats.window.page("home")
                    home._installed((index, localpacks.game_dir(ctx.lay, lp.id), missing))

            self.chats.run(lambda _: chat_packs.install_card(ctx, card, lambda *args: None, sources=sources), installed)

    def closeEvent(self,event):
        self.select(None)
        super().closeEvent(event)

    def changeEvent(self,event):
        super().changeEvent(event)
        from PySide6.QtCore import QEvent
        if event.type()==QEvent.Type.ActivationChange and self.isActiveWindow() and getattr(self,"active",None):
            self.history()
