"""
Multi-agent orchestration layer.

Three cooperating agents, coordinated by an event-driven `AgentOrchestrator`
that mirrors ADF-style trigger/dependency orchestration:

    RetrieverAgent -> ReasonerAgent -> ResponderAgent

Each agent is a small, single-responsibility unit so the chain can be
extended (e.g. add a CriticAgent for self-verification) without touching
the others - the same modular-DAG mindset used for reusable pipeline
templates.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.config import settings
from src.monitoring import timed
from src.vector_store import SearchResult, VectorStore


@dataclass
class AgentContext:
    question: str
    retrieved: list[SearchResult] = field(default_factory=list)
    draft_answer: str | None = None
    citations: list[str] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)


class RetrieverAgent:
    """Pulls the most relevant Gold-layer chunks for the incoming question."""

    def __init__(self, vector_store: VectorStore) -> None:
        self.vector_store = vector_store

    def run(self, ctx: AgentContext) -> AgentContext:
        with timed("agent.retriever", question=ctx.question[:80]):
            ctx.retrieved = self.vector_store.search(ctx.question, top_k=settings.top_k)
            ctx.trace.append(f"retriever: found {len(ctx.retrieved)} chunks")
            return ctx


class ReasonerAgent:
    """Grounds reasoning strictly in retrieved context; falls back to an
    extractive summary when no LLM credentials are configured, so the whole
    pipeline stays runnable end-to-end in CI without external API access."""

    def __init__(self) -> None:
        self._client = None
        if settings.openai_api_key:
            from openai import OpenAI

            self._client = OpenAI(api_key=settings.openai_api_key)

    def run(self, ctx: AgentContext) -> AgentContext:
        with timed("agent.reasoner", chunks=len(ctx.retrieved)):
            if not ctx.retrieved:
                ctx.draft_answer = "I don't have enough indexed context to answer that yet."
                ctx.trace.append("reasoner: no context available")
                return ctx

            context_block = "\n\n".join(f"[{r.chunk_id}] {r.text}" for r in ctx.retrieved)

            if self._client is not None:
                completion = self._client.chat.completions.create(
                    model=settings.chat_model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Answer strictly using the provided context. "
                                "Cite chunk ids you relied on. If the context is "
                                "insufficient, say so explicitly."
                            ),
                        },
                        {
                            "role": "user",
                            "content": f"Context:\n{context_block}\n\nQuestion: {ctx.question}",
                        },
                    ],
                    timeout=settings.request_timeout_s,
                )
                ctx.draft_answer = completion.choices[0].message.content
            else:
                ctx.draft_answer = (
                    "Based on the retrieved context: "
                    + " ".join(r.text[:200] for r in ctx.retrieved[:2])
                )

            ctx.citations = [r.chunk_id for r in ctx.retrieved]
            ctx.trace.append("reasoner: drafted grounded answer")
            return ctx


class ResponderAgent:
    """Formats the final response and attaches provenance for auditability."""

    def run(self, ctx: AgentContext) -> dict:
        with timed("agent.responder"):
            ctx.trace.append("responder: formatted final payload")
            return {
                "answer": ctx.draft_answer,
                "citations": ctx.citations,
                "trace": ctx.trace,
            }


class AgentOrchestrator:
    """Event-driven coordinator: wires the agent chain together and exposes
    a single entrypoint, analogous to an ADF pipeline invoking dependent
    activities in sequence with shared run-context."""

    def __init__(self, vector_store: VectorStore) -> None:
        self.retriever = RetrieverAgent(vector_store)
        self.reasoner = ReasonerAgent()
        self.responder = ResponderAgent()

    def handle(self, question: str) -> dict:
        ctx = AgentContext(question=question)
        ctx = self.retriever.run(ctx)
        ctx = self.reasoner.run(ctx)
        return self.responder.run(ctx)
