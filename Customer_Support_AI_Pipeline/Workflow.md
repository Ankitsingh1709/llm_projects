# Customer Support AI Pipeline Architecture

This document describes the architecture and workflow of the `Customer_Support_AI_Pipeline` project.

## Overview

The pipeline is notebook-driven and uses configuration files to select providers, manage categories, and evaluate model outputs. The main workflow processes customer support transcripts, classifies requests, generates AI responses, and evaluates those responses against quality criteria.

## Architecture Diagram

```text
+--------------------+      +----------------------+      +---------------------+
|                    |      |                      |      |                     |
|  data/transcripts  | ---> |   CSC.ipynb          | ---> |   LLM Providers     |
|  .csv              |      |   (analysis/pipeline)|      |   (openai / gemini /|
|                    |      |                      |      |    ollama / openrouter)
+--------------------+      +----------------------+      +---------------------+
                                    |                          |
                                    |                          |
                                    v                          v
                           +---------------------+      +---------------------+
                           |  config.json        |      |  config/config.json |
                           |  (provider, models, |      |  (labels, eval,     |
                           |   eval settings)    |      |   category config)   |
                           +---------------------+      +---------------------+
                                    |
                                    v
                           +---------------------+
                           |  Evaluation /       |
                           |  result review       |
                           +---------------------+
```

## Components

- `CSC.ipynb`
  - Central notebook that orchestrates dataset loading, prompt generation, classification, and evaluation.
  - Runs experiments and visualizes results.

- `data/transcripts.csv`
  - Customer support transcript dataset used as input for classification and response generation.

- `config.json`
  - Top-level provider configuration for model selection and generation parameters.
  - Includes model names, temperatures, and token limits for each supported provider.

- `config/config.json`
  - Domain-specific configuration such as support categories and evaluation criteria.


- `requirements.txt`
  - Python dependencies for running the pipeline.


