# Fine_Tunning_LLM

Short developer-oriented repo for experimenting with parameter-efficient fine-tuning (PEFT) of causal LLMs using LoRA and qLoRA.

**What this repo does**
- Provides a minimal baseline inference script and the structure to add LoRA / qLoRA adapter training and adapter-based inference. The goal is to iterate quickly on small, task-specific datasets and compare the baseline model vs adapter-enhanced model.

**What is PEFT?**
- PEFT (Parameter-Efficient Fine-Tuning) is a class of techniques that modify only a small subset of a large language model's parameters (or add small adapter modules) instead of updating all weights. Common methods include LoRA (low-rank adapters) and qLoRA (quantized LoRA for low-memory fine-tuning). PEFT lets you adapt large models using far less compute, storage, and training time while keeping the base model weights unchanged.

**Model & libraries used**
- Base model: `microsoft/phi-1_5` (specified in `script1_baseline_chat.py`).
- Key libraries: `transformers`, `peft`, `accelerate`, `bitsandbytes` (optional, for 4-bit/qLoRA), `datasets`, `torch`.
- See `requirement.txt` for full dependency pins.

**Data format**
- Training data: `data/train.jsonl` — each line is a JSON object with at least `instruction` and `output` fields (example present in the repo).
- Evaluation data: `data/eval_questions.jsonl` — each line is a JSON object with a `question` field used for quick manual/automated evaluation.

**Project structure (key files)**
- [projectflow.txt](projectflow.txt): high-level flow and next steps.
- [script1_baseline_chat.py](script1_baseline_chat.py): baseline inference using `microsoft/phi-1_5`.
- [script2_lora_finetune.py](script2_lora_finetune.py): (to implement) LoRA training pipeline that saves adapters under `models/adapters/`.
- [script2_qlora_finetune.py](script2_qlora_finetune.py): (to implement) qLoRA (4-bit) training pipeline.
- [script3_chat_with_adapter.py](script3_chat_with_adapter.py): (to implement) inference code demonstrating how to load the base model and attach an adapter.

**Quick start**
1. Create a Python virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirement.txt
```

2. Baseline inference (downloads base model):

```bash
python script1_baseline_chat.py
```

3. Next (recommended) work to finish the repo:
- Implement `script2_lora_finetune.py` to train and save adapters into `models/adapters/` using `peft` + `accelerate`.
- Implement `script3_chat_with_adapter.py` to load adapters (PEFT API) and compare outputs vs baseline.
- Add small README files inside each saved adapter folder describing hyperparameters and dataset.

**Hardware & notes**
- GPU recommended. Use `bitsandbytes` + qLoRA for memory-efficient 4-bit training if you have limited GPU RAM. LoRA is simpler and good for quick experiments.

If you want, I can implement the LoRA and qLoRA training scripts and add an automated evaluation script next.
