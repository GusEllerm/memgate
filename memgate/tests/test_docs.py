"""The integration guide bundled in the plugin's skill must be the guide in this package."""

from pathlib import Path

import pytest

GUIDE = Path(__file__).resolve().parents[1] / "INTEGRATION.md"
BUNDLED = Path(__file__).resolve().parents[2] / "plugins" / "memgate" / "skills" / "integrate-memgate" / "INTEGRATION.md"


@pytest.mark.skipif(not BUNDLED.exists(), reason="not in a repo checkout with the plugin")
def test_the_skill_bundles_the_current_guide():
    assert BUNDLED.read_text() == GUIDE.read_text(), "copy memgate/INTEGRATION.md into the plugin's skill folder"


def test_the_package_version_matches_pyproject():
    import tomllib
    import memgate
    pyproject = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())
    assert memgate.__version__ == pyproject["project"]["version"]
