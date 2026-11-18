"""Numbers of the built-in example project in the comparison table."""

from decimal import Decimal

from procnorm.calc import compare
from procnorm.example import EXAMPLE_FILE
from procnorm.project import load_file


def test_example_final_skipped_checks():
    project, _ = load_file(EXAMPLE_FILE)
    rows = compare(project).rows
    final = {r.code: r.slices[-1].total for r in rows}
    assert final == {
        "T1": Decimal(0),
        "T2": Decimal(0),
        "T3": Decimal(11),
        "T4": Decimal(0),
    }
