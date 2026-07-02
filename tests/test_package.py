import re

import bidkit


def test_version_is_exposed_and_pep440_like() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+([a-z0-9.+-]*)?", bidkit.__version__)
