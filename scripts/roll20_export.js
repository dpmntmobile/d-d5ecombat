/*
 * D&D 5e Combat Simulator - Roll20 character exporter
 *
 * Install this as a Roll20 Mod (API) script. In the Roll20 chat, run:
 *
 *     !exportjson CHARACTER_ID
 *
 * Copy everything between the START and END markers from the Mod Console into
 * a .json file. The simulator intentionally treats Roll20 as the source of
 * truth for characters.
 */

var DND5E_EXPORT_COMMAND = "!exportjson";
var DND5E_EXPORT_VERSION = 2;

function dnd5eExportValue(attribute) {
    var value = { current: attribute.get("current") };
    var maximum = attribute.get("max");

    if (maximum !== "" && maximum !== null && maximum !== undefined) {
        value.max = maximum;
    }

    return value;
}

function dnd5eHasValue(value) {
    return value !== "" && value !== null && value !== undefined;
}

function dnd5eIsGeneratedRoll(name, current) {
    var text = String(current);

    return name.endsWith("_roll") ||
        name.startsWith("roll_") ||
        text.indexOf("^{") !== -1 ||
        text.indexOf("@{wtype}") !== -1;
}

function dnd5eStoreAttribute(characterData, name, value) {
    if (name.startsWith("repeating_attack_")) {
        if (!dnd5eIsGeneratedRoll(name, value.current)) {
            characterData.attacks_and_spellcasting[name] = value;
        }
        return;
    }

    // Traits contain racial traits, class features, feats, and fighting styles.
    if (name.startsWith("repeating_traits_")) {
        characterData.traits_and_features[name] = value;
        return;
    }

    if (name.startsWith("repeating_inventory_")) {
        characterData.inventory[name] = value;
        return;
    }

    if (name.startsWith("repeating_resource_")) {
        characterData.resources[name] = value;
        return;
    }

    if (dnd5eIsGeneratedRoll(name, value.current)) {
        return;
    }

    if (name.match(/^(strength|dexterity|constitution|intelligence|wisdom|charisma)(_base|_mod|_bonus)?$/)) {
        characterData.stats[name] = value;
        return;
    }

    if (name.match(/^(acrobatics|animal_handling|arcana|athletics|deception|history|insight|intimidation|investigation|medicine|nature|perception|performance|persuasion|religion|sleight_of_hand|stealth|survival)(_bonus|_prof|_type)?$/)) {
        characterData.skills[name] = value;
        return;
    }

    if (name.match(/^(hp|hp_max|level|class|subclass|race|experience|pb|ac|initiative_bonus|speed)$/)) {
        characterData.hp_and_level[name] = value;
        return;
    }

    // Keep unknown repeating sections separate. This makes the export
    // future-proof without mixing them into ordinary sheet attributes.
    if (name.startsWith("repeating_")) {
        characterData.other_repeating_attributes[name] = value;
        return;
    }

    if (name !== "appliedUpdates") {
        characterData.other_attributes[name] = value;
    }
}

on("chat:message", function (message) {
    if (message.type !== "api" || message.content.indexOf(DND5E_EXPORT_COMMAND) !== 0) {
        return;
    }

    try {
        var characterId = message.content
            .replace(DND5E_EXPORT_COMMAND, "")
            .trim();
        var character = getObj("character", characterId);

        if (!character) {
            log("ERROR: Character not found. Use !exportjson CHARACTER_ID");
            return;
        }

        var characterData = {
            export_metadata: {
                format: "dnd5ecombat-roll20",
                version: DND5E_EXPORT_VERSION
            },
            name: character.get("name"),
            character_id: characterId,
            stats: {},
            skills: {},
            hp_and_level: {},
            attacks_and_spellcasting: {},
            traits_and_features: {},
            inventory: {},
            resources: {},
            other_repeating_attributes: {},
            other_attributes: {}
        };

        var attributes = findObjs({
            type: "attribute",
            characterid: characterId
        });

        attributes.forEach(function (attribute) {
            var name = attribute.get("name");
            var current = attribute.get("current");

            if (!dnd5eHasValue(current)) {
                return;
            }

            if (name.startsWith("kingdom_") ||
                    name.startsWith("army_") ||
                    name.indexOf("kingmaker") !== -1) {
                return;
            }

            dnd5eStoreAttribute(
                characterData,
                name,
                dnd5eExportValue(attribute)
            );
        });

        var jsonText = JSON.stringify(characterData, null, 2);

        log("--- START DND5E COMBAT EXPORT ---");
        log(jsonText);
        log("--- END DND5E COMBAT EXPORT ---");

        sendChat(
            "Exporter",
            "/w gm Character JSON is ready in the Mod Console. " +
                "Copy the text between the START and END markers."
        );
    } catch (error) {
        log("EXPORT ERROR: " + error.message);
    }
});
