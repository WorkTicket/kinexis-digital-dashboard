"""
QLoRA fine-tune Qwen3-14B on Kinexis marketing SFT data, then merge adapters
into full weights for Ollama export.

True full-parameter FT of 14B needs ~80GB+ VRAM. On a 12GB card (e.g. RTX 5070)
we train with 4-bit QLoRA, merge LoRA -> dense weights, then quantize to GGUF.

Usage (from finetune/ with venv active):
  python generate_dataset.py
  python train.py
  python train.py --merge-only   # if adapters already trained
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = ROOT / "data" / "train.jsonl"
DEFAULT_VAL = ROOT / "data" / "val.jsonl"
DEFAULT_OUT = ROOT / "output" / "kinexis-marketing-qlora"
DEFAULT_MERGED = ROOT / "output" / "kinexis-marketing-merged"
BASE_MODEL = os.environ.get("KINEIS_FT_BASE", "Qwen/Qwen3-8B")


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def format_chat(tokenizer, messages: list[dict]) -> str:
    if hasattr(tokenizer, "apply_chat_template"):
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False,
        )
    parts = []
    for m in messages:
        parts.append(f"<|{m['role']}|>\n{m['content']}")
    return "\n".join(parts)


def train(args: argparse.Namespace) -> None:
    import torch
    from datasets import Dataset
    from peft import LoraConfig, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    train_rows = load_jsonl(Path(args.train_data))
    val_rows = load_jsonl(Path(args.val_data)) if Path(args.val_data).exists() else []

    print(f"Base model: {args.base_model}")
    print(f"Train examples: {len(train_rows)}  Val: {len(val_rows)}")
    print(f"GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")
    if torch.cuda.is_available():
        mem = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        print(f"VRAM: {mem:.1f} GB")
        if mem < 20 and not args.force:
            print(
                "Note: 14B QLoRA on ~12GB is tight. Using batch=1, grad accumulation, "
                "and checkpointing. Pass --force to silence this."
            )

    compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=compute_dtype,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Keep the whole quantized model on GPU (required for stable bnb + LoRA on Windows).
    # Default base is Qwen3-8B for 12GB cards; set KINEIS_FT_BASE=Qwen/Qwen3-14B on 24GB+.
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        quantization_config=bnb,
        device_map={"": 0},
        trust_remote_code=True,
        dtype=compute_dtype,
    )
    model = prepare_model_for_kbit_training(model)
    model.config.use_cache = False

    lora = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
    )

    def to_text(row: dict) -> dict:
        return {"text": format_chat(tokenizer, row["messages"])}

    train_ds = Dataset.from_list(train_rows).map(to_text)
    eval_ds = Dataset.from_list(val_rows).map(to_text) if val_rows else None

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sft_args = SFTConfig(
        output_dir=str(out_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        logging_steps=5,
        save_strategy="epoch",
        eval_strategy="epoch" if eval_ds is not None else "no",
        bf16=torch.cuda.is_bf16_supported(),
        fp16=not torch.cuda.is_bf16_supported(),
        optim="paged_adamw_8bit",
        gradient_checkpointing=True,
        max_grad_norm=0.3,
        report_to="none",
        seed=args.seed,
        dataset_text_field="text",
        max_length=args.max_seq_len,
        packing=False,
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        peft_config=lora,
        processing_class=tokenizer,
    )

    trainer.train()
    adapter_dir = out_dir / "adapter"
    trainer.save_model(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    print(f"Saved LoRA adapter -> {adapter_dir}")

    if args.merge:
        merge_adapters(args.base_model, adapter_dir, Path(args.merged_dir))


def merge_adapters(base_model: str, adapter_dir: Path, merged_dir: Path) -> None:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    # CPU merge avoids GPU OOM/freeze on 12GB cards (8B fp16 ~16GB).
    print(f"Merging {adapter_dir} into full weights on CPU (slower, safer)...")
    tokenizer = AutoTokenizer.from_pretrained(adapter_dir, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        dtype=torch.float16,
        device_map="cpu",
        trust_remote_code=True,
        low_cpu_mem_usage=True,
    )
    model = PeftModel.from_pretrained(model, str(adapter_dir))
    model = model.merge_and_unload()
    merged_dir.mkdir(parents=True, exist_ok=True)
    print(f"Saving merged weights to {merged_dir} ...")
    model.save_pretrained(str(merged_dir), safe_serialization=True, max_shard_size="2GB")
    tokenizer.save_pretrained(str(merged_dir))
    print(f"Merged full weights -> {merged_dir}")
    print("Next: run export_ollama.ps1 to convert to GGUF and create the Ollama model.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Kinexis QLoRA fine-tune")
    ap.add_argument("--base-model", default=BASE_MODEL)
    ap.add_argument("--train-data", default=str(DEFAULT_DATA))
    ap.add_argument("--val-data", default=str(DEFAULT_VAL))
    ap.add_argument("--output-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--merged-dir", default=str(DEFAULT_MERGED))
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--grad-accum", type=int, default=16)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--lora-alpha", type=int, default=32)
    ap.add_argument("--max-seq-len", type=int, default=2048)
    ap.add_argument(
        "--gpu-max-mem-gb",
        type=int,
        default=10,
        help="Cap GPU allocation so accelerate can offload overflow to CPU on 12GB cards",
    )
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--merge", action="store_true", default=True)
    ap.add_argument("--no-merge", action="store_true")
    ap.add_argument("--merge-only", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--full-ft",
        action="store_true",
        help="Attempt full-parameter FT (needs >>12GB VRAM; errors clearly if not feasible)",
    )
    args = ap.parse_args()
    if args.no_merge:
        args.merge = False

    if args.full_ft:
        raise SystemExit(
            "Full-parameter fine-tuning of Qwen3-14B needs ~80GB+ GPU memory "
            "(or multi-GPU ZeRO). On this machine use QLoRA (default), which merges "
            "into full dense weights afterward for Ollama.\n"
            "To full-FT a smaller base instead: set KINEIS_FT_BASE=Qwen/Qwen3-8B "
            "and use a multi-GPU / cloud box with DeepSpeed ZeRO-3."
        )

    if args.merge_only:
        merge_adapters(
            args.base_model,
            Path(args.output_dir) / "adapter",
            Path(args.merged_dir),
        )
        return

    if not Path(args.train_data).exists():
        raise SystemExit(f"Missing {args.train_data} — run generate_dataset.py first")

    train(args)


if __name__ == "__main__":
    main()
