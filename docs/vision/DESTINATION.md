# Destination: a personal computational world

**Status:** consolidated aspiration and endorsed design direction. Concrete release scope is in [V1](../roadmap/V1.md); verified implementation is in [STATE](../roadmap/STATE.md). This document describes where we are going, not a retrospective claim that we have arrived.

## 1. The problem is the loss of a world, not the absence of another chatbot

A substantial project leaves fragments everywhere: conversations, terminal output, edits, decisions, prompts, skills, browser pages, subagents, attempted plans, failures, and half-finished actions. The person remembers relations among them that no individual application preserves. An assistant may understand a moment exquisitely, then lose that understanding at a context limit or a handoff. A useful result survives as prose while the conditions that made it useful disappear.

Nema should make those relations survive as structure. A conversation is evidence of work and a participant in it, not the only container in which work can exist. A UI, prompt, context packet, task arrangement, interpretation, and continuation should be independently referable and revisable. The user should not have to serve as the manual serializer of the whole project into every new session.

The immediate motivation is personal: preserve and extend the kind of collaborative thinking that produced this repository. The long-term motivation is broader: a computational environment in which people, agents, code, places, and representations can participate in the same meaningful world.

## 2. What Nema is

**Nema is an authority-local personal computational world whose first and best application is its own reflective workbench.** Eidos is the language through which its descriptions, bindings, interactions, and continuations become inspectable and composable. A nema can be understood as a self-realizing process: it interprets a description of its current situation, interacts, and leaves a new durable description from which work can continue.

This is not a demand to classify every object as a process, actor, frame, observer, and protocol simultaneously. Those are different useful views. The working vocabulary should make a distinction pay rent before multiplying nouns.

“Authority-local” means the owner's domain is a real locus of control, persistence, and resource decisions. It does not mean all execution must happen on one physical machine. Local and remote executors can be bound to roles, but identity, authority, placement, and route must not silently become the same thing. A web interface is one client of the personal world, not its sole owner.

Codex is the initial powerful native evaluator. Nema wraps it. We want the user's existing authorized Codex subscription and native harness behavior, not an expensive accidental reimplementation of the agent loop. Other providers or executors may later inhabit compatible roles without defining the language around the lowest common denominator.

## 3. The transformative experience

Imagine returning to a complicated project after interruption. Instead of finding the right chat and scrolling, open a saved working arrangement. It shows a current plan, relevant evidence, unresolved alternatives, live or suspended processes, and the exact changes under consideration. Each panel is a lens, not an independent cache with a different idea of reality.

Ask: “Show the argument that led us to this design, alongside the strongest rejected alternative. Put the implementation diff below it. Give a specialist the two relevant cuts, but not unrelated conversation history. Let it ask for more evidence if needed. Keep the current production thread untouched.”

The arrangement and the context given to the specialist are themselves inspectable artifacts. The specialist may realize a local closure, use Codex, inspect a named value, ask another observer, suspend awaiting a response, or be handed to another executor. The returned work cites its sources and records what was supplied, what was inferred, and what was actually done. The user can compare, accept, reject, or reinterpret it.

Later an auditor notices that several investigations repeatedly needed the same missing context. It proposes a better lens, instruction, skill, wrapper, or context builder. The proposal includes the motivating traces, a patch, a falsifiable expected improvement, and tests against held-out or explicitly counterfactual cases. Adoption creates a new version. The prior environment and explanation remain available.

This whole loop—not any single screen—is the product.

## 4. Five enduring principles

### Semantic conservation

When information crosses a boundary, preserve every meaningful relation that can survive it. At an opaque boundary, preserve the raw record and identify what remains unknown rather than inventing a complete ontology. Keep native fields, call identities, timings, output fragments, and relationships available for later interpreters. A summary cannot be the only surviving source.

This is not “store secrets indiscriminately.” Capture policy, redaction, private storage, and authorization are part of the boundary; record deliberate omissions and their reasons.

### Addressability

Anything that may later matter independently deserves a stable way to refer to it: not only documents, but evidence ranges, bindings, context versions, places, prompts, proposals, continuations, observations, and views. References must survive rearrangement and historical reinterpretation. A label or array position is not durable identity.

### Observer-relative understanding, shared causal facts

There is no compulsory canonical UI, narrative, or universal frontier. Different observers may possess different causal cuts and models. Their histories can meet through an occurrence without becoming one omniscient viewpoint. This is not metaphysical denial of truth: the system can record objective local commitments and distinguish them from interpretations. Something previously outside an observer's addressable world may enter it through a new observation.

### Grounded agency

Descriptions are not possession. Knowledge is not permission. A meaningful interface presents currently admissible continuations in a situated domain, not a generic button list that invents authority. Joint understanding may relate cuts from several participants; acting on them still requires the relevant live authority.

### A small core, a consequential whole

Smallness is an architectural discipline, not permission to ship a toy. Reuse native harnesses and derive rich semantics above a narrow boundary. Choose the smallest integrated system that changes how the owner actually works. A tiny kernel can support an ambitious experience; endless kernel reduction can also become an avoidance of it.

## 5. What makes this more than familiar parts

We are deliberately combining several things usually separated:

- A debugger's ability to inspect what happened and what could resume.
- A programmable compositor's ability to arrange attention and expose alternative views.
- An agent harness's ability to delegate meaningful work and invoke tools.
- A personal knowledge environment's durable relations and provenance.
- A language runtime's explicit binding, interpretation, and continuation semantics.

The consequential insight is their recursive closure: the tools for understanding and reshaping work are themselves work in the same medium. The system can inspect an agent's context construction with the same provenance lenses it uses to inspect the agent's output; it can render a proposed UI arrangement as something reviewable before applying it; its own improvement sessions do not happen in an invisible control plane.

Do not claim that assembling those parts proves a new theory of computation. Demonstrate the new decisions and actions the combination makes possible.

## 6. What the first product must not become

Not a chat-history dashboard with counts and status cards. Not a TUI that lists threads but lacks domain-native interaction. Not a replacement Codex loop. Not a grand ontology imposed before useful evidence exists. Not a permissions product whose interesting work never begins. Not a distributed ledger, DNS mesh, or operating-system rewrite required to open yesterday's conversation. Not a self-improvement daemon rewarded for changing itself rather than improving outcomes.

The distinctive aesthetic is restrained, experimental, structurally candid, and high-bandwidth. “Minimal” should remove chrome, not meaning. A diff deserves a diff; a pending answer deserves its question; a process deserves its output; an arrangement deserves the composition proposed and the composition actually realized. JSON is an excellent substrate and an inadequate universal interface.

## 7. Long horizon, without compulsory prerequisites

The world may grow into many independently placed nemata; browser sidecars and terminal hosts; multiple opinionated compositors; negotiated disclosure; reflective model processes; partial evaluation and code migration; semantic knowledge/control of filesystems, services, mail, windows, or remote places. Persistent context and stable references should make these extensions possible.

Earlier intuitions about cells, membranes, sockets, routing, names, and living systems help explain why interaction frontiers matter. They are not scientific premises or mandatory network protocols. Our direction should survive abandoning any particular metaphor, language implementation, storage engine, or transport.

## 8. How to recognize progress

A returning user reconstructs less context, reaches relevant evidence faster, can see why a result followed, safely runs richer investigations, loses less work to interruption, and can test an improvement without confusing its counterfactual world with the live one. Independent agents can contribute without the human manually coordinating every detail. A result can be revisited with better models without erasing what was known or authorized then.

The project is succeeding when its owner naturally uses the workbench to improve the workbench. That is the standard by which the next thousand sessions should be judged.
