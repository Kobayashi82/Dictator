import hashlib
import os
from pathlib import Path

import pytest

from dictado.models.download import PARAKEET, SILERO, ModelFile, verify

MODELS = Path(os.environ.get("LOCALAPPDATA", "")) / "Dictado" / "models"


def test_git_blob_hash(tmp_path):
    content = b"hola\n"
    sha1 = hashlib.sha1(b"blob 5\0" + content).hexdigest()
    path = tmp_path / "a.txt"
    path.write_bytes(content)
    assert verify(path, ModelFile("r", "v", "a.txt", 5, git_sha1=sha1))
    path.write_bytes(b"hola!")
    assert not verify(path, ModelFile("r", "v", "a.txt", 5, git_sha1=sha1))


def test_sha256_and_size(tmp_path):
    content = b"modelo"
    path = tmp_path / "m.onnx"
    path.write_bytes(content)
    good = ModelFile("r", "v", "m.onnx", len(content), sha256=hashlib.sha256(content).hexdigest())
    assert verify(path, good)
    assert not verify(path, ModelFile("r", "v", "m.onnx", len(content) + 1, sha256=good.sha256))
    assert not verify(tmp_path / "no-existe", good)


@pytest.mark.parametrize("pack", [SILERO, PARAKEET])
def test_installed_models_match_pinned_hashes(pack):
    folder = MODELS / pack.folder
    if not folder.is_dir():
        pytest.skip("modelos no instalados")
    for f in pack.files:
        assert verify(folder / f.name, f), f.name
