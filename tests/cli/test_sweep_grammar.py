"""The `--vary` grammar — specs/sweep-and-review R1.2, R1.3, R1.4, R1.6."""

from __future__ import annotations

import pytest

from ssc.cli import sweep
from ssc.cli.errors import UsageError


# R1.3 — an explicit list.
def test_a_list_keeps_its_order_and_its_values() -> None:
    varied = sweep.parse_vary("mode=flood,global")
    assert varied.name == "mode"
    assert varied.values == ("flood", "global")


def test_a_list_of_one_is_a_list() -> None:
    assert sweep.parse_vary("tol=60").values == ("60",)


def test_surrounding_space_is_not_part_of_a_value() -> None:
    assert sweep.parse_vary(" tol = 40, 60 ").values == ("40", "60")


def test_an_empty_value_is_refused_rather_than_dropped() -> None:
    with pytest.raises(UsageError) as refused:
        sweep.parse_vary("mode=flood,,global")
    assert refused.value.code == "invalid-vary"


def test_a_repeated_value_is_refused() -> None:
    with pytest.raises(UsageError) as refused:
        sweep.parse_vary("tol=60,60")
    assert refused.value.code == "invalid-vary"


# R1.6 — the shape has to be a parameter and its values.
@pytest.mark.parametrize("written", ["tol", "=60", "", "  =  "])
def test_something_that_is_not_name_equals_values_is_refused(written: str) -> None:
    with pytest.raises(UsageError) as refused:
        sweep.parse_vary(written)
    assert refused.value.code == "invalid-vary"


# R1.3 — first..last:step.
def test_a_whole_range_is_inclusive_of_its_last_point() -> None:
    assert sweep.parse_vary("tol=40..80:20").values == ("40", "60", "80")


def test_a_range_stops_before_a_last_point_the_step_does_not_land_on() -> None:
    assert sweep.parse_vary("tol=40..85:20").values == ("40", "60", "80")


def test_a_fractional_range_does_not_accumulate_float_drift() -> None:
    # Accumulating 0.1 lands on 0.30000000000000004, which would become a directory name.
    assert sweep.parse_vary("scale=0.1..0.4:0.1").values == ("0.1", "0.2", "0.3", "0.4")


def test_a_descending_range_walks_downwards() -> None:
    assert sweep.parse_vary("tol=80..40:-20").values == ("80", "60", "40")


def test_a_step_of_zero_is_refused() -> None:
    with pytest.raises(UsageError) as refused:
        sweep.parse_vary("tol=40..80:0")
    assert refused.value.code == "invalid-vary"


def test_a_step_pointing_away_from_the_last_point_is_refused() -> None:
    with pytest.raises(UsageError) as refused:
        sweep.parse_vary("tol=40..80:-20")
    assert refused.value.code == "invalid-vary"


def test_a_range_of_too_many_points_is_refused_without_building_it() -> None:
    with pytest.raises(UsageError) as refused:
        sweep.parse_vary("tol=0..1000000:1")
    assert refused.value.code == "invalid-vary"


def test_a_non_number_in_a_range_is_refused() -> None:
    with pytest.raises(UsageError) as refused:
        sweep.parse_vary("tol=a..b:c")
    assert refused.value.code == "invalid-vary"


# R1.2 — the cross product.
def test_one_parameter_expands_to_one_point_per_value() -> None:
    points = sweep.expand([sweep.Vary("tol", ("40", "60"))])
    assert [point.values for point in points] == [{"tol": "40"}, {"tol": "60"}]
    assert [point.index for point in points] == [0, 1]


def test_the_first_parameter_varies_slowest() -> None:
    points = sweep.expand(
        [sweep.Vary("tol", ("40", "60")), sweep.Vary("mode", ("flood", "global"))]
    )
    assert [point.values for point in points] == [
        {"tol": "40", "mode": "flood"},
        {"tol": "40", "mode": "global"},
        {"tol": "60", "mode": "flood"},
        {"tol": "60", "mode": "global"},
    ]


def test_every_point_is_numbered_from_zero() -> None:
    points = sweep.expand([sweep.Vary("a", ("1", "2", "3")), sweep.Vary("b", ("x", "y"))])
    assert [point.index for point in points] == [0, 1, 2, 3, 4, 5]


def test_a_point_labels_itself_with_its_parameters() -> None:
    (point,) = sweep.expand([sweep.Vary("tol", ("60",))])
    assert point.label == "tol-60"


# R1.4 — the ceiling, and it is checked before the product is built.
def test_a_product_over_the_ceiling_is_refused() -> None:
    with pytest.raises(UsageError) as refused:
        sweep.expand(
            [
                sweep.Vary("a", tuple(str(n) for n in range(9))),
                sweep.Vary("b", tuple(str(n) for n in range(9))),
            ]
        )
    assert refused.value.code == "too-many-variants"
    assert "81" in refused.value.message


def test_a_product_exactly_at_the_ceiling_is_allowed() -> None:
    points = sweep.expand(
        [
            sweep.Vary("a", tuple(str(n) for n in range(8))),
            sweep.Vary("b", tuple(str(n) for n in range(8))),
        ]
    )
    assert len(points) == sweep.MAX_VARIANTS


def test_varying_nothing_is_refused() -> None:
    with pytest.raises(UsageError) as refused:
        sweep.expand([])
    assert refused.value.code == "no-vary"


def test_the_same_parameter_varied_twice_is_refused() -> None:
    with pytest.raises(UsageError) as refused:
        sweep.expand([sweep.Vary("tol", ("40",)), sweep.Vary("tol", ("60",))])
    assert refused.value.code == "invalid-vary"
