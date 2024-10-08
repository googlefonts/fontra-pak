import asyncio
import logging
import multiprocessing
import os
import pathlib
import secrets
import signal
import sys
import tempfile
import webbrowser
from contextlib import aclosing, redirect_stderr, redirect_stdout
from urllib.parse import quote

from fontra import __version__ as fontraVersion
from fontra.backends import getFileSystemBackend, newFileSystemBackend
from fontra.backends.copy import copyFont
from fontra.core.classes import FontSource, LineMetric
from fontra.core.server import FontraServer, findFreeTCPPort
from fontra.core.urlfragment import dumpURLFragment
from fontra.filesystem.projectmanager import FileSystemProjectManager
from PyQt6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QSettings,
    QSize,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
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

exportFileTypes = [
    # name, extension
    ("TrueType", "ttf"),
    ("OpenType", "otf"),
] + fileTypes

exportFileTypesMapping = {
    f"{name} (*.{extension})": f".{extension}" for name, extension in exportFileTypes
}

exportExtensionMapping = {v: k for k, v in exportFileTypesMapping.items()}


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


def getFontPath(path, fileType, mapping):
    extension = mapping[fileType]
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

        button = QPushButton("&New Font...", self)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        button.clicked.connect(self.newFont)

        layout.addWidget(button)
        layout.addWidget(self.label)

        self.textBox = QPlainTextEdit(self.settings.value("sampleText", "Hello"), self)
        self.textBox.setFixedHeight(50)

        self.textBox.textChanged.connect(
            lambda: self.settings.setValue("sampleText", self.textBox.toPlainText())
        )
        layout.addWidget(QLabel("Initial sample text:"))
        layout.addWidget(self.textBox)
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
            textboxValue = self.textBox.toPlainText()
            openFile(path, self.port, sampleText=textboxValue)
        event.acceptProposedAction()

    @property
    def activeFolder(self):
        activeFolder = self.settings.value("activeFolder", os.path.expanduser("~"))
        if not os.path.isdir(activeFolder):
            activeFolder = os.path.expanduser("~")
        return activeFolder

    def newFont(self):
        fontPath, fileType = QFileDialog.getSaveFileName(
            self,
            "New Font...",
            os.path.join(self.activeFolder, "Untitled"),
            ";;".join(fileTypesMapping),
        )

        if not fontPath:
            # User cancelled
            return

        fontPath = getFontPath(fontPath, fileType, fileTypesMapping)

        self.settings.setValue("activeFolder", os.path.dirname(fontPath))

        # Create a new empty project on disk
        try:
            asyncio.run(createNewFont(fontPath))
        except Exception as e:
            showMessageDialog("The new font could not be saved", repr(e))
            return

        if os.path.exists(fontPath):
            textboxValue = self.textBox.toPlainText()
            openFile(fontPath, self.port, sampleText=textboxValue)

    def messageFromServer(self, item):
        action, path, options = item
        handler = getattr(self, action, None)
        if handler is not None:
            handler(path, options)

    def exportAs(self, path, options):
        sourcePath = pathlib.Path(path)
        fileExtension = options["format"]

        wFlags = self.windowFlags()
        self.setWindowFlags(wFlags | Qt.WindowType.WindowStaysOnTopHint)
        self.show()
        self.setWindowFlags(wFlags)
        self.show()

        destPath, fileType = QFileDialog.getSaveFileName(
            self,
            "Export font...",
            os.path.join(self.activeFolder, sourcePath.stem),
            exportExtensionMapping["." + fileExtension],
        )

        if not destPath:
            # User cancelled
            return

        destPath = getFontPath(destPath, fileType, exportFileTypesMapping)

        with tempfile.NamedTemporaryFile() as logFile:
            exportProcess = multiprocessing.Process(
                target=exportFontToPath,
                args=(sourcePath, destPath, fileExtension, logFile.name),
            )
            exportProcess.start()
            exportProcess.join()
            if exportProcess.exitcode:
                logFile.seek(0)
                logData = logFile.read().decode("utf-8")
                logLines = logData.splitlines()
                infoText = logLines[-1] if logLines else "The reason is not clear."
                showMessageDialog(
                    "The font could not be exported", infoText, detailedText=logData
                )


def exportFontToPath(sourcePath, destPath, fileExtension, logFilePath):
    with open(logFilePath, "w") as logFile:
        # sys.stdout = sys.stderr = logFile

        with redirect_stdout(logFile), redirect_stderr(logFile):
            asyncio.run(exportFontToPathAsync(sourcePath, destPath, fileExtension))

        logFile.flush()


async def exportFontToPathAsync(sourcePath, destPath, fileExtension):
    sourcePath = pathlib.Path(sourcePath)
    destPath = pathlib.Path(destPath)

    if fileExtension in {"ttf", "otf"}:
        from fontra.workflow.workflow import Workflow

        continueOnError = False
        config = dict(
            steps=[
                dict(filter="decompose-composites", onlyVariableComposites=True),
                dict(filter="drop-unreachable-glyphs"),
                dict(
                    output="compile-fontmake",
                    destination=destPath.name,
                    options=dict(verbose="DEBUG"),
                ),
            ]
        )

        workflow = Workflow(config=config, parentDir=sourcePath.parent)

        async with workflow.endPoints() as endPoints:
            assert endPoints.endPoint is not None

            for output in endPoints.outputs:
                await output.process(destPath.parent, continueOnError=continueOnError)
    else:
        sourceBackend = getFileSystemBackend(sourcePath)
        destBackend = newFileSystemBackend(destPath)
        async with aclosing(sourceBackend), aclosing(destBackend):
            await copyFont(sourceBackend, destBackend)


defaultLineMetrics = {
    "ascender": (750, 16),
    "descender": (-250, -16),
    "xHeight": (500, 16),
    "capHeight": (750, 16),
    "baseline": (0, -16),
}


async def createNewFont(fontPath):
    # Create a new empty project on disk
    import secrets

    defaultSource = FontSource(
        name="Regular",
        lineMetricsHorizontalLayout={
            name: LineMetric(value=value, zone=zone)
            for name, (value, zone) in defaultLineMetrics.items()
        },
    )

    destBackend = newFileSystemBackend(fontPath)
    await destBackend.putSources({secrets.token_hex(4): defaultSource})
    await destBackend.aclose()


def openFile(path, port, sampleText="Hello"):
    path = pathlib.Path(path).resolve()
    assert path.is_absolute()
    parts = list(path.parts)
    if not path.drive:
        assert parts[0] == "/"
        del parts[0]
    path = "/".join(quote(part, safe="") for part in parts)

    urlFragment = dumpURLFragment({"text": sampleText})
    webbrowser.open(f"http://localhost:{port}/editor/-/{path}{urlFragment}")


def showMessageDialog(
    message, infoText, detailedText=None, icon=QMessageBox.Icon.Warning
):
    dialog = QMessageBox()
    if icon is not None:
        dialog.setIcon(icon)
    dialog.setText(message)
    dialog.setInformativeText(infoText)
    if detailedText is not None:
        dialog.setStyleSheet("QTextEdit { font-weight: regular; }")
        dialog.setDetailedText(detailedText)
    dialog.exec()


class FontraPakProjectManager(FileSystemProjectManager):
    async def exportAs(self, fontHandler, options):
        self.appQueue.put(("exportAs", fontHandler.projectIdentifier, options))


def runFontraServer(port, queue):
    logging.basicConfig(
        format="%(asctime)s %(name)-17s %(levelname)-8s %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    manager = FontraPakProjectManager(None)
    manager.appQueue = queue
    server = FontraServer(
        host="localhost",
        httpPort=port,
        projectManager=manager,
        versionToken=secrets.token_hex(4),
    )
    server.setup()
    server.run(showLaunchBanner=False)


class QueueFetchWorker(QObject):
    fetched = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, queue):
        super().__init__()
        self.queue = queue
        self.items = {}

    def run(self):
        while True:
            item = self.queue.get()
            if item is None:
                break

            identifier = secrets.token_hex(4)
            self.items[identifier] = item

            self.fetched.emit(identifier)

        self.finished.emit()

    def popItem(self, identifier):
        return self.items.pop(identifier)


class AppMediator:
    def __init__(self):
        self.queue = multiprocessing.Queue()
        self.thread = QThread()
        self.queueWorker = QueueFetchWorker(self.queue)
        self.queueWorker.moveToThread(self.thread)
        self.thread.started.connect(self.queueWorker.run)
        self.queueWorker.finished.connect(self.thread.quit)
        self.queueWorker.finished.connect(self.queueWorker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def connect(self, callback):
        self.callback = callback
        self.queueWorker.fetched.connect(self._callback)

    def _callback(self, identifier):
        self.callback(self.queueWorker.popItem(identifier))

    def close(self):
        self.queue.put(None)
        self.thread.quit()
        self.thread.wait()


def main():
    mediator = AppMediator()

    port = findFreeTCPPort()
    serverProcess = multiprocessing.Process(
        target=runFontraServer, args=(port, mediator.queue)
    )

    serverProcess.start()

    app = FontraApplication(sys.argv, port)

    def cleanup():
        mediator.close()
        os.kill(serverProcess.pid, signal.SIGINT)

    app.aboutToQuit.connect(cleanup)

    mainWindow = FontraMainWidget(port)
    mediator.connect(mainWindow.messageFromServer)
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
