import os
import jsonlines
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import peft_model
import torch

import warnings
warnings.filterwarnings("ignore")

DATA_DIR = "data"
EVAL_FILE = os.path.join(DATA_DIR, "eval_questions.jsonl")
BASE_MODEL = "microsoft/phi-1_5"

def load_eval_questions():
    questions = []
    with jsonlines.open(EVAL_FILE, "r") as reader:
        for l in reader:
            questions.append(l["question"])
    return questions 

def chat(model, tokenizer, question):
    """ Generate response for a given queestion. """
    prompt = f"question : {question}\n Answer:"
    input = tokenizer(prompt, return_tensors = "pt")

    with torch.no_grad(): # tells PyTorch: Don't track gradients
        # Normally, PyTorch tracks all the operations on tensors to compute gradients for training neural networks( backpropagation.)
        # When you are only running inference(making predictions, not training), you don't need gradients.
        optput_ids = model.generate(  # Calls the model's text generation engine
            **input,  # model receives the tokenizer prompt.
            max_new_tokens = 80, # The model can generate up to 80 tokens
            do_sample = False, # Disable randomness, the model always picks the most probable next token
            temperature = 0.1, # Controls how "sharp" or "flat" token probabilities are
            pad_token_id = tokenizer.eos_token_id
            # Hugging Face requires a pad token for generation, Prevents warnings or runtime errors
            # Some models need all sequences in a batch to be the same length, so they  add "padding" tokens to short sequences.
            # The pad_token_id_ argument specifies which token ID should be used for this padding. 
        )
    decoder = tokenizer.decode(optput_ids[0], skip_special_tokens = True)
    # output_ids -> first (and only) squence in the batch
    # skip_special token -> removes things like: <eos>, <pad>
    return decoder

def run_baseline_evaluation():
    print("\nLoading base model....\n\n")

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    # tokenizer  - load the text -to-numbers convert that was trained alongside this model.
    model  = AutoModelForCausalLM.from_pretrained(BASE_MODEL, trust_remote_code=True)
    
    # model - Load the actual neural network weights of the language model.

    questions = load_eval_questions()
    if not questions:
        print(f"No evaluation questions found in {EVAL_FILE}. Please add JSONL entries with a 'question' field.")
        return

    print("\n====== Baseline Response (Before Finetunning) ======\n\n")

    for q in questions:
        print(f"Question: {q}\n")
        answer = chat(model, tokenizer,q)
        print(f"Model's Final Response: {answer}\n\n")
        print("_"*60)

run_baseline_evaluation()   
