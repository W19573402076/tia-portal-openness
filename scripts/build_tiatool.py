# -*- coding: utf-8 -*-
"""Compile TiaTool.cs with the .NET Framework csc. No Visual Studio needed."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CSC = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
DEFAULT_API = r"E:\TIA_V21\coding\Portal V21\PublicAPI\V21\net48"


def main():
    api = os.environ.get("TIA_API_DIR", DEFAULT_API)
    base = os.path.join(api, "Siemens.Engineering.Base.dll")
    step7 = os.path.join(api, "Siemens.Engineering.Step7.dll")
    for p in (base, step7):
        if not os.path.isfile(p):
            sys.exit("Missing Openness assembly: %s\nSet TIA_API_DIR." % p)
    outdir = os.path.join(HERE, "bin")
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, "TiaTool.exe")
    cmd = [CSC, "-nologo", "-codepage:65001", "-platform:x64",
           "-target:exe", "-out:" + out,
           "-r:" + base, "-r:" + step7,
           os.path.join(HERE, "TiaTool.cs")]
    print(" ".join('"%s"' % c if " " in c else c for c in cmd))
    rc = subprocess.call(cmd)
    if rc != 0:
        sys.exit(rc)
    print("built", out)


if __name__ == "__main__":
    main()
