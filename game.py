import os
import re
import ollama

LORE_FILE = "world_lore/active_lore.md"
LAST_RESPONSE_FILE = "world_lore/last_response.txt"
ARCHIVE_DIR = "world_lore/archive"
MODEL_NAME = "llama3.1:latest"  # Works best with llama3.2, llama3, or qwen2.5

# Ensure directories exist
os.makedirs(ARCHIVE_DIR, exist_ok=True)
os.makedirs("world_lore", exist_ok=True)

def load_file_content(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def write_file_content(filepath, content):
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

def get_archived_files_list():
    return [f for f in os.listdir(ARCHIVE_DIR) if f.endswith(".md") or f.endswith(".txt")]

def initialize_game():
    """Initializes files and boots up your last session's text response verbatim."""
    if not os.path.exists(LORE_FILE):
        initial_lore = (
            "CURRENT CONTEXT:\n"
            "- Location: Starting Outpost\n"
            "- Time: Day 1, Dawn\n"
            "- Active Items: [Iron Knife]\n\n"
            "ACTIVE TIMELINE:\n"
            "- You woke up at the edge of the world with no memory.\n"
        )
        write_file_content(LORE_FILE, initial_lore)
        
    if not os.path.exists(LAST_RESPONSE_FILE):
        initial_story = "You wake up at the edge of the world with no memory. Cold air cuts through your clothes, and an iron knife rests on the ground beside you."
        write_file_content(LAST_RESPONSE_FILE, initial_story)

    last_story = load_file_content(LAST_RESPONSE_FILE)
    if last_story:
        print("\n" + "📖" * 25)
        print("          ✨ CONTINUING YOUR ADVENTURE ✨          ")
        print("📖" * 25)
        print(f"\n{last_story.strip()}")
        print("\n" + "="*50)
    
    print("\nClean Narrative Engine Active. Make any move you wish. Type 'exit' to save and quit.")

def main():
    initialize_game()

    while True:
        player_input = input("\n> ")
        if player_input.lower() == 'exit':
            print("Game state saved securely. Goodbye!")
            break

        if not player_input.strip():
            continue

        active_lore = load_file_content(LORE_FILE)
        available_archives = get_archived_files_list()

        # --- PASS 1: AUTONOMOUS ARCHIVE READ CHECK ---
        memory_prompt = f"""
        You are the mental logic center of a Game Master. 
        The player wants to do this: "{player_input}"
        
        Here is your current active summary notes file:
        {active_lore}

        You have these deep-history archive log files stored on disk: {available_archives}

        Task: Decide if you need to read the contents of ANY deep archive files to handle the player's input correctly.
        Reply with ONLY the filename (e.g., history_log_1.md) or strictly the word: NONE.
        """

        try:
            mem_response = ollama.generate(model=MODEL_NAME, prompt=memory_prompt, options={"temperature": 0.0})
            decision = mem_response['response'].strip()

            requested_file = None
            for arch_file in available_archives:
                if arch_file in decision:
                    requested_file = arch_file
                    break

            injected_memory = ""
            if requested_file and requested_file in available_archives:
                injected_memory = f"\n\n[RETRIEVED DEEP MEMORY FROM ARCHIVE {requested_file}]:\n" + load_file_content(os.path.join(ARCHIVE_DIR, requested_file))

            # =================================================================
            # PASS 2: THE NARRATOR (Generates pure storytelling first)
            # =================================================================
            story_system_prompt = (
                "You are an immersive, highly description-rich fantasy text adventure narrator.\n"
                "Your job is to look at the ground truth world notes and output ONLY pure creative story prose "
                "describing the vivid physical result of the player's action.\n"
                "Do not display lists, choices, brackets, inventories, notes, or system tags. "
                "Output nothing but the story narrative."
            )

            story_user_prompt = f"""
            GROUND TRUTH WORLD LOGS:
            {active_lore}
            {injected_memory}

            PLAYER ACTION DETAILED:
            "{player_input}"

            Task: Describe the narrative outcome beautifully based on the logs. Keep your prose fluid and open-ended.
            """

            story_response = ollama.generate(
                model=MODEL_NAME, 
                system=story_system_prompt, 
                prompt=story_user_prompt,
                options={"temperature": 0.7}
            )
            
            clean_story = story_response['response'].strip()

            # Print your clean narrative right away and cache it for startup
            print(f"\n{clean_story}")
            write_file_content(LAST_RESPONSE_FILE, clean_story)

            # =================================================================
            # PASS 3: THE NOTE-TAKER (Updates files silently AFTER the fact)
            # =================================================================
            notes_system_prompt = (
                "You are an administrative backend tracking log system for a text adventure.\n"
                "Your task is to take the old world notes, look at what the player did, look at the story text "
                "that just occurred, and rewrite the entire notes text file to incorporate everything that just happened.\n"
                "Keep tracking tags like context, location, inventory, and your timeline history up to date.\n"
                "Output ONLY the plain text notes file structure. Do not tell a story or talk out of character."
            )

            notes_user_prompt = f"""
            OLD LOREBOOK NOTES ON DISK:
            {active_lore}

            WHAT THE PLAYER DID:
            "{player_input}"

            WHAT ACTUALLY HAPPENED IN RESPONSE (THE STORY):
            "{clean_story}"

            Task: Rewrite and update the notes file completely to record this turn's events and changes.
            """

            notes_response = ollama.generate(
                model=MODEL_NAME, 
                system=notes_system_prompt, 
                prompt=notes_user_prompt,
                options={"temperature": 0.1}  # Low temperature for precise record-keeping
            )
            
            # Instantly overwrite the background file with the fully informed raw logs
            updated_lore = notes_response['response'].strip()
            write_file_content(LORE_FILE, updated_lore)

        except Exception as e:
            print(f"\n❌ Local Connection Error: {e}")
            break

if __name__ == "__main__":
    main()
