"""Per-trial availability for attack uses and d6 recharge abilities."""

from dataclasses import replace


class AttackResources:
    def __init__(
        self,
        attacks,
        spell_slots=(),
        pact_slots=(),
        spell_slot_capacity=(),
        pact_slot_capacity=(),
    ):
        self.spell_slots = dict(spell_slots)
        self.pact_slots = dict(pact_slots)
        self.maximum_spell_slots = dict(spell_slot_capacity or self.spell_slots)
        self.maximum_pact_slots = dict(pact_slot_capacity or self.pact_slots)
        # Identical profiles referenced repeatedly by a multiattack share uses.
        self.remaining = {
            attack: (1 if attack.recharge_min_roll is not None else attack.limited_uses)
            for attack in attacks
            if attack.recharge_min_roll is not None or attack.limited_uses is not None
        }

    def start_turn(self, rng):
        for attack, uses in self.remaining.items():
            if uses == 0 and attack.recharge_min_roll is not None:
                if rng.randint(1, 6) >= attack.recharge_min_roll:
                    self.remaining[attack] = 1

    def slot_for(self, attack):
        level = attack.spell_slot_level
        if not level:
            return None
        candidates = []
        for pool_name, pool in (
            ("spellcasting", self.spell_slots),
            ("pact", self.pact_slots),
        ):
            if attack.spell_slot_pool not in ("any", pool_name):
                continue
            for casting_level, count in pool.items():
                if count and (
                    casting_level == level
                    or (attack.allow_upcast and casting_level >= level)
                ):
                    candidates.append((casting_level, pool_name))
        # Lowest sufficient slot first; Pact Magic wins equal-level ties.
        return min(candidates) if candidates else None

    def available(self, attack):
        return (not self.remaining or self.remaining.get(attack, 1) > 0) and (
            not attack.spell_slot_level or self.slot_for(attack) is not None
        )

    def prepare(self, attack):
        """Resolve the current casting level without spending a resource."""
        slot = self.slot_for(attack)
        if slot is None:
            return attack
        extra_levels = slot[0] - attack.spell_slot_level
        if not extra_levels:
            return attack
        return replace(
            attack,
            damage_dice=attack.damage_dice + attack.upcast_damage_dice * extra_levels,
            spell_slot_level=slot[0],
        )

    def spend(self, attack):
        if not self.available(attack):
            raise ValueError(f"no uses remaining for {attack.name}")
        slot = self.slot_for(attack)
        if slot:
            level, pool = slot
            (self.pact_slots if pool == "pact" else self.spell_slots)[level] -= 1
        if self.remaining and attack in self.remaining:
            self.remaining[attack] -= 1

    def rest(self, kind):
        """Restore slot capacities recorded at construction; uses are encounter resources."""
        if kind not in {"short", "long"}:
            raise ValueError("rest must be short or long")
        self.pact_slots = self.maximum_pact_slots.copy()
        if kind == "long":
            self.spell_slots = self.maximum_spell_slots.copy()

    def plan(self, preferred, fallbacks, choose):
        """Reserve uses locally; real spending happens only on attempted attacks."""
        remaining = self.remaining.copy()
        sequence = []

        def available(attack):
            level = attack.spell_slot_level
            return (
                (not remaining or remaining.get(attack, 1) > 0)
                and (not level or self.slot_for(attack) is not None)
                and (not sequence or level is None)
            )

        for attack in preferred:
            if not available(attack):
                candidates = tuple(a for a in fallbacks if available(a))
                if not candidates:
                    continue
                attack = choose(candidates)
            sequence.append(attack)
            if remaining and attack in remaining:
                remaining[attack] -= 1
            if attack.spell_slot_level is not None:
                # Casting consumes the action, including for cantrips.
                # Extra Attack cannot add weapon attacks or additional casts.
                break
        return tuple(sequence)
