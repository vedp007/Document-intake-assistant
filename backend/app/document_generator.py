"""
Document generator for the Document Intake Assistant.

Generates a plain-text draft Personal Wishes Document from the current
PersonalWishesState. The document is intentionally simple and clearly
labelled as fictional/not legal advice.
"""
from __future__ import annotations

from .models import PersonalWishesState

_DIVIDER = "─" * 52


def generate_document(state: PersonalWishesState) -> str:
    """
    Render a Personal Wishes Document draft from the current state.

    Fields that are not yet known are shown as "Not yet provided" so
    the evaluator can see exactly what information is still outstanding.
    """
    lines: list[str] = [
        _DIVIDER,
        "",
        "  ⚠  FICTIONAL — NOT LEGAL ADVICE  ⚠",
        "",
        "        PERSONAL WISHES DOCUMENT",
        "           (Draft — for review only)",
        "",
        _DIVIDER,
        "",
    ]

    # Full name
    lines += [
        "Name:",
        f"  {state.full_name or 'Not yet provided'}",
        "",
    ]

    # Home address
    lines += [
        "Home Address:",
        f"  {state.home_address or 'Not yet provided'}",
        "",
    ]

    # Worldwide assets
    if state.covers_worldwide_assets is True:
        asset_scope = "Yes — worldwide"
    elif state.covers_worldwide_assets is False:
        asset_scope = "No — not worldwide"
    else:
        asset_scope = "Not yet provided"
    lines += [
        "Worldwide Assets:",
        f"  {asset_scope}",
        "",
    ]

    # Children
    if state.has_children is True:
        if state.children_names:
            lines += [
                "Children:",
                *[f"  {n}" for n in state.children_names],
                "",
            ]
        else:
            lines += [
                "Children:",
                "  Yes (names not yet provided)",
                "",
            ]
    elif state.has_children is False:
        lines += [
            "Children:",
            "  None",
            "",
        ]
    else:
        lines += [
            "Children:",
            "  Not yet provided",
            "",
        ]

    # Executor
    if state.executor:
        exec_name = state.executor.name or "Not yet provided"
        exec_rel = state.executor.relationship or "Not yet provided"
        lines += [
            "Executor:",
            f"  Name:         {exec_name}",
            f"  Relationship: {exec_rel}",
            "",
        ]
    else:
        lines += [
            "Executor:",
            "  Not yet provided",
            "",
        ]

    # Specific gifts
    if state.specific_gifts is None:
        lines += [
            "Specific Gifts:",
            "  Not yet provided",
            "",
        ]
    elif state.specific_gifts == []:
        lines += [
            "Specific Gifts:",
            "  None specified.",
            "",
        ]
    else:
        lines.append("Specific Gifts:")
        for gift in state.specific_gifts:
            lines.append(f"  • {gift.description} → {gift.recipient}")
        lines.append("")

    # Additional wishes
    lines += [
        "Additional Wishes:",
        f"  {state.additional_wishes or 'None recorded'}",
        "",
    ]

    lines += [
        _DIVIDER,
        "",
        "  This document is a fictional specimen generated",
        "  by an automated intake tool. It has no legal",
        "  standing and must not be relied upon as advice.",
        "",
        _DIVIDER,
    ]

    return "\n".join(lines)
