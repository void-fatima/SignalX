from app.agents.contracts import TargetMessage, RunConfig


def select_context(target: TargetMessage, messages: list[TargetMessage], config: RunConfig) -> list[TargetMessage]:
    ordered = sorted([m for m in messages if m.conversation_id == target.conversation_id], key=lambda m: (m.timestamp, m.external_id))
    index = next(i for i, m in enumerate(ordered) if m.id == target.id)
    before = list(reversed(ordered[max(0, index - 3):index]))
    after = ordered[index + 1:index + 3] if config.offline_context else []
    parents = [m for m in ordered if m.external_id == target.reply_to_external_id and m.id != target.id
               and (config.offline_context or (m.timestamp, m.external_id) < (target.timestamp, target.external_id))]
    selected, size = [], 0
    for m in parents + before + after:
        if m.id in {x.id for x in selected}:
            continue
        if len(selected) < 5 and size + len(m.content) <= config.context_max_chars:
            selected.append(m)
            size += len(m.content)
    return sorted(selected, key=lambda m: (m.timestamp, m.external_id))
