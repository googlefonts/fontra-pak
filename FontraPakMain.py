import logging
import multiprocessing
import os
import pathlib
import secrets
import signal
import sys
import webbrowser
from urllib.parse import quote

from fontra import __version__ as fontraVersion
from fontra.backends import newFileSystemBackend
from fontra.core.server import FontraServer, findFreeTCPPort
from fontra.filesystem.projectmanager import FileSystemProjectManager
from PyQt6.QtCore import QEvent, QPoint, QSettings, QSize, Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

commonCSS = """
border-radius: 20px;
border-style: dashed;
font-size: 18px;
padding: 16px;
"""

neutralCSS = (
    """
background-color: rgba(255,255,255,128);
border: 5px solid lightgray;
"""
    + commonCSS
)

droppingCSS = (
    """
background-color: rgba(255,255,255,64);
border: 5px solid gray;
"""
    + commonCSS
)

mainText = """
<span style="font-size: 40px;">Drop font files here</span>
<br>
<br>
Your fonts will stay on your computer and will not be uploaded anywhere.
<br>
<br>
Fontra Pak reads and writes .ufo, .designspace, .rcjk and .fontra
<br>
Additionally, it can read (not write) .ttf, .otf, and (with some limitations)
.glyphs and .glyphspackage
"""

fileTypes = [
    # name, extension
    ("Designspace", "designspace"),
    ("Fontra", "fontra"),
    ("RoboCJK", "rcjk"),
    ("Unified Font Object", "ufo"),
]

fileTypesMapping = {
    f"{name} (*.{extension})": f".{extension}" for name, extension in fileTypes
}


class FontraApplication(QApplication):
    def __init__(self, argv, port):
        self.port = port
        super().__init__(argv)

    def event(self, event):
        """Handle macOS FileOpen events."""
        if event.type() == QEvent.Type.FileOpen:
            openFile(event.file(), self.port)
        else:
            return super().event(event)

        return True


def getFontPath(path, fileType):
    extension = fileTypesMapping[fileType]
    if not path.endswith(extension):
        path += extension

    return path


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

        self.label = QLabel(mainText)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet(neutralCSS)
        self.label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.label.setWordWrap(True)

        layout = QVBoxLayout()
        h_layout = QHBoxLayout()
        layout.addLayout(h_layout)

        button = QPushButton("&New Font...", self)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        button.clicked.connect(self.newFont)
        h_layout.addWidget(button)

        self.textBox = QLineEdit("Your sample text here", self)
        self.textBox.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        h_layout.addWidget(self.textBox)

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
            textboxValue = self.textBox.text()
            openFile(path, self.port, defaultText=textboxValue)
        event.acceptProposedAction()

    def newFont(self):
        fontPath, fileType = QFileDialog.getSaveFileName(
            self,
            "New Font...",
            "Untitled",
            ";;".join(fileTypesMapping),
        )

        if not fontPath:
            # User cancelled
            return

        fontPath = getFontPath(fontPath, fileType)

        # Create a new empty project on disk
        destBackend = newFileSystemBackend(fontPath)
        destBackend.close()

        if os.path.exists(fontPath):
            textboxValue = self.textBox.text()
            openFile(fontPath, self.port, defaultText=textboxValue)


def prepareDefaultTextForURL(text):
    if not text:
        return "Hello"
    if text == "Your sample text here":
        return "Hello"
    return text.replace(" ", "%20").replace("\n", "%20").replace("\r", "%20")


def openFile(path, port, defaultText="Hello"):
    path = pathlib.Path(path).resolve()
    assert path.is_absolute()
    parts = list(path.parts)
    if not path.drive:
        assert parts[0] == "/"
        del parts[0]
    path = "/".join(quote(part, safe="") for part in parts)
    txt = prepareDefaultTextForURL(defaultText)
    webbrowser.open(f"http://localhost:{port}/editor/-/{path}?text=%22{txt}%22")


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
    port = findFreeTCPPort()
    serverProcess = multiprocessing.Process(target=runFontraServer, args=(port,))
    serverProcess.start()

    app = FontraApplication(sys.argv, port)
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
