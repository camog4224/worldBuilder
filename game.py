import json
import os
import re
from datetime import datetime, timezone

import ollama

WORLD_LORE_DIR = "world_lore"
LORE_FILE = os.path.join(WORLD_LORE_DIR, "active_lore.md")
LONG_TERM_MEMORY_FILE = os.path.join(WORLD_LORE_DIR, "long_term_memory.md")
RECENT_TURNS_FILE = os.path.join(WORLD_LORE_DIR, "recent_turns.jsonl")
LAST_RESPONSE_FILE = os.path.join(WORLD_LORE_DIR, "last_response.txt")
ARCHIVE_DIR = os.path.join(WORLD_LORE_DIR, "archive")
ARCHIVE_FILE = os.path.join(ARCHIVE_DIR, "history.jsonl")
MODEL_NAME = "llama3.1:latest"

# Ollama does not provide a portable token-counting API. Character budgets are
# conservative estimates (roughly four characters per token) and leave room
# for instructions and the narrator's response.
MAX_CONTEXT_TOKENS = 8192
RESPONSE_TOKENS = 1400
PROMPT_OVERHEAD_TOKENS = 1000
MAX_PROMPT_CHARS = (
    (MAX_CONTEXT_TOKENS - RESPONSE_TOKENS - PROMPT_OVERHEAD_TOKENS) * 4
)
RECENT_MEMORY_LIMIT_CHARS = 10000
LONG_TERM_MEMORY_LIMIT_CHARS = 6500
ARCHIVE_RETRIEVAL_LIMIT_CHARS = 3000
ARCHIVE_CATALOG_LIMIT_CHARS = 5000

os.makedirs(ARCHIVE_DIR, exist_ok=True)
os.makedirs(WORLD_LORE_DIR, exist_ok=True)


def load_file_content(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as file:
            return file.read()
    return ""


def write_file_content(filepath, content):
    with open(filepath, "w", encoding="utf-8") as file:
        file.write(content)


def append_jsonl(filepath, record):
    with open(filepath, "a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_jsonl(filepath):
    records = []
    if not os.path.exists(filepath):
        return records
    with open(filepath, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSON in {filepath} at line {line_number}"
                ) from error
    return records


def trim_text(text, limit):
    if len(text) <= limit:
        return text
    marker = "\n[Older content omitted for context safety.]"
    return text[: max(0, limit - len(marker))].rstrip() + marker


def get_recent_turns():
    return load_jsonl(RECENT_TURNS_FILE)


def format_recent_turns(turns):
    return "\n\n".join(
        f"TURN {turn['turn']}:\nPLAYER: {turn['player_action']}\n"
        f"NARRATOR: {turn['narrative']}"
        for turn in turns
    )


def initialize_game():
    if not os.path.exists(LORE_FILE):
        write_file_content(
            LORE_FILE,
            "CURRENT WORLD STATE:\n"
            "- Location: Starting Outpost\n"
            "- Time: Day 1, Dawn\n"
            "- Active Items: Iron Knife\n\n"
            "ACTIVE CONSEQUENCES:\n"
            "- You woke up at the edge of the world with no memory.\n",
        )
    if not os.path.exists(LONG_TERM_MEMORY_FILE):
        write_file_content(
            LONG_TERM_MEMORY_FILE,
            "IMPORTANT LONG-TERM FACTS:\n"
            "- The player woke up at the edge of the world with no memory.\n"
            "- The player began with an iron knife.\n",
        )
    if not os.path.exists(LAST_RESPONSE_FILE):
        write_file_content(
            LAST_RESPONSE_FILE,
            "You wake up at the edge of the world with no memory. "
            "Cold air cuts through your clothes, and an iron knife rests "
            "on the ground beside you.",
        )

    last_story = load_file_content(LAST_RESPONSE_FILE)
    if last_story:
        print("\n" + "📖" * 25)
        print("          ✨ CONTINUING YOUR ADVENTURE ✨          ")
        print("📖" * 25)
        print(f"\n{last_story.strip()}\n\n" + "=" * 50)
    print("\nClean Narrative Engine Active. Make any move you wish. Type 'exit' to save and quit.")


def archive_turn(turn):
    """Keep the original interaction immutable, even when active memory changes."""
    append_jsonl(ARCHIVE_FILE, turn)
    append_jsonl(RECENT_TURNS_FILE, turn)


def compact_old_turns():
    turns = get_recent_turns()
    recent_text = format_recent_turns(turns)
    if len(recent_text) <= RECENT_MEMORY_LIMIT_CHARS:
        return turns

    split_at = max(1, len(turns) // 2)
    old_turns = turns[:split_at]
    remaining_turns = turns[split_at:]
    old_text = format_recent_turns(old_turns)
    existing_memory = trim_text(
        load_file_content(LONG_TERM_MEMORY_FILE), LONG_TERM_MEMORY_LIMIT_CHARS
    )
    prompt = f"""
You maintain durable memory for a fantasy world.
Extract only facts that should remain true after many future turns:
important people and relationships, locations, discoveries, player choices,
items, factions, unresolved threats, and irreversible consequences.
Do not preserve atmosphere or repeated prose. Do not invent facts.
Return a concise plain-text list of facts.

EXISTING LONG-TERM MEMORY:
{existing_memory}

OLDER TURNS TO COMPRESS:
{trim_text(old_text, MAX_PROMPT_CHARS - len(existing_memory) - 2000)}
"""
    response = ollama.generate(
        model=MODEL_NAME,
        prompt=prompt,
        options={
            "temperature": 0.1,
            "num_predict": 900,
            "num_ctx": MAX_CONTEXT_TOKENS,
        },
    )
    updated_memory = trim_text(response["response"].strip(), LONG_TERM_MEMORY_LIMIT_CHARS)
    write_file_content(LONG_TERM_MEMORY_FILE, updated_memory)
    write_file_content(
        RECENT_TURNS_FILE,
        "".join(json.dumps(turn, ensure_ascii=False) + "\n" for turn in remaining_turns),
    )
    return remaining_turns


def get_archive_catalog():
    records = load_jsonl(ARCHIVE_FILE)
    catalog = "\n".join(
        f"TURN:{record['turn']} | {record['player_action'][:180]}"
        for record in records[-30:]
    )
    legacy_files = [
        name
        for name in os.listdir(ARCHIVE_DIR)
        if name.endswith(".md") or name.endswith(".txt")
    ]
    if legacy_files:
        catalog += "\nLEGACY FILES: " + ", ".join(sorted(legacy_files))
    return trim_text(catalog or "No archived turns exist.", ARCHIVE_CATALOG_LIMIT_CHARS)


def retrieve_archive_memory(player_input, active_lore, long_term_memory):
    catalog = get_archive_catalog()
    prompt = f"""
You select relevant archived memories for a game narrator.
Return ONLY one exact TURN:<number>, one exact legacy filename, or NONE.
Choose NONE unless an old event is needed to resolve the player's action.
You cannot request more context. The program will retrieve at most one bounded
archive entry and will never perform another lookup.

PLAYER ACTION:
{trim_text(player_input, 2500)}

CURRENT STATE:
{trim_text(active_lore, 4000)}

LONG-TERM MEMORY:
{trim_text(long_term_memory, 3000)}

ARCHIVE CATALOG:
{catalog}
"""
    response = ollama.generate(
        model=MODEL_NAME,
        prompt=trim_text(prompt, MAX_PROMPT_CHARS),
        options={
            "temperature": 0.0,
            "num_predict": 30,
            "num_ctx": MAX_CONTEXT_TOKENS,
        },
    )
    decision = response["response"].strip()
    turn_match = re.fullmatch(r"TURN:(\d+)", decision)
    if turn_match:
        requested_turn = int(turn_match.group(1))
        for record in load_jsonl(ARCHIVE_FILE):
            if record.get("turn") == requested_turn:
                return trim_text(
                    f"Archived turn {requested_turn}:\n"
                    f"PLAYER: {record['player_action']}\n"
                    f"NARRATOR: {record['narrative']}",
                    ARCHIVE_RETRIEVAL_LIMIT_CHARS,
                )
    legacy_files = {
        name
        for name in os.listdir(ARCHIVE_DIR)
        if name.endswith(".md") or name.endswith(".txt")
    }
    if decision in legacy_files:
        return trim_text(
            f"Archived legacy file {decision}:\n"
            + load_file_content(os.path.join(ARCHIVE_DIR, decision)),
            ARCHIVE_RETRIEVAL_LIMIT_CHARS,
        )
    return ""


def build_story_prompt(active_lore, long_term_memory, recent_turns, retrieved_memory, player_input):
    memory_sections = (
        f"CURRENT WORLD STATE:\n{trim_text(active_lore, 6500)}\n\n"
        f"LONG-TERM FACTS:\n{trim_text(long_term_memory, 5500)}\n\n"
        f"RECENT TURNS:\n{trim_text(format_recent_turns(recent_turns), 8500)}\n\n"
        f"RETRIEVED ARCHIVE MEMORY:\n{trim_text(retrieved_memory or 'None', ARCHIVE_RETRIEVAL_LIMIT_CHARS)}"
    )
    return trim_text(
        f"""GROUND TRUTH MEMORY:
{memory_sections}

PLAYER ACTION:
{trim_text(player_input, 2500)}

Describe the immediate and consequential result beautifully. Use the ground
truth memory, but do not claim that an event happened unless supported by it
or by the player's action. Output only immersive story prose.""",
        MAX_PROMPT_CHARS,
    )


def main():
    initialize_game()
    while True:
        player_input = input("\n> ")
        if player_input.lower() == "exit":
            print("Game state saved securely. Goodbye!")
            break
        if not player_input.strip():
            continue

        try:
            active_lore = load_file_content(LORE_FILE)
            recent_turns = compact_old_turns()
            # Compaction may have replaced the long-term memory file.
            long_term_memory = load_file_content(LONG_TERM_MEMORY_FILE)
            retrieved_memory = retrieve_archive_memory(
                player_input, active_lore, long_term_memory
            )
            story_response = ollama.generate(
                model=MODEL_NAME,
                system=(
                    "You are an immersive, highly descriptive fantasy text "
                    "adventure narrator. Output only pure story prose. Do not "
                    "output lists, choices, inventories, notes, or system tags."
                ),
                prompt=build_story_prompt(
                    active_lore,
                    long_term_memory,
                    recent_turns,
                    retrieved_memory,
                    player_input,
                ),
                options={
                    "temperature": 0.7,
                    "num_predict": RESPONSE_TOKENS,
                    "num_ctx": MAX_CONTEXT_TOKENS,
                },
            )
            clean_story = story_response["response"].strip()
            print(f"\n{clean_story}")
            write_file_content(LAST_RESPONSE_FILE, clean_story)

            turn_number = len(load_jsonl(ARCHIVE_FILE)) + 1
            turn = {
                "turn": turn_number,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "player_action": player_input,
                "narrative": clean_story,
            }
            archive_turn(turn)

            notes_prompt = trim_text(
                f"""Rewrite the current structured world state after this turn.
Preserve all still-valid facts and update location, time, inventory, people,
quests, and consequences. Do not write narrative prose. Do not invent facts.
Keep the result under 4500 characters.

CURRENT WORLD STATE:
{trim_text(active_lore, 6500)}

LONG-TERM FACTS:
{trim_text(long_term_memory, 4000)}

PLAYER ACTION:
{trim_text(player_input, 2500)}

NARRATIVE THAT OCCURRED:
{clean_story}
""",
                MAX_PROMPT_CHARS,
            )
            notes_response = ollama.generate(
                model=MODEL_NAME,
                prompt=notes_prompt,
                options={
                    "temperature": 0.1,
                    "num_predict": 800,
                    "num_ctx": MAX_CONTEXT_TOKENS,
                },
            )
            write_file_content(LORE_FILE, trim_text(notes_response["response"].strip(), 6500))
            compact_old_turns()
        except Exception as error:
            print(f"\n❌ Local Connection Error: {error}")
            break


if __name__ == "__main__":
    main()
