"""Build a minimal VS Code VSIX installer without a network dependency."""
import json
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "vscode-extension"


def build() -> Path:
    metadata = json.loads((EXTENSION / "package.json").read_text(encoding="utf-8"))
    source = EXTENSION / "src" / "extension.ts"
    runtime = EXTENSION / "extension.js"
    if source.read_bytes() != runtime.read_bytes():
        raise RuntimeError("Extension source changed. Run npm run compile first.")
    bundled_backend = EXTENSION / "backend" / "spotai_backend"
    executable = bundled_backend / "spotai_backend.exe"
    if not executable.is_file():
        raise RuntimeError("Bundled backend is missing. Run python scripts/build_backend.py first.")

    name = metadata["name"]
    version = metadata["version"]
    publisher = metadata["publisher"]
    destination = EXTENSION / f"{name}-{version}.vsix"
    manifest = f"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id="{escape(name)}" Version="{escape(version)}" Publisher="{escape(publisher)}" />
    <DisplayName>{escape(metadata["displayName"])}</DisplayName>
    <Description xml:space="preserve">{escape(metadata["description"])}</Description>
    <Categories>{escape(",".join(metadata["categories"]))}</Categories>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="{escape(metadata["engines"]["vscode"])}" />
    </Properties>
  </Metadata>
  <Installation><InstallationTarget Id="Microsoft.VisualStudio.Code" /></Installation>
  <Dependencies />
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Code.Details" Path="extension/README.md" Addressable="true" />
  </Assets>
</PackageManifest>"""
    content_types = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="vsixmanifest" ContentType="text/xml" />
  <Default Extension="json" ContentType="application/json" />
  <Default Extension="js" ContentType="application/javascript" />
  <Default Extension="md" ContentType="text/markdown" />
</Types>"""
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("extension.vsixmanifest", manifest)
        for filename in ("package.json", "extension.js", "README.md"):
            archive.write(EXTENSION / filename, f"extension/{filename}")
        for item in sorted(bundled_backend.rglob("*")):
            if item.is_file():
                relative = item.relative_to(EXTENSION).as_posix()
                archive.write(item, f"extension/{relative}")
    return destination


if __name__ == "__main__":
    try:
        print(build())
    except (OSError, RuntimeError, KeyError) as exc:
        print(f"VSIX build failed: {exc}", file=sys.stderr)
        sys.exit(1)
