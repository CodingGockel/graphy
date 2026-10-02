import pytest

from src.util.think_splitter import ThinkSplitter, split_think


def _split(deltas: list[str]) -> tuple[str, str]:
    """Feed the deltas and return the collected `(thinking, answer)` text."""
    splitter = ThinkSplitter()
    parts = [part for delta in deltas for part in splitter.feed(delta)] + splitter.flush()
    thinking = "".join(text for kind, text in parts if kind == "thinking")
    answer = "".join(text for kind, text in parts if kind == "answer")
    return thinking, answer


class TestThinkSplitter:
    def test_text_without_a_block_is_answer(self):
        splitter = ThinkSplitter()
        assert splitter.feed("Hello ") == [("answer", "Hello ")]
        assert splitter.feed("world") == [("answer", "world")]
        assert splitter.flush() == []

    def test_one_block(self):
        splitter = ThinkSplitter()
        assert splitter.feed("<think>let me see</think>The answer") == [
            ("thinking", "let me see"),
            ("answer", "The answer"),
        ]

    def test_block_over_several_deltas(self):
        assert _split(["<think>let ", "me see", "</think>The ", "answer"]) == (
            "let me see", "The answer",
        )

    def test_several_blocks(self):
        assert _split(["a<think>1</think>b<think>2</think>c"]) == ("12", "abc")

    @pytest.mark.parametrize("cut", range(1, len("<think>reasoning</think>answer")))
    def test_tag_split_across_deltas_at_every_position(self, cut):
        text = "<think>reasoning</think>answer"
        assert _split([text[:cut], text[cut:]]) == ("reasoning", "answer")

    def test_one_character_per_delta(self):
        assert _split(list("x<think>a<b</think>y < z")) == ("a<b", "xy < z")

    def test_incomplete_tag_is_held_back_until_it_is_decided(self):
        splitter = ThinkSplitter()
        assert splitter.feed("a <thi") == [("answer", "a ")]
        # not a tag after all
        assert splitter.feed("s") == [("answer", "<this")]

    def test_unterminated_block_stays_thinking(self):
        assert _split(["<think>cut ", "off"]) == ("cut off", "")

    def test_flush_releases_held_back_text(self):
        splitter = ThinkSplitter()
        assert splitter.feed("1 <") == [("answer", "1 ")]
        assert splitter.flush() == [("answer", "<")]
        assert splitter.flush() == []

    def test_flush_inside_a_block_is_thinking(self):
        splitter = ThinkSplitter()
        splitter.feed("<think>a</thi")
        assert splitter.flush() == [("thinking", "</thi")]

    def test_lone_closing_tag_is_not_handled(self):
        # The text before it has already gone out as answer; split_think fixes it up.
        assert _split(["reasoning", "</think>answer"]) == ("", "reasoning</think>answer")


class TestSplitThink:
    def test_no_block(self):
        assert split_think(" just text ") == (None, "just text")

    def test_one_block(self):
        assert split_think("<think> why </think>\n\nThe answer.") == ("why", "The answer.")

    def test_several_blocks_are_joined(self):
        assert split_think("<think>a</think>x<think>b</think>y") == ("a\n\nb", "xy")

    def test_unclosed_block(self):
        assert split_think("answer<think>cut off") == ("cut off", "answer")

    def test_lone_closing_tag(self):
        assert split_think("reasoning\n</think>\nThe answer.") == ("reasoning", "The answer.")

    def test_lone_closing_tag_followed_by_a_block(self):
        assert split_think("a</think>x<think>b</think>y") == ("a\n\nb", "xy")

    def test_empty_block_is_no_thinking(self):
        assert split_think("<think>  </think>answer") == (None, "answer")
