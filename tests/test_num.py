from __future__ import annotations

import pytest

import mintchip as mc


@pytest.mark.parametrize(
    ("kwargs", "text"),
    [
        ({"value": 0.82}, "0.82"),
        ({"value": 0.82, "pm": 0.03}, "0.82 ± 0.03"),
        ({"value": 0.8213, "pm": 0.012}, "0.821 ± 0.012"),
        ({"value": 20.31, "unit": "ms"}, "20.3 ms"),
        ({"value": 82, "unit": "%"}, "82%"),
        ({"value": 1234.5}, "1,234"),
        ({"value": 0.000123}, "1.23e−4"),
        ({"value": 0.5, "signed": True}, "+0.5"),
        ({"value": -0.5}, "−0.5"),
        ({"value": 3.14159, "sig": 5}, "3.1416"),
    ],
)
def test_formats(kwargs: dict, text: str) -> None:
    assert mc.num(**kwargs).text() == text


def test_no_graphic_and_ascii() -> None:
    c = mc.num(-0.82, pm=0.03)
    assert c.svg() == "" and c.text(value=False) == ""
    assert c.text(ascii=True) == "-0.82 +/- 0.03"
    assert '<span class="mc-v">−0.82 ± 0.03</span>' in c.html()


def test_validation() -> None:
    with pytest.raises(mc.ChipError, match="sig"):
        mc.num(1.0, sig=0)
    with pytest.raises(mc.ChipError, match="pm"):
        mc.num(1.0, pm=-0.1)
