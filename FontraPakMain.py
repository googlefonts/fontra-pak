import asyncio
import functools
from urllib.parse import quote
import webbrowser
import sys

from aiohttp import web
from PyQt6.QtWidgets import QMainWindow, QLabel, QVBoxLayout, QWidget
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QSize, QPoint, QSettings
import qasync
from qasync import asyncClose, QApplication
from fontra.filesystem.projectmanager import FileSystemProjectManager
from fontra.core.server import FontraServer


neutralCSS = """
background-color: white;
border: 5px solid lightgray;
border-radius: 20px;
border-style: dashed
"""

droppingCSS = """
background-color: white;
border: 5px solid gray;
border-radius: 20px;
border-style: dashed
"""


class FontraMainWidget(QMainWindow):
    def __init__(self, closeCallback):
        super().__init__()
        self.closeCallback = closeCallback
        self.setWindowTitle("Fontra Shell — Drag and Drop Font Files")
        self.resize(720, 480)

        self.settings = QSettings("xyz.fontra", "FontraPak")

        self.resize(self.settings.value("size", QSize(720, 480)))
        self.move(self.settings.value("pos", QPoint(50, 50)))

        self.setAcceptDrops(True)

        self.label = QLabel("Drop font files here")
        self.label.setFont(QFont("Helvetica", 40))
        self.label.setGeometry(20, 20, 680, 440)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet(neutralCSS)

        layout = QVBoxLayout()
        layout.addWidget(self.label)

        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)
        self.show()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
            self.label.setStyleSheet(droppingCSS)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.label.setStyleSheet("background-color: lightgray;")
        self.label.setStyleSheet(neutralCSS)

    def dropEvent(self, event):
        self.label.setStyleSheet(neutralCSS)
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        for path in files:
            path = quote(path, safe="")
            webbrowser.open(f"http://localhost:8000/editor/-/{path}?text=%22Hello%22")
        event.acceptProposedAction()

    @asyncClose
    async def closeEvent(self, event):
        # Write window size and position to config file
        self.settings.setValue("size", self.size())
        self.settings.setValue("pos", self.pos())
        await self.closeCallback()


async def main():
    def close_future(future, loop):
        # loop.call_later(10, future.cancel)
        future.cancel()

    loop = asyncio.get_event_loop()
    future = asyncio.Future()

    app = QApplication.instance()
    if hasattr(app, "aboutToQuit"):
        getattr(app, "aboutToQuit").connect(
            functools.partial(close_future, future, loop)
        )

    manager = FileSystemProjectManager(None)
    server = FontraServer(
        host="localhost",
        httpPort=8000,
        projectManager=manager,
    )
    server.setup()

    runner = web.AppRunner(server.httpApp)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 8000)
    await site.start()

    mainWindow = FontraMainWidget(runner.cleanup)
    mainWindow.show()

    await future
    await asyncio.shield(runner.cleanup())

    return True


if __name__ == "__main__":
    try:
        qasync.run(main())
    except asyncio.exceptions.CancelledError:
        sys.exit(0)
