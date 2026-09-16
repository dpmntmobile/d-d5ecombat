"""Interactive CLI menu orchestration."""

import os

from .character_profiles import (
    build_from_roll20_with_attack,
    get_build_file_path,
    import_from_roll20,
    load_custom_build,
)
from .cli_catalog import (
    CHARACTERS_DIR,
    list_character_files,
    prompt_monster_profile,
)
from .cli_characters import build_character_presets, prompt_custom_build


def run_interactive_menu(
    input_func=input,
    output_func=print,
    target_profile=None,
):
    builds = build_character_presets()
    output_func("\nD&D 5e Combat Simulator\n")
    output_func("Choose a preset build:")
    for index, build in enumerate(builds, start=1):
        output_func(f"{index}) {build.name} - {build.description}")
    output_func("C) Create custom build")
    output_func("L) Load saved custom build")
    output_func("R) Import from Roll20 JSON")
    output_func("0) Use generic demo build")
    output_func("Q) Quit")

    choice = input_func("Choose a character [Tobias]: ").strip().lower()
    if choice in {"q", "quit", "exit"}:
        raise SystemExit(0)

    if not choice:
        selected_build = builds[0]
    elif choice in {"tobias", "t"}:
        selected_build = builds[0]
    elif choice in {"brute", "b"}:
        selected_build = builds[1]
    elif choice in {"scout", "s"}:
        selected_build = builds[2]
    elif choice in {"c", "custom", "create"}:
        selected_build = prompt_custom_build(input_func=input_func, output_func=output_func, save_after=True)
    elif choice in {"l", "load"}:
        build_name = input_func("Enter saved build name [Tobias]: ").strip() or "Tobias"
        loaded = load_custom_build(get_build_file_path(build_name))
        if loaded:
            selected_build = loaded
            output_func(f"Loaded {loaded.name}.")
        else:
            output_func(f"No saved build found for {build_name}. Using Tobias preset.")
            selected_build = builds[0]
    elif choice in {"r", "roll20", "import"}:
        # List available character files
        char_files = list_character_files()
        if char_files:
            output_func(f"\nAvailable character files ({len(char_files)} found):")
            for idx, filename in enumerate(char_files, start=1):
                output_func(f"  {idx}) {filename}")
            output_func("  0) Enter file path manually")

            file_choice = input_func("Choose a character file [1]: ").strip() or "1"
            try:
                file_idx = int(file_choice)
                if file_idx == 0:
                    roll20_file = input_func("Path to Roll20 JSON export: ").strip()
                elif 1 <= file_idx <= len(char_files):
                    roll20_file = os.path.join(CHARACTERS_DIR, char_files[file_idx - 1])
                else:
                    output_func("Invalid choice, using first character file.")
                    roll20_file = os.path.join(CHARACTERS_DIR, char_files[0])
            except ValueError:
                output_func("Invalid choice, using first character file.")
                roll20_file = os.path.join(CHARACTERS_DIR, char_files[0])
        else:
            output_func("No character files found in characters/ directory.")
            roll20_file = input_func("Path to Roll20 JSON export: ").strip()

        roll20_data = import_from_roll20(roll20_file)
        if roll20_data:
            output_func(f"Loaded {roll20_data['name']} ({roll20_data['class']}, {roll20_data['race']}, Lvl {roll20_data['level']})")
            output_func(f"AC: {roll20_data['armor_class']}, HP: {roll20_data['max_hp']}")

            # Show available attacks from Roll20
            attacks = roll20_data.get("attacks", [])
            selected_attack_name = None
            if attacks:
                output_func(f"\nAvailable attacks ({len(attacks)} found):")
                for idx, attack in enumerate(attacks, start=1):
                    output_func(f"  {idx}) {attack['name']}: +{attack['bonus']} to hit, {attack['damage_dice']} {attack['damage_type']}")

                attack_choice = input_func("Choose an attack [1]: ").strip() or "1"
                try:
                    attack_idx = int(attack_choice) - 1
                    if 0 <= attack_idx < len(attacks):
                        selected_attack = attacks[attack_idx]
                        selected_attack_name = selected_attack["name"]
                        attack_bonus = selected_attack["bonus"]
                        damage_text = selected_attack["damage_dice"]
                        damage_mod = selected_attack["damage_modifier"]

                        output_func(f"Selected: {selected_attack['name']} (+{attack_bonus}, {damage_text})")
                    else:
                        output_func("Invalid attack choice, using first attack.")
                        selected_attack = attacks[0]
                        selected_attack_name = selected_attack["name"]
                        attack_bonus = selected_attack["bonus"]
                        damage_text = selected_attack["damage_dice"]
                        damage_mod = selected_attack["damage_modifier"]
                except ValueError:
                    output_func("Invalid choice, using first attack.")
                    selected_attack = attacks[0]
                    selected_attack_name = selected_attack["name"]
                    attack_bonus = selected_attack["bonus"]
                    damage_text = selected_attack["damage_dice"]
                    damage_mod = selected_attack["damage_modifier"]
            else:
                # No attacks found, ask for manual entry
                output_func("No attacks found in Roll20 export.")
                attack_bonus = int(input_func(f"Attack bonus [STR {roll20_data['strength_mod']}]: ").strip() or roll20_data['strength_mod'])
                damage_text = input_func("Damage dice [1d8]: ").strip() or "1d8"
                damage_mod = int(input_func(f"Damage modifier [STR {roll20_data['strength_mod']}]: ").strip() or roll20_data['strength_mod'])

            equipment = input_func("Equipment (comma-separated) [none]: ").strip()
            selected_build = build_from_roll20_with_attack(
                roll20_data,
                attack_bonus,
                damage_text,
                damage_mod,
                equipment,
                selected_attack_name=selected_attack_name,
            )
            output_func(f"Imported {selected_build.name} ready to use.")
        else:
            output_func(f"Failed to load Roll20 JSON from {roll20_file}. Using Tobias preset.")
            selected_build = builds[0]
    else:
        try:
            build_index = int(choice)
        except ValueError as error:
            raise ValueError("Please choose a preset build number or name.") from error

        if build_index == 0:
            selected_build = None
        elif 1 <= build_index <= len(builds):
            selected_build = builds[build_index - 1]
        else:
            raise ValueError("Selected build is out of range.")

    if target_profile is None:
        target_profile = prompt_monster_profile(input_func, output_func)
    else:
        output_func(
            f"\nUsing enemy {target_profile.name} "
            f"(AC {target_profile.armor_class}, {target_profile.max_hp} HP)."
        )

    output_func("\nSelect a scenario:")
    output_func("1) Run default comparison")
    output_func("2) Compare attack scenarios")
    output_func("3) Compare turn plans")
    output_func("4) Compare save effects")
    output_func("5) Run all comparisons")
    output_func("6) Single combat drill")
    output_func("7) Simulate character-versus-monster duel")
    output_func("Q) Quit")

    mode_choice = input_func("Choose an option: ").strip().lower()
    if mode_choice in {"q", "quit", "exit"}:
        raise SystemExit(0)

    try:
        option_number = int(mode_choice)
    except ValueError as error:
        raise ValueError("Please enter a valid option number.") from error

    settings = {
        "mode": "compare",
        "target_hp": 20,
        "enemy_armor_class": 15,
        "enemy_initiative_bonus": 0,
        "target_save_bonus": 2,
        "armor_classes": [12, 14, 16, 18, 20],
        "trials": 10_000,
        "seed": 42,
        "selected_build": selected_build,
        "target_profile": target_profile,
    }

    if option_number not in {1, 2, 3, 4, 5, 6, 7}:
        raise ValueError("Option must be between 1 and 7.")

    if target_profile is None and option_number in {1, 2, 5, 6}:
        target_hp_value = input_func("Target HP [20]: ").strip()
        settings["target_hp"] = int(target_hp_value) if target_hp_value else 20

    if target_profile is None and option_number == 6:
        enemy_ac_value = input_func("Enemy AC [15]: ").strip()
        if enemy_ac_value:
            enemy_values = [int(value) for value in enemy_ac_value.split()]
            settings["enemy_armor_class"] = enemy_values[0]

    if target_profile is None and option_number in {1, 2, 5}:
        armor_text = input_func("Armor classes to compare [12 14 16 18 20]: ").strip()
        if armor_text:
            settings["armor_classes"] = [int(value) for value in armor_text.split()]

    if option_number in {1, 2, 3, 4, 5, 6, 7}:
        trials_value = input_func("Simulation trials [10000]: ").strip()
        settings["trials"] = int(trials_value) if trials_value else 10_000

    if option_number in {1, 2, 3, 4, 5, 6, 7}:
        seed_value = input_func("Seed [42]: ").strip()
        settings["seed"] = int(seed_value) if seed_value else 42

    settings["mode"] = {
        1: "default",
        2: "attacks",
        3: "turns",
        4: "saves",
        5: "all",
        6: "single",
        7: "duels",
    }[option_number]

    return settings
