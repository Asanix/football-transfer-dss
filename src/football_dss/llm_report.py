"""Cognitive layer: turn computed numbers into a sporting-director memo.

The LLM only RE-WORDS facts we pass in as JSON; it gets no web access and is told not to
add facts. Without ANTHROPIC_API_KEY a deterministic template is used instead.
"""
import json
import os

from . import config

SYSTEM = (
    "You are an analyst at a football club writing for the sporting director. "
    "Use ONLY the numbers and names in the JSON you receive; do not add facts, injuries, "
    "real-world transfer news or player history that is not in the JSON. Ratings come from "
    "the EA FIFA 23 game and are proxies, say so once. Write in Russian, concise, with "
    "sections: Вывод, Почему эти игроки, Риски, Что проверить скаутам вживую."
)


def template_report(facts: dict) -> str:
    lines = [f"# Трансферный меморандум: {facts['club']}", "",
             f"Бюджет: {facts['budget_m']:.0f} млн EUR. Чистые траты по плану: {facts['net_spend_m']:.1f} млн EUR.", "",
             "## Приоритетные позиции"]
    lines += [f"- {g['group']}: отставание от элиты {g['gap_vs_elite']:+.1f}, игроков {g['players']}/{g['min_depth']}"
              for g in facts["priorities"]]
    lines += ["", "## Покупки"]
    lines += [f"- {b['short_name']} ({b['pos_group']}, {b['age']:.0f} лет, {b['club_name']}): fit {b['role_fit']:.1f}, "
              f"цена ~{b['fee']/1e6:.1f} млн, риск спада {b['bust_risk']:.0%}" for b in facts["buys"]]
    lines += ["", "## Продажи"]
    lines += [f"- {s['short_name']} ({s['pos_group']}, {s['age']:.0f} лет): ~{s['revenue']/1e6:.1f} млн" for s in facts["sells"]] or ["- нет"]
    lines += ["", "Рейтинги взяты из EA FIFA 23 и являются приближением реального уровня игроков."]
    return "\n".join(lines)


def llm_report(facts: dict) -> str:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return template_report(facts)
    try:
        import anthropic
        client = anthropic.Anthropic()
        response = client.beta.messages.create(
            model=config.LLM_MODEL,
            max_tokens=4000,
            system=SYSTEM,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": json.dumps(facts, ensure_ascii=False, default=float)}],
        )
        if response.stop_reason == "refusal":
            return template_report(facts)
        text = "".join(b.text for b in response.content if b.type == "text")
        return text or template_report(facts)
    except Exception as exc:
        print(f"[llm] falling back to template: {exc}")
        return template_report(facts)
