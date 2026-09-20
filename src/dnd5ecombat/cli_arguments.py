"""Command-line argument definitions for the console application."""

import argparse
from dataclasses import asdict

from .scenario_persistence import load_scenario


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare simple D&D 5e combat options with seeded simulations."
    )
    parser.add_argument("--scenario", help="Load encounter settings from a JSON file.")
    parser.add_argument("--save-scenario", metavar="FILE",
                        help="Save encounter settings to JSON and exit without simulating.")
    parser.add_argument(
        "--initiative-bonus",
        type=int,
        default=None,
        help="Character initiative bonus override used in the initiative sequence.",
    )
    parser.add_argument(
        "--enemy-initiative-bonus",
        type=int,
        default=None,
        help="Initiative bonus override for the opposing combatant.",
    )
    parser.add_argument(
        "--target-save-bonus",
        type=int,
        default=2,
        help="Saving throw bonus for targets of imported save-based spells.",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=10_000,
        help="Number of trials to simulate for each comparison (default: 10000).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Worker processes for independent simulation jobs (default: 1).",
    )
    parser.add_argument(
        "--include-advantage",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Add an advantaged variant of each attack to the comparison.",
    )
    parser.add_argument(
        "--include-disadvantage",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Add a disadvantaged variant of each attack to the comparison.",
    )
    parser.add_argument(
        "--duels",
        action="store_true",
        help="Simulate two-sided duels against monster profiles.",
    )
    parser.add_argument(
        "--starting-distance-feet", type=int, default=None,
        help="Enable duel positioning at this distance in feet (default: abstract).",
    )
    parser.add_argument(
        "--character-speed-feet", type=int, default=30,
        help="Character movement per duel turn in feet (default: 30).",
    )
    parser.add_argument("--abstract-positioning", dest="starting_distance_feet",
                        action="store_const", const=None,
                        help="Disable distance and movement, including a scenario's distance.")
    parser.add_argument(
        "--monster-speed-feet", type=int, default=30,
        help="Monster movement per duel turn in feet (default: 30).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed used for deterministic simulation results.",
    )
    parser.add_argument(
        "--target-hp",
        type=int,
        default=20,
        help="Target hit points used for the attack comparison sweep.",
    )
    parser.add_argument(
        "--armor-classes",
        type=int,
        nargs="+",
        default=[12, 14, 16, 18, 20],
        help="Armor classes to compare, e.g. --armor-classes 12 14 16 18 20.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Start the interactive, prompt-based combat comparison menu.",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Start the optional PySide6 desktop interface.",
    )
    parser.add_argument(
        "--character-file",
        default=None,
        help="Path to a Roll20 JSON character file to load for the simulation.",
    )
    parser.add_argument(
        "--target-file",
        "--monster-file",
        dest="target_file",
        default=None,
        help="Path to a monster JSON profile used by the simulations.",
    )
    for side in ("character", "monster"):
        parser.add_argument(f"--{side}-ally-near-target", action=argparse.BooleanOptionalAction, default=False,
                            help="Assume an active ally within 5 feet of the opponent for Pack Tactics/Sneak Attack.")
        parser.add_argument(f"--{side}-can-hide", action=argparse.BooleanOptionalAction, default=False,
                            help="Assume suitable concealment for Nimble Escape Hide attempts.")
    parser.add_argument("--rest-before-duel", choices=("none", "short", "long"), default="none",
                        help="Recover slot capacities before each duel trial.")
    arguments = parser.parse_args(argv)
    if (arguments.scenario or arguments.save_scenario) and (arguments.gui or arguments.interactive):
        parser.error("Scenario options require non-interactive CLI mode; use Load/Save scenario in the GUI.")
    if arguments.scenario:
        try:
            settings = load_scenario(arguments.scenario)
        except (OSError, ValueError, TypeError) as error:
            parser.error(str(error))
        parser.set_defaults(**asdict(settings))
        arguments = parser.parse_args(argv)
    return arguments
