import logging
import multiprocessing
import os
import pathlib
import secrets
import signal
import socket
import sys
import webbrowser
from urllib.parse import quote

from fontra import __version__ as fontraVersion
from fontra.core.server import FontraServer
from fontra.filesystem.projectmanager import FileSystemProjectManager
from PyQt6.QtCore import QPoint, QSettings, QSize, Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

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
    def __init__(self, port):
        super().__init__()
        self.port = port
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

    def closeEvent(self, event):
        self.settings.setValue("size", self.size())
        self.settings.setValue("pos", self.pos())

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
            path = pathlib.Path(path).resolve()
            assert path.is_absolute()
            parts = list(path.parts)
            if not path.drive:
                assert parts[0] == "/"
                del parts[0]
            path = "/".join(quote(part, safe="") for part in parts)
            webbrowser.open(
                f"http://localhost:{self.port}/editor/-/{path}?text=%22Hello%22"
            )
        event.acceptProposedAction()


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


def runFontraServer(port):
    logging.basicConfig(
        format="%(asctime)s %(name)-17s %(levelname)-8s %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    manager = FileSystemProjectManager(None)
    server = FontraServer(
        host="localhost",
        httpPort=port,
        projectManager=manager,
        versionToken=secrets.token_hex(4),
    )
    server.setup()
    server.run(showLaunchBanner=False)


def main():
    port = getFreeTCPPort()
    serverProcess = multiprocessing.Process(target=runFontraServer, args=(port,))
    serverProcess.start()

    app = QApplication(sys.argv)
    app.aboutToQuit.connect(lambda: os.kill(serverProcess.pid, signal.SIGINT))

    mainWindow = FontraMainWidget(port)
    mainWindow.show()

    if "test-startup" in sys.argv:

        def delayedQuit():
            print("test-startup")
            app.quit()

        QTimer.singleShot(1500, delayedQuit)

    sys.exit(app.exec())


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
