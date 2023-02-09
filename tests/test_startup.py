import pathlib
import subprocess
import sys

repoRoot = pathlib.Path(__file__).resolve().parent.parent


def test_startup():
    if sys.platform == "darwin":
        app_path = (
            repoRoot / "dist" / "Fontra Pak.app" / "Contents" / "MacOS" / "Fontra Pak"
        )
    elif sys.platform == "win32":
        app_path = repoRoot / "dist" / "Fontra Pak.exe"
        return  # FIXME: This currently does not work on Windows
    else:
        return
    result = subprocess.run(
        [app_path, "test-startup"],
        capture_output=True,
        timeout=30,
        check=False,
        encoding="utf-8",
    )
    assert "" == result.stderr
    assert "test-startup\n" == result.stdout
