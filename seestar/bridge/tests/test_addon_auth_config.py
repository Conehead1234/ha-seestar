"""Static contracts for the bundled driver's interoperability-key wiring."""

from pathlib import Path


_ADDON_DIR = Path(__file__).resolve().parents[2]


def test_manifest_exposes_read_only_share_and_optional_pem_path():
    manifest = (_ADDON_DIR / "config.yaml").read_text(encoding="utf-8")

    assert "interop_pem_path: \"\"" in manifest
    assert "interop_pem_path: str?" in manifest
    assert "- type: share\n    read_only: true" in manifest


def test_startup_validates_and_persists_only_the_pem_path():
    script = (
        _ADDON_DIR / "rootfs/etc/s6-overlay/scripts/init-config"
    ).read_text(encoding="utf-8")

    assert "^/share/seestar/[A-Za-z0-9._-]+\\.pem$" in script
    assert "serialization.load_pem_private_key" in script
    assert "isinstance(key, RSAPrivateKey)" in script
    assert 'echo "[seestar_initialization]"' in script
    assert 'echo "interop_pem = ' in script
    assert "handle.read()" in script
    assert "bashio::log.info \"Validated the configured interoperability PEM.\"" in script


def test_docs_never_instruct_users_to_store_key_content_in_options():
    docs = (_ADDON_DIR / "DOCS.md").read_text(encoding="utf-8")
    normalized_docs = " ".join(docs.split())

    assert "/share/seestar/seestar_interop.pem" in docs
    assert "do not paste it into the add-on options" in normalized_docs
    assert "chmod 0600" in docs
