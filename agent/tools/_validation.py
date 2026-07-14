"""Shared argument validation for the SQL tools (not a tool itself).

Bad taxonomy names and malformed dates are the model's most likely mistakes,
so both raise ModelRetry listing what IS valid: the ReAct loop gets one shot
at self-correcting instead of the run crashing.
"""

from datetime import date

from pydantic_ai import ModelRetry

# Full seeded range of the synthetic data; used as defaults when the model
# does not pass dates.
DATA_START = date(2026, 1, 1)
DATA_END = date(2026, 6, 30)


def parse_date(value: str | None, field: str, default: date) -> date:
    if value is None:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ModelRetry(f"{field}={value!r} is not a valid ISO date; use YYYY-MM-DD.")


def parse_month(value: str) -> tuple[date, date]:
    """'YYYY-MM' -> (first day, first day of next month)."""
    try:
        year, month = map(int, value.split("-"))
        start = date(year, month, 1)
    except (ValueError, AttributeError):
        raise ModelRetry(f"month={value!r} is not valid; use YYYY-MM, e.g. '2026-05'.")
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


async def resolve_taxonomy(
    conn,
    category: str | None = None,
    subcategory: str | None = None,
    spend_type: str | None = None,
) -> tuple[int | None, int | None, int | None]:
    """Case-insensitive name -> id resolution against the lookup tables.

    Unknown names raise ModelRetry carrying the valid options, scoped to the
    parent when one was given (e.g. subcategories of the chosen category).
    """
    cat_id = sub_id = spend_id = None

    if category is not None:
        rows = await conn.fetch("SELECT id, name FROM categories")
        by_name = {r["name"].lower(): r for r in rows}
        hit = by_name.get(category.lower())
        if hit is None:
            names = ", ".join(sorted(r["name"] for r in rows))
            raise ModelRetry(f"Unknown category {category!r}. Valid categories: {names}.")
        cat_id = hit["id"]

    if subcategory is not None:
        if cat_id is not None:
            rows = await conn.fetch(
                "SELECT id, name, category_id FROM subcategories WHERE category_id = $1", cat_id
            )
        else:
            rows = await conn.fetch("SELECT id, name, category_id FROM subcategories")
        by_name = {r["name"].lower(): r for r in rows}
        hit = by_name.get(subcategory.lower())
        if hit is None:
            names = ", ".join(sorted(r["name"] for r in rows))
            scope = f" under category {category!r}" if category else ""
            raise ModelRetry(f"Unknown subcategory {subcategory!r}{scope}. Valid: {names}.")
        sub_id = hit["id"]
        cat_id = cat_id or hit["category_id"]

    if spend_type is not None:
        if sub_id is not None:
            rows = await conn.fetch(
                "SELECT id, name, subcategory_id FROM spend_types WHERE subcategory_id = $1", sub_id
            )
        else:
            rows = await conn.fetch("SELECT id, name, subcategory_id FROM spend_types")
        matches = [r for r in rows if r["name"].lower() == spend_type.lower()]
        if not matches:
            names = ", ".join(sorted({r["name"] for r in rows}))
            scope = f" under subcategory {subcategory!r}" if subcategory else ""
            raise ModelRetry(f"Unknown spend_type {spend_type!r}{scope}. Valid: {names}.")
        if len(matches) > 1:
            raise ModelRetry(
                f"spend_type {spend_type!r} exists under multiple subcategories; "
                "pass subcategory as well to disambiguate."
            )
        spend_id = matches[0]["id"]
        sub_id = sub_id or matches[0]["subcategory_id"]

    return cat_id, sub_id, spend_id
