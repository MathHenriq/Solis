import pytest

from solis import banco


@pytest.fixture(autouse=True)
def banco_temporario(tmp_path):
    """Cada teste num SQLite próprio — nunca no banco de verdade do usuário."""
    banco.usar(tmp_path / 'solis.db')
