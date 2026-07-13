# LLM App Engineering Course 📚

> [中文](README.md) | **English**

A hands-on, **learn-from-zero-to-mastery** course for building large language model applications, covering six tracks: **RAG · Agents · Framework Engineering · Multi-Agent Orchestration · LLMOps · Agent Frontiers**.

Designed for **developers who know Python but are new to LLMs**, it pairs runnable code with principle walkthroughs—taking you step by step from hand-written fundamentals to framework implementations, then to multi-agent architectures, and finally into the frontier of agent capabilities.

> **Stack:** Zhipu GLM-4 + embedding-3 · Chroma (local vector DB) · LangChain + LangGraph · CrewAI · AutoGen · Python

---

## 🗺️ The Six Courses at a Glance

This workspace holds **six progressive courses**. Recommended order:

| Course | What you learn | Status |
|--------|----------------|--------|
| 📘 [Hand-written RAG](rag-lessons/) | Understand RAG from scratch (embedding → retrieval → chunking → prompting → hybrid retrieval → rewriting → evaluation → engineering) | ✅ 9/9 done |
| 🤖 [Hand-written Agents](agent-lessons/) | Understand AI Agents from scratch (Function Calling → ReAct → tool design → memory → planning → Agentic RAG → multi-agent → capstone) | ✅ 9/9 done |
| 🔧 [Framework Engineering](framework-lessons/) | LangChain + LangGraph engineering (translate hand-written principles into frameworks; each lesson compares "hand-written vs framework") | ✅ 9/9 done |
| 🔀 [Workflow & Multi-Agent Orchestration](workflow-lessons/) | Multi-agent collaboration architectures (supervisor / swarm / subgraphs / parallel / shared state / multi-model; side-by-side comparison across three frameworks) | ✅ 9/9 done |
| 🛡️ [LLMOps in Production](ops-lessons/) | After launch: observability (logging / tracing / online eval) → security (auth & rate limiting / injection offense & defense / guardrails) → MCP integration → performance & cost (caching / load testing / model selection). Take the portfolio projects from "works" to "ops-ready" | ✅ 13/13 done |
| 🧠 [Agent Frontiers](frontier-lessons/) | Agent memory / reflection / Code Agents / trajectory eval / context engineering / long-horizon tasks—teaching not-yet-converged frontiers, growing research-assistant into a cross-session Deep Research Agent v2. **Every lesson has a schools-of-thought comparison + design experiments that validate the gains** | ✅ 13/13 done |

> **Learning path:** RAG first (understand retrieval) → Agents (autonomous decision-making) → Framework Engineering (productionize) → Multi-Agent Orchestration (architect track) → LLMOps (ops-ready) → Agent Frontiers (let agents evolve).

---

## 🚀 Production-Grade Portfolio Projects

After finishing the courses, stitch the skills together into **genuinely production-ready AI apps**:

| Project | What it is | Status |
|---------|-----------|--------|
| 📚 [Enterprise Knowledge Base QA](portfolio-projects/knowledge-base-qa/) | Production RAG: hybrid retrieval + Zhipu rerank + anti-hallucination citations + ragas evaluation. **Upgraded to ops-ready v2 in ops-lessons:** structured logging / Langfuse tracing / online eval loop + API-key auth & rate limiting + injection-defense guardrails + an MCP Server (callable by Agents) + semantic caching / load testing / cost-aware model selection. | ✅ Ops-ready |
| 🔬 [AI Research Assistant](portfolio-projects/research-assistant/) | A multi-agent parallel research system: real web search + review loop + multi-model cost optimization + SSE streaming + SqliteSaver persistence + FastAPI service + Docker deploy. **Gains MCP access in ops-lessons L09** (internal + web dual sources). **Upgraded to Deep Research Agent v2 in frontier-lessons:** agent memory (episodic / semantic layered) + reflective dual-channel reviewer (conflict correction) + CodeAct code interpreter (reproducible numbers) + progressive Skills loading + task ledger (cross-session incremental briefings) + trajectory evaluation (mechanism gains quantified). | ✅ Deep v2 |

> These are **production-grade landings** of the course skills—not demos, but AI application services you can deploy directly, handle real traffic, and tell a complete ops story with.
> The two projects are wired together via the MCP standard protocol (see [ops-lessons L09](ops-lessons/09_mcp_client/)).

---

## 📚 Course 1: Hand-written RAG (9 lessons)

Follows the real RAG data flow, adding one stage per lesson:

| # | Lesson | You'll learn |
|---|--------|--------------|
| 01 | [Get it running: your first RAG](rag-lessons/01_getting_started/) | Run the full pipeline end-to-end and build the big picture |
| 02 | [Deep dive into Embeddings](rag-lessons/02_embedding/) | How vectors represent semantics, cosine similarity |
| 03 | [Vector Retrieval](rag-lessons/03_retrieval/) | Top-K, ANN, and using Chroma |
| 04 | [Chunking](rag-lessons/04_chunking/) | The trade-offs of chunk_size / overlap |
| 05 | [Prompt Engineering](rag-lessons/05_prompt/) | Anti-hallucination prompts, citation grounding |
| 06 | [Advanced Retrieval](rag-lessons/06_advanced_retrieval/) | Hybrid retrieval + reranking |
| 07 | [Query Rewriting](rag-lessons/07_query_rewrite/) | HyDE, multi-query expansion |
| 08 | [RAG Evaluation](rag-lessons/08_evaluation/) | The three RAGAS dimensions |
| 09 | [Engineering: Capstone](rag-lessons/09_engineering/) | An interactive QA assistant integrating everything |

> All **9 lessons** done 🎉. Each lesson has a principle walkthrough + runnable code + exercises.

---

## 🤖 Course 2: Hand-written Agents (9 lessons)

Builds up agent capability layer by layer—each lesson adds one ability (tools → loop → memory → planning → collaboration):

| # | Lesson | You'll learn |
|---|--------|--------------|
| 01 | [Meet the Agent: from Q&A to action](agent-lessons/01_what_is_agent/) | Run a minimal agent; grasp "LLM + tools + decision" |
| 02 | [Function Calling in depth](agent-lessons/02_function_calling/) | Understand the function-calling mechanism; hand-write a generic tool dispatcher |
| 03 | [ReAct: the think-act-observe loop](agent-lessons/03_react_loop/) | Hand-write a minimal ReAct loop (no framework; an interview staple) |
| 04 | [Multiple tools & tool design](agent-lessons/04_tool_design/) | Trade-offs across 5+ tools; how description quality affects selection |
| 05 | [Memory: remembering context](agent-lessons/05_memory/) | Multi-turn dialogue, context-window limits and handling strategies |
| 06 | [Planning & task decomposition](agent-lessons/06_planning/) | The Plan-and-Execute paradigm vs ReAct, and when to use which |
| 07 | [Agentic RAG: Agent + RAG](agent-lessons/07_agentic_rag/) | Wrap RAG as a tool; let the agent decide when to retrieve |
| 08 | [Multi-agent collaboration](agent-lessons/08_multi_agent/) | Multiple agents, each with a role, cooperate on complex tasks |
| 09 | [Capstone: smart research assistant](agent-lessons/09_capstone/) | Web search + structured research report (résumé-grade) |

> All **9 lessons** done 🎉. Each lesson has a principle walkthrough + runnable code + exercises.

---

## 🔧 Course 3: Framework Engineering (9 lessons)

Re-implement what you hand-wrote in the first two courses with **LangChain / LangGraph**, comparing "hand-written vs framework" each lesson:

| # | Lesson | You'll learn |
|---|--------|--------------|
| 01 | [LCEL & the framework landscape](framework-lessons/01_lcel_overview/) | Hand-written RAG vs LCEL—see what the framework does for you |
| 02 | [The trio: Models + Prompts + Parsers](framework-lessons/02_models_prompts_parsers/) | Standardized building blocks for calling models, writing prompts, parsing output |
| 03 | [Documents: Loaders + Splitters + VectorStores](framework-lessons/03_documents_splitter_vectorstore/) | The engineering pipeline for getting data in |
| 04 | [Retrievers + RAG Chain](framework-lessons/04_retrievers_rag_chain/) | Compose blocks with `\|` into a full RAG chain |
| 05 | [Advanced retrieval engineering](framework-lessons/05_advanced_retrieval/) | Ensemble + MultiQuery—where the framework really pays off |
| 06 | [LangGraph basics](framework-lessons/06_langgraph_basics/) | Rewrite ReAct with StateGraph (the pivot from LangChain to LangGraph) |
| 07 | [Framework-level Agents](framework-lessons/07_tools_and_agents/) | `@tool` decorator + `create_agent`—dozens of hand-written lines in a few |
| 08 | [State, memory & human-in-the-loop](framework-lessons/08_state_memory_hitl/) | Checkpointer persistence + interrupt HITL (LangGraph's killer feature) |
| 09 | [Capstone: LangGraph research assistant](framework-lessons/09_capstone/) | Multi-node graph + Checkpointer, integrating all framework skills |

> All **9 lessons** done 🎉. Each lesson has a principle walkthrough + runnable code + exercises.

---

## 🔀 Course 4: Workflow & Multi-Agent Orchestration (9 lessons)

The first three courses cover "single agent + single flow." This course moves into **multi-agent orchestration**—a core skill for the AI architect track. LangGraph is the backbone for 6 classic topologies, then CrewAI / AutoGen are used for cross-paradigm comparison on the same problem:

| # | Lesson | You'll learn |
|---|--------|--------------|
| 01 | [Supervisor pattern](workflow-lessons/01_supervisor_pattern/) | Centralized dynamic routing (vs the hard-coded loop from hand-written L08) |
| 02 | [Swarm & Handoff](workflow-lessons/02_swarm_handoff/) | Decentralized swarm + state handoff (vs hand-written string concatenation) |
| 03 | [Subgraphs](workflow-lessons/03_subgraph/) | Embed a compiled graph as a node for modular reuse |
| 04 | [Parallel Map-Reduce](workflow-lessons/04_parallel_mapreduce/) | fan-out burst + reducer merge (parallelism hand-writing can't do) |
| 05 | [Shared-state communication](workflow-lessons/05_shared_state/) | Compare messaging / shared state / blackboard |
| 06 | [Multi-model routing & topology](workflow-lessons/06_multimodel_routing/) | Star / ring / mesh / hierarchical topologies + cost control |
| 07 | [CrewAI comparison](workflow-lessons/07_crewai_comparison/) | Role-driven declarative orchestration vs LangGraph supervisor |
| 08 | [AutoGen comparison](workflow-lessons/08_autogen_comparison/) | Conversation-driven group chat vs LangGraph swarm |
| 09 | [Capstone: multi-agent research system](workflow-lessons/09_capstone/) | supervisor + parallel + shared state + multi-model (résumé-grade) |

> All **9 lessons** done 🎉. Each lesson keeps the "hand-written Agent L08 pipeline vs framework multi-agent" side-by-side. The L09 capstone integrates all of L01–L08 and is a résumé-grade piece.

---

## 🛡️ Course 5: LLMOps in Production (13 lessons)

The first four courses teach you to **build** an AI app; this one teaches you to **operate** it—answering the interviewer's "and after your project goes live? How do you know it's good, defend against attacks, get integrated by other systems, control cost?" All changes land directly on **knowledge-base-qa**, upgrading it from "running demo" to "ops-ready v2." Four modules, progressively:

| # | Lesson | You'll learn |
|---|--------|--------------|
| 01 | [Structured logging](ops-lessons/01_structured_logging/) | From print to queryable JSON event streams + trace_id across the chain |
| 02 | [Langfuse end-to-end tracing](ops-lessons/02_langfuse_tracing/) | Visualize per-query retrieval / rerank / generation latency, tokens, cost |
| 03 | [Online eval loop](ops-lessons/03_online_eval/) | Real-query sampling + automated ragas scoring + bad-answer queue |
| 04 | [API auth & rate limiting](ops-lessons/04_auth_ratelimit/) | Key auth + per-key rate limiting—prevent open access and runaway bills (401/429/200) |
| 05 | [Prompt injection offense/defense](ops-lessons/05_prompt_injection/) | Indirect injection (malicious instructions hidden in docs) + build an attack test set and run a breach baseline |
| 06 | [I/O guardrails](ops-lessons/06_guardrails/) | Material isolation + instruction/data separation + output filtering, hardened into CI |
| 07 | [What is MCP](ops-lessons/07_mcp_basics/) | The "USB port" for AI apps: M×N→M+N; hand-write a minimal server/client |
| 08 | [Wrap the KB as an MCP Server](ops-lessons/08_mcp_server/) | Expose kb-qa retrieval as a standard tool; any host integrates with zero code |
| 09 | [Agent as MCP Client](ops-lessons/09_mcp_client/) | research-assistant calls kb-qa—connecting the two portfolio projects |
| 10 | [Semantic caching](ops-lessons/10_semantic_cache/) | Cache hits on synonymous queries, skipping retrieval + generation |
| 11 | [Load testing & concurrency](ops-lessons/11_loadtest/) | QPS / P95 / P99 baselines; locate the bottleneck at the upstream API limiter |
| 12 | [Cost/quality trade-offs](ops-lessons/12_cost_quality/) | Quantify glm-4 vs flash on eval data; per-stage model selection to cut cost |
| 13 | [Capstone: ops-ready v2](ops-lessons/13_capstone/) | An ops dashboard + a production launch checklist tying all 12 lessons together |

> All **13 lessons** done 🎉. Teaching `code.py` files are all zero-dependency or have mock fallback paths so they run standalone; production changes go into kb-qa with a "## rollout checklist." Places that can't run real external services (Langfuse / Docker / load testing) are **honestly marked as unverified** with a fallback path.

---

## 🧠 Course 6: Agent Frontiers (13 lessons)

The first five courses teach **converged knowledge** (how to chunk for RAG, how to write ReAct). This course teaches **not-yet-converged frontiers**—agent memory, reflection, Code Agents, trajectory evaluation, context engineering—where the industry has no standard answer. So the style changes: the README doesn't lecture "the standard way," it lays out "which schools of thought exist, what the trade-offs are, and why we picked X…"; the code is "hand-write the core mechanism + a design experiment to test whether it helps." All changes land on **research-assistant**, growing it from a one-shot "search → write report" system into a **cross-session Deep Research Agent v2**. Six modules:

| # | Lesson | You'll learn |
|---|--------|--------------|
| 00 | [Method warm-up](frontier-lessons/00_method/) | The three-pass paper reading method + reading LangGraph source + running an amnesiac baseline (reference throughout) |
| 01 | [Memory tiers](frontier-lessons/01_memory/) | Episodic (Chroma) + semantic (list) MemoryStore; researcher gets `recall` |
| 02 | [Reflective writes](frontier-lessons/02_reflection_write/) | `reflect_and_store` distills memory + `consolidate` reinforces + forgetting policy |
| 03 | [Skills & context engineering](frontier-lessons/03_skills/) | Progressive `skill_loader`; unify memory / skills / RAG / MCP under context engineering |
| 04 | [Hand-written Reflexion](frontier-lessons/04_reflexion/) | Three-component loop + blind-retry vs reflective-retry comparison + ablation |
| 05 | [Reflection into the research loop](frontier-lessons/05_reflection_research/) | Dual-channel reviewer (text + facts) + conflict detection + targeted re-research and correction |
| 06 | [Hand-written CodeAct](frontier-lessons/06_codeact/) | Code as the action space + process-level sandbox (import allowlist / timeout / truncation) |
| 07 | [Code interpreter lands](frontier-lessons/07_code_interpreter/) | `code_interpreter` wired into writer; report numbers become reproducible |
| 08 | [Trajectory evaluation](frontier-lessons/08_trajectory_eval/) | TrajectoryEvaluator: success rate / steps / loops / attribution + mechanism-trigger detection |
| 09 | [Eval Harness](frontier-lessons/09_eval_harness/) | Switch matrix × task set = mechanism-gains table (regression-style eval) |
| 10 | [Long-horizon tasks](frontier-lessons/10_long_task/) | TaskLedger: TODO tree + resume-from-checkpoint + incremental briefings |
| 11 | [Capstone](frontier-lessons/11_capstone/) | Deep Research v2: five mechanisms in concert + architecture doc + gains table |
| 12 | [Frontier-tracking method](frontier-lessons/12_frontier_tracking/) | Full three-pass reading method + framework evaluation checklist + minimal multi-agent memory-sharing repro |

> All **13 lessons** done 🎉. **Two through-lines:** ① an evaluation main line (L00 sets the baseline → L08 builds the evaluator → L09 harness quantifies every mechanism's gain); ② a context-engineering main line (memory / skills / RAG / MCP unified under the one question "what goes in the window"). Each lesson's README has a "schools of thought" section + at least one "design experiment to validate" exercise. 104 unit tests green; all new mechanisms default-off, with intact fallback paths.

---

## 🚀 Quick Start (5 steps)

```bash
# 1. Make sure you have Python 3.9+
python --version

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure your API key
cp .env.example .env
# Edit .env and replace ZHIPUAI_API_KEY with your real key
# Get a key: https://bigmodel.cn/ → Console → API Keys

# 4. Run the first lesson
python rag-lessons/01_getting_started/code.py

# 5. Watch the output, then read rag-lessons/01_getting_started/README.md for the principles
```

Once it runs, open the [Lesson 01 exercise](rag-lessons/01_getting_started/exercise.md) and tweak the code yourself.

---

## 📁 Directory Structure

```
RAG-test/
├── README.md                  ← Course index (Chinese)
├── README.en.md               ← You are here: six courses + portfolio overview (English)
├── requirements.txt           ← Dependencies (shared across all six courses)
├── .env.example               ← API key config template
├── data/sample_docs/          ← Sample docs for exercises (shared across courses)
├── rag-lessons/               ← Course 1: Hand-written RAG (9 lessons, done)
├── agent-lessons/             ← Course 2: Hand-written Agents (9 lessons, done)
├── framework-lessons/         ← Course 3: Framework Engineering (9 lessons, done)
├── workflow-lessons/          ← Course 4: Workflow & Multi-Agent Orchestration (9 lessons, done)
├── ops-lessons/               ← Course 5: LLMOps in Production (13 lessons, done)
├── frontier-lessons/          ← Course 6: Agent Frontiers (13 lessons, done)
├── portfolio-projects/        ← 🚀 Production-grade portfolio projects (landings after the courses; main battleground for ops/frontier)
│   ├── knowledge-base-qa/     ←   Enterprise KB QA (RAG, ops-ready v2)
│   └── research-assistant/    ←   AI Research Assistant (multi-agent + FastAPI + Docker)
└── docs/                      ← Design docs and implementation plans
```

Each lesson ships as a fixed trio: **① a principles README (the why and the trade-offs) + ② a runnable `code.py` (with detailed comments) + ③ exercises.**
Portfolio projects use a **modular engineering layout** (`src/` + `api/` + `tests/` + `Docker`), organized to production standards.

---

## 💡 Study Tips

- **Run the code.** Don't just read. A lot of RAG intuition comes from changing parameters yourself and watching the output change.
- Learn in order—each lesson builds on the previous one.
- When you're stuck, ask your AI assistant—paste the error and we'll sort it out.

---

Thanks to:
 Linux.do community: https://linux.do/
