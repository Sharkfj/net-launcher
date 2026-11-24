"""Bounded file transfers and image compression for friends chat."""
from __future__ import annotations

import base64
import os
import tempfile
import uuid
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QSize, Qt
from PySide6.QtGui import QImage, QImageReader

from netlauncher.i18n import t

CHUNK = 1536 * 1024
MAX_FILE = 20 * 1024 * 1024


def image_attachment(image: QImage, name: str):
    if image.isNull():
        raise ValueError(t("Не удалось открыть изображение."))
    if max(image.width(), image.height()) > 2048:
        image = image.scaled(2048, 2048, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    output = QBuffer()
    output.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(output, "JPG", 85):
        raise ValueError(t("Не удалось открыть изображение."))
    return Path(name).stem[:150] + ".jpg", bytes(output.data()), "image"


def attachment(path):
    path = Path(path)
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    if reader.canRead():
        size = reader.size()
        if size.isValid() and max(size.width(), size.height()) > 2048:
            reader.setScaledSize(size.scaled(QSize(2048,2048), Qt.AspectRatioMode.KeepAspectRatio))
        return image_attachment(reader.read(), path.name)
    if not 0 < path.stat().st_size <= MAX_FILE:
        raise ValueError(t("Выбери файл размером до 20 МБ."))
    with path.open("rb") as stream:
        data = stream.read(MAX_FILE+1)
    return path.name, data, "file"


def send_file(client, room, prepared):
    name, data, kind = prepared
    if not 0 < len(data) <= MAX_FILE:
        raise ValueError(t("Выбери файл размером до 20 МБ."))
    file = uuid.uuid4().hex
    client.chat("upload", room=room, file=file, name=name, size=len(data))
    for offset in range(0,len(data),CHUNK):
        client.chat("chunk", room=room, file=file, part=offset//CHUNK,
                    data=base64.b64encode(data[offset:offset+CHUNK]).decode())
    return client.chat("post", room=room, nonce=file, kind=kind, file=file, text=name)


def receive_file(client, room, msg, dest):
    size = msg["size"]
    if type(size) is not int or not 0 < size <= MAX_FILE:
        raise ValueError(t("Срок хранения файла истёк."))
    dest = Path(dest)
    fd, temp = tempfile.mkstemp(dir=dest.parent)
    try:
        with os.fdopen(fd,"wb") as stream:
            for offset in range(0,size,CHUNK):
                piece = client.chat("download",room=room,file=msg["file"],part=offset//CHUNK)
                data = base64.b64decode(piece["data"],validate=True)
                if len(data) != min(CHUNK,size-offset):
                    raise ValueError(t("Файл скачан не полностью."))
                stream.write(data)
        os.replace(temp,dest)
    finally:
        Path(temp).unlink(missing_ok=True)
    return dest
