"""Tests for the persona slot + validation backend."""

import importlib


def _reload():
    import database
    import accounts
    import personas
    importlib.reload(database)
    importlib.reload(accounts)
    importlib.reload(personas)
    return database, accounts, personas


def test_default_slots_validate():
    _, _, personas = _reload()
    slots = personas.default_slots()
    result = personas.validate_slots(slots, 20_000)
    assert result.ok, result.errors


def test_balance_bounds_enforced():
    _, _, personas = _reload()
    slots = personas.default_slots()
    assert not personas.validate_slots(slots, personas.MIN_BALANCE - 1).ok
    assert not personas.validate_slots(slots, personas.MAX_BALANCE + 1).ok
    assert personas.validate_slots(slots, personas.MIN_BALANCE).ok


def test_duplicate_name_blocks_launch():
    _, _, personas = _reload()
    slots = personas.default_slots()
    slots[1] = personas.PersonaSlot(
        name="Warren", lastname="Twin", model_name="gpt-4o-mini",
        strategy="x" * 60, is_custom=True,
    )
    result = personas.validate_slots(slots, 20_000)
    assert not result.ok
    assert any("duplicate" in e.lower() for e in result.errors)


def test_colon_in_name_blocks_launch():
    _, _, personas = _reload()
    slots = personas.default_slots()
    slots[0] = personas.PersonaSlot(
        name="bad:name", lastname="Hacker", model_name="gpt-4o-mini",
        strategy="y" * 60, is_custom=True,
    )
    result = personas.validate_slots(slots, 20_000)
    assert not result.ok


def test_short_custom_strategy_is_warning_not_error():
    _, _, personas = _reload()
    slots = personas.default_slots()
    slots[0] = personas.PersonaSlot(
        name="Lisa", lastname="Quant", model_name="gpt-4o-mini",
        strategy="be aggressive", is_custom=True,
    )
    result = personas.validate_slots(slots, 20_000)
    assert result.ok
    assert any("short" in w for w in result.warnings)


def test_start_session_resets_all_four():
    _, accounts, personas = _reload()
    slots = personas.default_slots()
    personas.start_session("phase2-test", slots, initial_balance=42_000)
    for slot in slots:
        acc = accounts.Account.get(slot.name, "phase2-test")
        assert acc.balance == 42_000
        assert acc.strategy.strip() == slot.strategy.strip()
