"""Que el comando de type checking documentado y el que corre CI sean el mismo.

Durante 12 días CI corrió `mypy teleflow` mientras el README y `.claude/CLAUDE.md` decían
`mypy .`. El comando documentado fallaba —exit code 2, `Duplicate module named "conftest"`—
por un motivo que se lee como un problema de herramientas, no de código; y el atajo natural
(correr el de CI, que pasa) dejaba los tests sin chequear sin que eso se notara nunca.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github" / "workflows" / "ci.yml"
README = ROOT / "README.md"


def comando_de_ci() -> str:
    run = re.search(r"^\s*run:\s*(mypy .+)$", CI.read_text(encoding="utf-8"), re.MULTILINE)
    assert run, "no se encontró el paso de mypy en ci.yml"
    return run.group(1).strip()


def comando_del_readme() -> str:
    linea = re.search(r"^mypy [^\n#]+", README.read_text(encoding="utf-8"), re.MULTILINE)
    assert linea, "el README no documenta ningún comando mypy"
    return linea.group(0).strip()


def test_ci_y_readme_corren_el_mismo_mypy():
    assert comando_de_ci() == comando_del_readme(), (
        "CI y README mandan comandos de mypy distintos: el que la gente corre a mano no es "
        "el que gatea los merges"
    )


def test_el_type_check_cubre_el_repo_entero():
    """Acotarlo a un subdirectorio deja archivos fuera del gate sin que nada lo diga."""
    assert comando_de_ci() == "mypy .", (
        f"CI corre '{comando_de_ci()}': si se acota el alcance a propósito, actualizar "
        f"este test y el README para que digan por qué"
    )
