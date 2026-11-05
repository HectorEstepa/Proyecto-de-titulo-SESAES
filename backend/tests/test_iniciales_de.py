import pytest

from app.routers.admin import _iniciales_de


@pytest.mark.parametrize(
    "nombre,esperado",
    [
        (
            "Mar?a Fernanda Garc?a L?pez",
            "MG",
        ),
        (
            "Juan Carlos P?rez",
            "JP",
        ),
        (
            "Juan P?rez",
            "JP",
        ),
        (
            "Camila Soto",
            "CS",
        ),
        (
            "Juan",
            "J",
        ),
        (
            "",
            "?",
        ),
        (
            None,
            "?",
        ),
        (
            "   ",
            "?",
        ),
    ],
)
def test_iniciales_de_primer_nombre_mas_primer_apellido(
    nombre,
    esperado,
):
    """
    Regla: primer nombre + primer apellido (no las dos primeras
    palabras a secas, no el ?ltimo apellido). Con nombres
    compuestos, el primer apellido cae en el punto medio de los
    tokens redondeando hacia arriba: con cantidad impar de
    palabras, la palabra extra queda del lado de los nombres
    ("Juan Carlos P?rez" -> nombre compuesto "Juan Carlos" +
    apellido "P?rez", no "Juan" + "Carlos"). Misma regla que
    frontend/.../citas/admin-citas.utils.ts::inicialesDe.
    """
    assert _iniciales_de(nombre) == esperado
