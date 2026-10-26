import unittest

from pydantic import ValidationError

from app.api_models import AgentRunRequest, ChatStreamRequest, SearchRequest


class SearchRequestTests(unittest.TestCase):
    def test_strips_query_whitespace(self) -> None:
        request = SearchRequest(query="  search terms  ")

        self.assertEqual(request.query, "search terms")

    def test_rejects_blank_query(self) -> None:
        with self.assertRaises(ValidationError):
            SearchRequest(query="   ")

    def test_rejects_top_k_outside_supported_range(self) -> None:
        with self.assertRaises(ValidationError):
            SearchRequest(query="search terms", top_k=0)


class AgentRunRequestTests(unittest.TestCase):
    def test_strips_prompt_whitespace(self) -> None:
        request = AgentRunRequest(prompt="  run a skill  ")

        self.assertEqual(request.prompt, "run a skill")

    def test_rejects_blank_prompt(self) -> None:
        with self.assertRaises(ValidationError):
            AgentRunRequest(prompt="   ")


class ChatStreamRequestTests(unittest.TestCase):
    def test_strips_prompt_and_model(self) -> None:
        request = ChatStreamRequest(
            prompt="  Explain streaming.  ",
            provider="openai_compatible",
            model="  gpt-4o-mini  ",
        )

        self.assertEqual(request.prompt, "Explain streaming.")
        self.assertEqual(request.model, "gpt-4o-mini")

    def test_rejects_blank_prompt_or_model(self) -> None:
        with self.assertRaises(ValidationError):
            ChatStreamRequest(prompt="  ")
        with self.assertRaises(ValidationError):
            ChatStreamRequest(prompt="Hello", model="  ")


if __name__ == "__main__":
    unittest.main()
