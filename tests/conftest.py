import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from teleflow.dsl.parser import TeleFlowParser  # noqa: E402


@pytest.fixture(scope="session")
def parser() -> TeleFlowParser:
    return TeleFlowParser()


@pytest.fixture(scope="session")
def ceibal_source() -> str:
    return (ROOT / "examples" / "ceibal.tflow").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def venta_source() -> str:
    return (ROOT / "examples" / "venta_internet_hogar.tflow").read_text(encoding="utf-8")
