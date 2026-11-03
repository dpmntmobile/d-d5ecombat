"""Reusable party/encounter definitions and shared-initiative group battles."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .character_models import CharacterBuild
from .models import TargetProfile
from .profile_catalog import load_character_build
from .monster_profiles import load_monster_profile
from .scenario_factory import build_duel_policy_matchups


@dataclass(frozen=True)
class MonsterGroup:
    profile: TargetProfile
    count: int = 1

    def __post_init__(self):
        if isinstance(self.count, bool) or not isinstance(self.count, int):
            raise TypeError("monster count must be an integer")
        if self.count < 1:
            raise ValueError("monster count must be positive")


@dataclass(frozen=True)
class PartyBattle:
    party: tuple
    encounter: tuple

    def __post_init__(self):
        object.__setattr__(self, "party", tuple(self.party))
        object.__setattr__(self, "encounter", tuple(self.encounter))
        if not self.party or not self.encounter:
            raise ValueError(
                "a battle needs at least one character and one monster group"
            )
        if not all(isinstance(member, CharacterBuild) for member in self.party):
            raise TypeError("party must contain CharacterBuild instances")
        if not all(isinstance(group, MonsterGroup) for group in self.encounter):
            raise TypeError("encounter must contain MonsterGroup instances")
        if not all(
            isinstance(group.profile, TargetProfile) for group in self.encounter
        ):
            raise TypeError("monster groups must contain TargetProfile instances")

    @property
    def combatants(self):
        result = {}
        for index, build in enumerate(self.party):
            matchups = build_duel_policy_matchups(build, self.encounter[0].profile)
            if not matchups:
                raise ValueError("every monster must have a supported combat action")
            result[f"character:{index}"] = matchups[0].character
        for index, group in enumerate(self.encounter):
            matchups = build_duel_policy_matchups(self.party[0], group.profile)
            if not matchups:
                raise ValueError("every monster must have a supported combat action")
            member = matchups[0].monster
            for instance in range(group.count):
                result[f"monster:{index}:{instance}"] = member
        return result


@dataclass(frozen=True)
class BattleResult:
    trials: int
    party_wins: int
    encounter_wins: int
    draws: int
    total_rounds: int
    party_hp: int
    encounter_hp: int
    party_survivors: int
    encounter_survivors: int

    def report(self):
        return {
            **asdict(self),
            "party_win_rate": self.party_wins / self.trials,
            "encounter_win_rate": self.encounter_wins / self.trials,
            "draw_rate": self.draws / self.trials,
            "average_rounds": self.total_rounds / self.trials,
            "average_party_hp": self.party_hp / self.trials,
            "average_encounter_hp": self.encounter_hp / self.trials,
            "average_party_survivors": self.party_survivors / self.trials,
            "average_encounter_survivors": self.encounter_survivors / self.trials,
        }


def battle_report(battle, result, seed, max_rounds_per_trial):
    """Capture the effective composition and settings alongside trial results."""
    from . import __version__

    return {
        "result_format_version": 1,
        "application_version": __version__,
        "seed": seed,
        "max_rounds_per_trial": max_rounds_per_trial,
        "composition": {
            "party": [asdict(member) for member in battle.party],
            "encounter": [asdict(group) for group in battle.encounter],
        },
        **result.report(),
    }


def save_battle_results(report, path):
    """Export a captured run without consulting mutable desktop controls."""
    import os
    import tempfile
    from .result_export import _json_default

    content = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False,
                         default=_json_default) + "\n"
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def simulate_party_battle(
    battle, trials=1000, seed=42, max_rounds_per_trial=100, cancellation_check=None
):
    from .duel_simulation import simulate_duel

    if not isinstance(battle, PartyBattle):
        raise TypeError("battle must be a PartyBattle")
    matchup = build_duel_policy_matchups(battle.party[0], battle.encounter[0].profile)
    if not matchup:
        raise ValueError("every monster must have a supported combat action")
    return simulate_duel(
        trials,
        matchup[0],
        seed=seed,
        max_rounds_per_trial=max_rounds_per_trial,
        cancellation_check=cancellation_check,
        _battle=battle,
    )


def load_battle(path):
    """Resolve profile references relative to the battle JSON file."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"version", "party", "encounter"}:
        raise ValueError("battle requires exactly version, party, and encounter")
    if type(data["version"]) is not int or data["version"] != 1:
        raise ValueError("unsupported battle version")
    if not isinstance(data["party"], list) or not isinstance(data["encounter"], list):
        raise ValueError("party and encounter must be arrays")

    def profile_path(value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("profile paths must be non-empty strings")
        return path.parent / value

    characters = tuple(
        load_character_build(profile_path(value)) for value in data["party"]
    )
    groups = []
    for entry in data["encounter"]:
        if not isinstance(entry, dict) or set(entry) != {"monster", "count"}:
            raise ValueError("each encounter entry requires monster and count")
        groups.append(
            MonsterGroup(
                load_monster_profile(profile_path(entry["monster"])), entry["count"]
            )
        )
    return PartyBattle(characters, tuple(groups))


def save_battle(path, character_paths, monster_counts):
    """Save references without copying or modifying the source profiles."""
    import os

    path = Path(path).resolve()
    characters = list(character_paths)
    groups = list(monster_counts)
    if not characters or not groups:
        raise ValueError("select at least one character and monster")
    for _, count in groups:
        MonsterGroup(None, count)

    def reference(source):
        try:
            return os.path.relpath(Path(source).resolve(), path.parent)
        except ValueError:  # Windows profiles on another drive.
            return str(Path(source).resolve())

    data = {
        "version": 1,
        "party": [reference(p) for p in characters],
        "encounter": [{"monster": reference(p), "count": n} for p, n in groups],
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path
