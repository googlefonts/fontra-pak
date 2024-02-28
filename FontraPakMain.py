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
from fontra.core.server import FontraServer, findFreeTCPPort
from fontra.filesystem.projectmanager import FileSystemProjectManager
from fontra.backends import newFileSystemBackend
from fontra.backends.designspace import DesignspaceBackend
from PyQt6.QtCore import QEvent, QPoint, QSettings, QSize, Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QPushButton,
    QMenu,
    QFileDialog
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


class FontraMainWidget(QMainWindow):
    def __init__(self, port):
        super().__init__()
        self.port = port
        self.setWindowTitle("Fontra Pak")
        self.resize(720, 480)

        fileMenu = self.menuBar().addMenu('File')

        newAction = fileMenu.addAction('New')
        newAction.triggered.connect(self.new)

        openFileAction = fileMenu.addAction('Open File')
        openFileAction.triggered.connect(self.openFile)

        openFolderAction = fileMenu.addAction('Open Folder')
        openFolderAction.triggered.connect(self.open)

        saveAction = fileMenu.addAction('Save')
        saveAction.triggered.connect(self.save)

        saveAsAction = fileMenu.addAction('Save as...')
        saveAsAction.triggered.connect(self.saveAs)

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
        layout.addWidget(self.label)
        layout.addWidget(QLabel(f"Fontra version {fontraVersion}"))
        '''
        menu = QMenu(self)
        button = QPushButton("&File", self).setMenu(menu)
        layout.addWidget(button)
        '''
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
            openFile(path, self.port)
        event.acceptProposedAction()

    def new(self):
        newFileName = 'untitled.designspace'
        dialog = QFileDialog.getSaveFileName(self, 
                                             'Save as...', 
                                             '/home/user/' + newFileName, 
                                             'Designspace (*.designspace)')
        projectPath = dialog[0]
        destBackend = DesignspaceBackend.createFromPath(projectPath)
        destBackend.close()
        if os.path.exists(projectPath):
            openFile(projectPath, self.port)

    def newSave(self):
        newFileName = 'untitled.fontra'
        dialog = QFileDialog.getSaveFileName(self, 
                                             'Save as...', 
                                             '/home/user/' + newFileName, 
                                             'Fontra (*.fontra)')
        projectPath = dialog[0]
        destBackend = newFileSystemBackend(projectPath)
        destBackend.close()
        if os.path.exists(projectPath):
            openFile(projectPath, self.port)

    def open(self):
        print("Fontra Pak: open folder")
        #dialog = QFileDialog.getOpenFileName(self, 'Open File')
        #path = dialog[0]
        projectPath = QFileDialog.getExistingDirectory(self, "Open Fontra Folder", "/home", QFileDialog.Option.ShowDirsOnly)
        if os.path.exists(projectPath):
            openFile(projectPath, self.port)

    def openFile(self):
        print("Fontra Pak: open file")
        dialog = QFileDialog.getOpenFileName(self, 'Open File')
        projectPath = dialog[0]
        if os.path.exists(projectPath):
            openFile(projectPath, self.port)

    def save(self):
        print("Fontra Pak: save")

    def saveAs(self):
        print("Fontra Pak: saveAs")
        '''
        dialog = QFileDialog.getSaveFileName(self, 
                                             'Save as...', 
                                             '/home', 
                                             'Designspace (*.designspace);;Fontra (*.fontra);;Robo CJK (*.rcjk);;Unified Font Object (*.ufo)', 
                                             options=QFileDialog.Option.DontUseNativeDialog)
        '''
        dialog = QFileDialog.getSaveFileName(self, 
                                             'Save as...', 
                                             '/home', 
                                             'Designspace (*.designspace);;Fontra (*.fontra);;Robo CJK (*.rcjk);;Unified Font Object (*.ufo)')
        path = dialog[0]
        fileType = dialog[1]
        if fileType == 'Designspace (*.designspace)':
            if not path.endswith('.designspace'):
                path += '.designspace'
        elif fileType == 'Fontra (*.fontra)': 
            if not path.endswith('.fontra'):
                path += '.fontra'
        elif fileType == 'Robo CJK (*.rcjk)':
            if not path.endswith('.rcjk'):
                path += '.rcjk'
        elif fileType == 'Unified Font Object (*.ufo)': 
            if not path.endswith('.ufo'):
                path += '.ufo'

        print('path: ', path)
        #file = open( name, 'w' )
        #text = self.textEdit.toPlainText()
        #file.write(text)
        #file.close()


def openFile(path, port):
    path = pathlib.Path(path).resolve()
    assert path.is_absolute()
    parts = list(path.parts)
    if not path.drive:
        assert parts[0] == "/"
        del parts[0]
    path = "/".join(quote(part, safe="") for part in parts)
    webbrowser.open(f"http://localhost:{port}/editor/-/{path}?text=%22Hello%22")


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
