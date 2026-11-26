"""Baut die Begleit-Erweiterung (vscode-extension/) als .vsix und installiert sie in VS Code und Cursor.

    python -m claude_pet.vsix            # bauen + in alle gefundenen Editoren installieren
    python -m claude_pet.vsix --remove   # aus allen Editoren entfernen

Ohne Node.js/vsce: eine .vsix ist ein ZIP mit Manifest.
"""
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from .paths import data_dir

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "vscode-extension"
FILES = ("package.json", "extension.js")
EDITORS = {"VS Code": "code", "VS Code Insiders": "code-insiders", "Cursor": "cursor"}

_CONTENT_TYPES = ('<?xml version="1.0" encoding="utf-8"?>'
                  '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                  '<Default Extension=".json" ContentType="application/json"/>'
                  '<Default Extension=".js" ContentType="application/javascript"/>'
                  '<Default Extension=".vsixmanifest" ContentType="text/xml"/></Types>')


def manifest(pkg):
    e = lambda k: escape(str(pkg[k]))  # noqa: E731
    return f'''<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id="{e('name')}" Version="{e('version')}" Publisher="{e('publisher')}"/>
    <DisplayName>{e('displayName')}</DisplayName>
    <Description xml:space="preserve">{e('description')}</Description>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="{escape(pkg['engines']['vscode'])}"/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="ui"/>
    </Properties>
  </Metadata>
  <Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation>
  <Dependencies/>
  <Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/></Assets>
</PackageManifest>'''


def package_info():
    return json.loads((SRC / "package.json").read_text(encoding="utf-8"))


def extension_id():
    pkg = package_info()
    return f"{pkg['publisher']}.{pkg['name']}"


def build(out_dir):
    pkg = package_info()
    out = Path(out_dir) / f"{pkg['name']}-{pkg['version']}.vsix"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("extension.vsixmanifest", manifest(pkg))
        for f in FILES:
            z.write(SRC / f, "extension/" + f)
    return out


# Mac: `code`/`cursor` sind oft nicht im PATH – dann direkt im App-Bundle
MAC_BUNDLES = {"VS Code": ("Visual Studio Code.app", ("code",)),
               "VS Code Insiders": ("Visual Studio Code - Insiders.app", ("code-insiders", "code")),
               "Cursor": ("Cursor.app", ("cursor", "code"))}


def editors():
    """Gefundene Editor-Kommandozeilen {Name: Pfad}."""
    found = {}
    for name, cmd in EDITORS.items():
        path = shutil.which(cmd)
        if not path and sys.platform == "darwin":
            app, bins = MAC_BUNDLES[name]
            for base in ("/Applications", os.path.expanduser("~/Applications")):
                for b in bins:
                    cand = os.path.join(base, app, "Contents", "Resources", "app", "bin", b)
                    if not path and os.path.exists(cand):
                        path = cand
        if path:
            found[name] = path
    return found


def _run(cli, *args):
    # .cmd-Wrapper (code.cmd) brauchen unter Windows die Shell
    r = subprocess.run([cli, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       shell=sys.platform == "win32" and cli.lower().endswith(".cmd"), timeout=180)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def install(vsix):
    results = {}
    for name, cli in editors().items():
        results[name] = _run(cli, "--install-extension", str(vsix), "--force")
    return results


def remove():
    results = {}
    for name, cli in editors().items():
        results[name] = _run(cli, "--uninstall-extension", extension_id())
    return results


def main(argv):
    if "--remove" in argv:
        res = remove()
    else:
        vsix = build(data_dir())
        print(f"gebaut: {vsix}")
        res = install(vsix)
    if not res:
        print("kein VS Code / Cursor gefunden (Befehl code bzw. cursor nicht im PATH)")
    for name, (ok, out) in res.items():
        print(f"{'OK' if ok else 'FEHLER'} {name}" + ("" if ok else f": {out[-300:]}"))
    return 0 if all(ok for ok, _ in res.values()) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
