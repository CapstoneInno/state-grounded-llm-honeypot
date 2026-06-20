# Model Selection Notes

## Goal

Select a local model suitable for a state-grounded SSH honeypot.

## Candidate Models

### qwen2.5:3b

Pros:
- Small memory footprint
- Fast inference
- Works on low-resource systems

Cons:
- Lower reasoning quality

### qwen2.5:7b

Pros:
- Better instruction following
- Better contextual consistency

Cons:
- Higher RAM requirements
- Slower responses

### llama3.1:8b

Pros:
- Strong general reasoning
- Large community support

Cons:
- Resource intensive

## Initial Decision

For Week 2 development and testing, qwen2.5:3b is selected as the default model.

Reasons:
- Already integrated in the project
- Runs on modest hardware
- Suitable for rapid iteration

Future work:
- Benchmark qwen2.5:7b
- Benchmark llama3.1:8b
- Compare consistency and latency
