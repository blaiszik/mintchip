from __future__ import annotations

import pytest

import mintchip as mc
from mintchip.prose import format_prose, lint
from mintchip.scales import union_domain

LOSS = mc.spark([1.84, 1.32, 0.96, 0.74, 0.61, 0.52, 0.46, 0.43, 0.42])
LIFT = mc.ci(0.08, (0.05, 0.11), level=0.95)


def test_formats() -> None:
    t = "Loss fell to {loss} & lift was {lift}."
    assert format_prose(t, loss=LOSS, lift=LIFT) == (
        f"Loss fell to {LOSS.text(compact=True)} & lift was {LIFT.text(compact=True)}."
    )
    assert format_prose(t, loss=LOSS, lift=LIFT, compact=False).endswith(f"{LIFT.text()}.")
    assert format_prose(t, ascii=True, loss=LOSS, lift=LIFT).isascii()
    md = format_prose(t, format="markdown", loss=LOSS, lift=LIFT)
    assert f"`{LOSS.text(compact=True)}`" in md and " & " in md
    assert format_prose(t, format="md", loss=LOSS, lift=LIFT) == md
    assert "\x1b[34m" in format_prose(t, format="ansi", loss=LOSS, lift=LIFT)
    assert "\x1b[" in format_prose(t, color=True, loss=LOSS, lift=LIFT)
    h = format_prose(t, format="html", loss=LOSS, lift=LIFT)
    assert h.startswith('Loss fell to <span class="mc mc-spark">') and " &amp; lift" in h
    assert mc.format_prose is format_prose and mc.lint is lint


def test_auto_share_needs_one_kind_and_one_unit() -> None:
    a, b = mc.spark([1, 2, 3, 4], unit="ms"), mc.spark([100, 200, 300, 400], unit="ms")
    shared = format_prose("{a} {b}", a=a, b=b)
    assert shared.split()[2] != shared.split()[5], "one scale: the small series sits low"
    own = format_prose("{a} {b}", a=a, b=b, share=False)
    assert own.split()[2] == own.split()[5], "own scales: identical shapes"
    c, d = mc.spark([1, 2, 3, 4]), mc.spark([100, 200, 300, 400])
    plain = format_prose("{c} {d}", c=c, d=d)
    assert plain.split()[1] == plain.split()[3], "no unit, no automatic sharing"
    grouped = format_prose("{c} {d}", c=c, d=d, share=[("c", "d")])
    both = union_domain(c.domain, d.domain)
    assert grouped == f"{c.text(compact=True, domain=both)} {d.text(compact=True, domain=both)}"


@pytest.mark.parametrize(
    ("share", "match"),
    [
        ([("a", "zz")], "not a chip"),
        ([("a", "r")], "mixes kinds"),
        ([("r", "r2")], "no scale to share"),
        ([("a",), ("a", "b")], "two share groups"),
        ("all", "must be groups"),
    ],
)
def test_bad_share_groups(share, match: str) -> None:
    chips = {"a": LOSS, "b": LOSS, "r": mc.ratio(1, 3), "r2": mc.ratio(2, 3)}
    with pytest.raises(mc.ChipError, match=match) as e:
        format_prose("{a}", share=share, **chips)
    assert e.value.fix_hint


def test_errors() -> None:
    with pytest.raises(mc.ChipError, match=r"no chip for \{lift\}"):
        format_prose("{loss} {lift}", loss=LOSS)
    with pytest.raises(mc.ChipError, match="not a chip"):
        format_prose("{n}", n=0.82)
    with pytest.raises(mc.ChipError, match="unknown format"):
        format_prose("x", format="rst")
    assert format_prose("a {not a slot} {}", loss=LOSS) == "a {not a slot} {}"


def test_lint_density_and_typed_copies() -> None:
    s = [mc.spark([1, 2, 3], unit="ms"), mc.spark([2, 3, 1], unit="ms"), mc.spark([3, 1, 2])]
    acc = mc.num(0.82, label="Accuracy")
    msgs = lint(
        "Accuracy was 0.82 ({acc}). Latency went {a}, {b} and {c}.\n\nLater {a} held.",
        {"acc": acc, "a": s[0], "b": s[1], "c": s[2]},
    )
    assert msgs == [
        "{acc} repeats the typed 0.82 beside it; delete the typed number.",
        (
            '"Latency went {a}, {b} and {c}." has 3 chips; keep one or two per sentence, '
            "or use a table."
        ),
        "Paragraph 1 has 3 spark chips ({a}, {b}, {c}); put comparable values in a table.",
    ]
    assert lint("Loss fell to {loss}, lift was {lift}.", {"loss": LOSS, "lift": LIFT}) == []
    assert lint("Accuracy {acc} beat 0.75.", {"acc": acc}) == []


def test_lint_returns_chip_warnings() -> None:
    lift = mc.ci(0.08, (0.05, 0.11))
    assert lint("Lift {lift}.", {"lift": lift}) == [f"{{lift}}: {w}" for w in lift.warnings]
    assert lift.warnings


def test_the_share_rule_is_public_and_drives_lint() -> None:
    from mintchip import directives, prose

    a = mc.dist([18.9, 19.4, 19.8, 20.1, 20.3, 20.3, 20.9, 21.6, 22.8, 47.8], unit="ms")
    b = mc.dist([30, 40, 45, 50, 55], unit="ms")
    d = prose.shared_domains({"a": a, "b": b, "n": mc.num(1)})
    assert set(d) == {"a", "b"} and d["a"] == d["b"] == mc.shared_domain(a, b)
    assert prose.shared_domains({"a": a, "b": b}, share=False) == {}
    assert directives.shared_domains([a, b]) == [d["a"], d["b"]]
    assert lint("Then {a}; later {b}.", {"a": a, "b": b}) == [], "the outlier is on the scale"
    assert lint("Then {a}; later {b}.", {"a": a, "b": b}, share=False)
