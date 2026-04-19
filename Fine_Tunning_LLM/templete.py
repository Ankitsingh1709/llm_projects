import os
import pathlib

def create_lora_qlora_structure():
    """Create the LoRA/qLoRA fine-tuning project structure with empty files"""
    
    # Define the complete folder structure
    structure = {
        "": [  # Root directory files
            "script1_baseline_chat.py",
            "script2_lora_finetune.py", 
            "script2_qlora_finetune.py",
            "script3_chat_with_adapter.py",
            "requirements.txt",
            "README.md"
        ],
        "data": [
            "train.jsonl",
            "eval_questions.jsonl"
        ],
        "models/base": [
            ".gitkeep"  # Placeholder file to keep the directory
        ],
        "models/adapters": [
            ".gitkeep"  # Placeholder file to keep the directory
        ]
    }
    
    print("Creating LoRA/qLoRA Fine-tuning Project structure...")
    
    # Create all folders and files
    for folder, items in structure.items():
        # Create folder if it doesn't exist
        if folder:
            os.makedirs(folder, exist_ok=True)
            print(f"📁 Created folder: {folder}/")
        
        # Create files within the folder
        for item in items:
            file_path = os.path.join(folder, item) if folder else item
            
            # Handle directories (ending with /)
            if item.endswith('/'):
                os.makedirs(file_path, exist_ok=True)
                print(f"📁 Created folder: {file_path}")
            else:
                # Create empty file
                pathlib.Path(file_path).touch()
                print(f"📄 Created file: {file_path}")
    
    print("\n✅ LoRA/qLoRA Fine-tuning Project structure created successfully!")
    print("📂 All files and folders are now ready.")

if __name__ == "__main__":
    create_lora_qlora_structure()