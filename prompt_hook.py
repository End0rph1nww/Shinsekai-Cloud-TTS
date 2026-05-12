from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from llm.template_generator import TemplateGenerator

from plugins.minimax_tts import state


_ORIGINAL_ATTR = "_minimax_tts_original_generate_chat_template"
_HOOK_ATTR = "_minimax_tts_prompt_hook"


def install() -> None:
    current = TemplateGenerator.generate_chat_template
    if getattr(current, _HOOK_ATTR, False):
        return

    @wraps(current)
    def wrapped(self: TemplateGenerator, *args: Any, **kwargs: Any) -> tuple[str, str]:
        template, out = current(self, *args, **kwargs)
        try:
            if state.prompt_constraint_active():
                template = state.add_prompt_constraint_text(template)
        except Exception:
            return template, out
        return template, out

    setattr(wrapped, _HOOK_ATTR, True)
    setattr(wrapped, _ORIGINAL_ATTR, current)
    TemplateGenerator.generate_chat_template = wrapped


def uninstall() -> None:
    current = TemplateGenerator.generate_chat_template
    original: Callable[..., tuple[str, str]] | None = getattr(
        current, _ORIGINAL_ATTR, None
    )
    if original is not None:
        TemplateGenerator.generate_chat_template = original
