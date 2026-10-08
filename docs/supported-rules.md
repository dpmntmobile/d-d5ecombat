# Supported simulation rules

This describes the current source implementation, including the local spell
extension to version 0.4.0. The project models a selected subset of 2014-style
D&D combat. It is not a complete rules adjudicator, a 2024 rules mode, or an
optimal-play solver. The behavior below describes the software, rather than
making claims about every tabletop rule.

## Simulation modes

| Mode | What it answers | Important scope |
| --- | --- | --- |
| Attacks | Repeated attacks needed to reach zero HP; hit/critical chance and expected damage | One attacker and passive target; no duel turn state or spell-resource depletion. |
| Turns | Repeated selected attack plans needed to reach zero HP | Ordered attacks and first-hit bonus damage; not two-sided tactical combat. |
| Saves | Repeated damaging save actions needed to reach zero HP | Save success can cause half or no damage; no resource depletion or ongoing spell riders. |
| Duels | Win rate, combat length, remaining HP, and initiative outcomes | Two combatants take turns, spend resources, move when positioning is enabled, and apply supported conditions/spells. |

Roster comparisons run multiple independent pairings, not a party encounter.
Each trial resets HP, resources, and conditions. A round limit can end an
unfinished duel without a winner. Seeded Monte Carlo estimates include sampling
uncertainty; exact attack analytics apply to the attack model, not the entire duel.

## Attacks, saves, and turns

Attacks resolve a d20 against AC, natural-one misses, natural-twenty criticals,
advantage/disadvantage cancellation, damage dice and modifiers, and damage-type
defenses. Criticals double damage dice. Eligible Great Weapon Fighting mappings
reroll each damage die showing 1 or 2 once. Saving throws use the recorded bonus
and DC, with half damage rounded down when specified. Conditions can modify or
automatically fail supported saves in duels.

Duels support explicit Extra Attack/multiattack, action and bonus-action attack
plans, mixed save/attack actions, first-hit damage riders, limited uses, recharge,
Spellcasting and Pact Magic pools, upcasting, and pre-duel rests. Spending and
selection use the lowest sufficient slot, preferring Pact Magic on equal
levels. A spell action replaces the Attack action. Bonus-action spell
restrictions constrain other spells on that turn. Reactions refresh at the
start of the reacting combatant's turn.

Action selection compares immediate expected damage, with bounded estimates
for healing, buffs, and Vicious Mockery. It does not optimize future slot use or
search every legal sequence. User-selected encounter assumptions affect rider
eligibility and tactical traits.

## Positioning and traits

Optional starting distance, speed, reach, normal range, and long range determine
movement, Dash, in-range attacks, and long-range disadvantage. The battlefield
is one separation distance, without terrain, cover, elevation, or a grid.
Abstract duels use melee/ranged approximations for distance-dependent conditions.

| Trait | Implemented subset |
| --- | --- |
| Undead Fortitude | Constitution save to remain at 1 HP; radiant damage and critical hits bypass it. |
| Pack Tactics | Advantage when the side's `ally_near_target` assumption is enabled. The ally takes no turns. |
| Aggressive | An available bonus action can add approach movement when needed. |
| Nimble Escape | Bonus-action Disengage for ranged repositioning, or Hide with the `can_hide` assumption, Stealth, and opposing passive Perception. |
| Sneak Attack | Explicit first-hit dice and eligible attack indices, with advantage or the configured nearby-ally route. |

## Conditions

Attack riders apply supported conditions on failed saves, respecting condition
immunities and excluded creature tags. Optional durations count the affected
combatant's turns; repeat saves occur at the end of those turns. Independent
sources keep independent timers, but modifiers do not stack. Reapplying the same
source refreshes it. Trials start without active conditions.

| Condition | Implemented subset in duels |
| --- | --- |
| Prone | Attack disadvantage; advantage for attackers within 5 feet and disadvantage farther away; standing costs movement. |
| Poisoned | Attack disadvantage; also affects the supported Hide check/passive Perception handling. |
| Restrained | Prevents movement, imposes attack disadvantage and Dexterity-save disadvantage, grants opposing attack advantage. |
| Stunned | Prevents actions/movement, grants opposing advantage, automatically fails Strength/Dexterity saves. |
| Incapacitated | Prevents actions and reactions; ends concentration; ordinary movement remains possible. |
| Paralyzed | Stunned modifiers, plus hits within 5 feet are critical. |
| Invisible | Attack advantage, opposing attack disadvantage, and visibility restrictions for supported spells; illumination suppresses its modeled benefits. |
| Deafened | Automatic save success against the supported Vicious Mockery and Dissonant Whispers effects. |

These last two conditions are model/rider support, not a general sensory system
or an implementation of every spell that creates invisibility or deafness.

## Explicit duel spells

Generic imported attack-roll and damaging save spells use their recorded dice,
save, range, and resources. Free text does not automatically create secondary
effects. These named spells have additional explicit behavior:

| Spell | Implemented behavior |
| --- | --- |
| Hellish Rebuke | Spend a reaction and slot after positive damage from a visible, in-range opponent; resolve fire damage before subsequent attacks. |
| Vicious Mockery | Failed save gives disadvantage on the next attack attempt, expiring at the end of the target's next turn. Requires a visible target; deafened targets automatically succeed. |
| Mind Sliver | Failed save subtracts 1d4 from the next supported save, including concentration; expires at the end of the caster's next turn and does not stack. Requires a visible target. |
| Dissonant Whispers | Failed save spends the target's available reaction to flee; with positioning, increases separation by eligible movement. Deafened targets automatically succeed. |
| Cure Wounds | Action and slot for self-healing, capped at maximum HP; upcasting adds healing dice. Policy considers it at half HP or below and excludes undead/constructs. |
| Faerie Fire | Action and slot; failed Dexterity save grants advantage against the target while concentration lasts. Current policy skips hidden or out-of-range targets. |
| Bless | Action and slot to concentrate on self only; adds 1d4 to attack rolls and supported saving throws. |
| Misty Step | Bonus action to teleport up to 30 feet when the policy can reach its selected attack range or escape close-range shooting disadvantage. Requires positioning and a compatible action plan. |

Concentration for Bless and Faerie Fire ends on death, incapacitation,
replacement, duration expiry, or a failed Constitution save after positive
damage (DC `max(10, damage // 2)`, after defenses). Defaults last ten caster
turns, with expiration checked at the start of a caster turn. Support action
spells replace the selected attack plan, including its bonus attacks.

Dissonant Whispers has a narrow opportunity-attack implementation: fleeing out
of the caster's melee reach can trigger one available non-spell melee attack,
spending the caster's reaction. It does not implement general opportunity
attacks, ally attacks, hazardous-path choices, or terrain. Without positioning,
the target's reaction can be spent but no distance change is represented.

The Roll20 support mapper recognizes Fey Touched and assigns a free Misty Step
cast. It assigns a free supported first-level choice only when the export has
one unambiguous eligible enchantment/divination spell without a prepared field.
Free casts precede slots and recover on a long rest. Ambiguous exports do not
justify guessing the chosen spell.

## Limits when interpreting results

The model does not implement area targeting, ally healing/buffs, general spell
components, arbitrary concentration effects, a complete perception/hearing
system, general retreat/opportunity attacks, legendary/lair actions, or arbitrary
free-text prerequisites. It stops combat at zero HP rather than simulating death
saves. Support heuristics can undervalue defensive or future benefits.

Preserved Roll20 traits and spells may lack mechanics. Review the profile's
`unmodeled_traits` and `unmodeled_effects`, which are reported with duel results.
Use [profile formats](profile-formats.md) to identify the explicit fields, and
the [README](../README.md) for scenario settings, command options, result
metadata, and more detailed tactical examples.
