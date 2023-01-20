import json
import subprocess
import sys


def printNotarizeLog(submissionID, appleID, teamID, password):
    infoCommand = [
        "xcrun",
        "notarytool",
        "log",
        "--apple-id", appleID,
        "--password", password,
        "--team-id", teamID,
        submissionID,
    ]
    try:
        result = subprocess.run(
            infoCommand, check=True, capture_output=True, encoding="ascii"
        )
    except subprocess.CalledProcessError as error:
        print("STDOUT", error.stdout)
        print("STDERR", error.stderr)
        raise
    print(result.stdout)


notarizeResult = json.loads(sys.stdin.read().encode("ascii"))

submissionID = notarizeResult.get("id")

if submissionID is None:
    print(notarizeResult)
    sys.exit(1)

printNotarizeLog(submissionID, sys.argv[1], sys.argv[2], sys.argv[3])
