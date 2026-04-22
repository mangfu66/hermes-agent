from prompt_toolkit.document import Document

from hermes_cli.commands import SlashCommandCompleter


def _texts(text: str) -> list[str]:
    completer = SlashCommandCompleter(skill_commands_provider=lambda: {})
    doc = Document(text, len(text))
    return [c.text for c in completer.get_completions(doc, None)]


def test_bare_model_with_trailing_space_does_not_offer_alias_completions():
    assert _texts('/model ') == []


def test_model_argument_completion_starts_after_first_character():
    texts = _texts('/model g')
    assert texts
    assert any(t.startswith('g') for t in texts)
