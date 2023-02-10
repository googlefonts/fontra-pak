import asyncio
import functools
import logging
import secrets
import socket
import sys
import webbrowser
from urllib.parse import quote

import qasync
from aiohttp import web
from fontra import __version__ as fontraVersion
from fontra.core.server import FontraServer
from fontra.filesystem.projectmanager import FileSystemProjectManager
from PyQt6.QtCore import QPoint, QSettings, QSize, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QMainWindow, QSizePolicy, QVBoxLayout, QWidget
from qasync import QApplication, asyncClose

neutralCSS = """
background-color: rgba(255,255,255,128);
border: 5px solid lightgray;
border-radius: 20px;
border-style: dashed
"""

droppingCSS = """
background-color: rgba(255,255,255,64);
border: 5px solid gray;
border-radius: 20px;
border-style: dashed
"""


class FontraMainWidget(QMainWindow):
    def __init__(self, port, closeCallback):
        super().__init__()
        self.port = port
        self.closeCallback = closeCallback
        self.setWindowTitle("Fontra Pak")
        self.resize(720, 480)

        self.settings = QSettings("xyz.fontra", "FontraPak")

        self.resize(self.settings.value("size", QSize(720, 480)))
        self.move(self.settings.value("pos", QPoint(50, 50)))

        self.setAcceptDrops(True)

        self.label = QLabel("Drop font files here")
        self.label.setFont(QFont("Helvetica", 40))
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet(neutralCSS)
        self.label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(QLabel(f"Fontra version {fontraVersion}"))

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
            webbrowser.open(
                f"http://localhost:{self.port}/editor/-/{path}?text=%22Hello%22"
            )
        event.acceptProposedAction()

    @asyncClose
    async def closeEvent(self, event):
        # Write window size and position to config file
        self.settings.setValue("size", self.size())
        self.settings.setValue("pos", self.pos())
        await self.closeCallback()


def getFreeTCPPort(startPort=8000):
    port = startPort
    while True:
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            tcp.bind(("", port))
        except OSError as e:
            if e.errno != 48:
                raise
            port += 1
        else:
            break
        finally:
            tcp.close()
    return port


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

    port = getFreeTCPPort()

    manager = FileSystemProjectManager(None)
    server = FontraServer(
        host="localhost",
        httpPort=port,
        projectManager=manager,
        versionToken=secrets.token_hex(4),
    )
    server.setup()

    runner = web.AppRunner(server.httpApp)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", port)
    await site.start()

    if "test-startup" in sys.argv:

        def delayed_quit():
            print("test-startup")
            loop.stop()

        loop.call_later(5, delayed_quit)

    mainWindow = FontraMainWidget(port, runner.cleanup)
    mainWindow.show()

    await future
    await asyncio.shield(runner.cleanup())

    return True


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(name)-17s %(levelname)-8s %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    try:
        qasync.run(main())
    except asyncio.exceptions.CancelledError:
        sys.exit(0)
