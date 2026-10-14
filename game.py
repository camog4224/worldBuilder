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
    """Initializes files and prints the exact narrative text from your last play session."""
    if not os.path.exists(LORE_FILE):
        initial_lore = (
            "# CURRENT CONTEXT\n"
            "- Location: Starting Outpost\n"
            "- Time: Day 1, Dawn\n"
            "- Active Items: [Iron Knife]\n\n"
            "# ACTIVE TIMELINE\n"
            "- You woke up at the edge of the world with no memory.\n"
        )
        write_file_content(LORE_FILE, initial_lore)
        initial_story = "You wake up at the edge of the world with no memory. Cold air cuts through your clothes, and an iron knife rests on the ground beside you."
        write_file_content(LAST_RESPONSE_FILE, initial_story)

    # Load and print the exact last narrative response
    last_story = load_file_content(LAST_RESPONSE_FILE)
    if last_story:
        print("\n" + "📖" * 25)
        print("          ✨ CONTINUING YOUR ADVENTURE ✨          ")
        print("📖" * 25)
        print(f"\n{last_story.strip()}")
        print("\n" + "="*50)
    
    print("\nClean Narrative Engine Active. Make any move you wish. Type 'exit' to save and quit.")

def clean_and_extract_story(full_text):
    """Isolates narrative text and prevents markdown data blocks from printing to screen."""
    match = re.search(r"```markdown\s*(.*?)\s*```", full_text, re.DOTALL | re.IGNORECASE)
    if not match:
        match = re.search(r"```\s*(.*?)\s*```", full_text, re.DOTALL)
        
    extracted_lore = None
    if match:
        extracted_lore = match.group(1).strip()
        block_start_idx = full_text.find("```")
        clean_narrative = full_text[:block_start_idx].strip()
    else:
        clean_narrative = full_text
        if "# CURRENT CONTEXT" in full_text:
            parts = full_text.split("# CURRENT CONTEXT")
            clean_narrative = parts[0].strip()
            extracted_lore = "# CURRENT CONTEXT" + parts[1].strip()

    return clean_narrative, extracted_lore

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

        # --- PASS 1: AUTONOMOUS MEMORY CHECK ---
        memory_prompt = f"""
        You are the mental logic center of a Game Master. 
        The player wants to do this: "{player_input}"
        
        Here is your current active summary:
        {active_lore}

        You have these archive files stored on disk: {available_archives}

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
            if requested_file:
                injected_memory = f"\n\n[RETRIEVED DEEP MEMORY FROM ARCHIVE {requested_file}]:\n" + load_file_content(os.path.join(ARCHIVE_DIR, requested_file))

            # --- PASS 2: PURE STORY GENERATION ---
            system_prompt = (
                "You are an immersive, open-world Text Adventure Engine.\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. Write ONLY the story text describing what happens next. Do not talk to the user out-of-character.\n"
                "2. DO NOT provide choices, hints, or menu options. Let the story hang open-ended.\n"
                "3. At the absolute end of your response, you MUST provide the entire updated active text lorebook "
                "wrapped inside a markdown code block starting with ```markdown. Keep this block strictly at the very end."
            )

            user_prompt = f"""
            ACTIVE LOREBOOK:
            {active_lore}
            {injected_memory}

            PLAYER ACTION:
            {player_input}
            """

            response = ollama.generate(model=MODEL_NAME, system=system_prompt, prompt=user_prompt)
            full_response = response['response']

            story_output, updated_lore = clean_and_extract_story(full_response)

            if updated_lore:
                write_file_content(LORE_FILE, updated_lore)
            
            if story_output:
                # Cache the exact narrative block on disk for the next startup cycle
                write_file_content(LAST_RESPONSE_FILE, story_output)
                print(f"\n{story_output}")

        except Exception as e:
            print(f"\n❌ Local Connection Error: {e}")
            break

if __name__ == "__main__":
    main()
