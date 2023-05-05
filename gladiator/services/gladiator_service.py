import concurrent.futures
import os
import random
from distutils.util import strtobool
from typing import List, Optional, Any, Iterator

import openai as openai

from gladiator.helpers import mock_replies, grading_prompt, mock_grading_response, save_reply, parse_json, \
    num_tokens_from_string
from gladiator.models.gpt_model import GptModel
from gladiator.models.reply import Reply
from gladiator.services.gladiator_interface import GladiatorInterface


class GladiatorService(GladiatorInterface):
    debug = strtobool(os.environ.get('DEBUG', 'False'))
    mock_api = strtobool(os.environ.get('MOCK_API', 'False'))

    def __init__(self):
        openai.api_key = os.environ.get('OPENAI_API_KEY')
        self.chat_completion_model = GptModel('gpt-4', 2048)
        self.completion_model = GptModel('text-davinci-003', 4097)
        self.n = 3

    def run(self, prompt: str) -> (bool, str, List[Reply]):
        # TODO: Enrich the prompt a bit?
        user_question = f"""{prompt}"""

        # create the context to use the chat completion with follow-up prompts
        messages = [
            {"role": "system",
             "content": "You are a helpful assistant who can grade answers to questions very effectively."},
            {"role": "user", "content": user_question}]

        replies, err = self._get_answers(self.n, user_question, messages)
        if err:
            return False, err, []

        # Ask the model to rate each response
        err = self._grade_answers(messages, replies)
        if err:
            return False, err, replies.values()

        return True, '', replies.values()

    def _call_api_concurrently(self, user_question: List[str], max_active_tasks: int) -> Iterator[Any]:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_active_tasks) as executor:
            results = executor.map(self._call_completion_api, user_question)
        return results

    def _get_answers(self, n: int, user_question: str, messages: List) -> (List[Reply], str):
        replies = {}
        if self.mock_api:
            for i in range(n):
                reply_text, err = mock_replies[i]["choices"][0]["text"], None
                if err:
                    return [], err
                save_reply(i, reply_text, messages, replies)
        else:
            for i, (reply_text, err) in enumerate(self._call_api_concurrently([user_question] * n, n)):
                if err:
                    return [], err
                save_reply(i, reply_text, messages, replies)

        return replies, None

    def _grade_answers(self, messages, replies: dict[int, Reply]) -> Optional[str]:
        """
        Grades the given answers
        :param messages: the messages on the chat completion context
        :param replies: the replies to grade
        :return: An error if something fails or None if request was successful
        """

        if self.mock_api:
            json_response = parse_json(mock_grading_response)
            for _, r in enumerate(json_response):
                key = r["idx"]
                if key not in replies:
                    continue
                replies[key].confidence = random.randint(1, 100)
                replies[key].explanation = r["exp"]
        else:
            messages.append({"role": "user", "content": grading_prompt})
            response, err = self._call_chat_completion_api(messages)
            if err:
                print(err)
                return "Replies could not be rated"

            json_response = parse_json(response)
            for _, r in enumerate(json_response):
                replies[r["idx"]].confidence = r["sc"]
                replies[r["idx"]].explanation = r["exp"]

        return None

    def _call_completion_api(self, prompt) -> (str, Optional[Exception]):
        """
        Calls the Completion API and returns the text response
        :param prompt:
        :return: a tuple (response, error)
        """

        current_tokens_used = num_tokens_from_string(prompt, self.completion_model.name)
        response_tokens = self.completion_model.tokens - current_tokens_used

        if self.debug:
            print('------------ CALLING COMPLETION API -------------')
            print(f'Token limit: {self.completion_model.tokens}')
            print(f'Send Token Count: {current_tokens_used}')
            print(f'Tokens remaining for response: {response_tokens}')
            print('------------ CONTEXT SENT TO AI ---------------')

        try:
            request = {
                "model": self.completion_model.name,
                "temperature": 1,
                "max_tokens": response_tokens,
                "prompt": prompt,
            }
            response = openai.Completion.create(**request)
            result = response.choices[0].text.strip()
            if self.debug:
                print('--------------- REPLY FROM OPEN AI API ----------')
                print(f'{result}')
            return result, None
        except Exception as e:
            print('Error: ', e)
            return '', e

    def _call_chat_completion_api(self, messages) -> (str, Optional[Exception]):
        """
        Calls the ChatCompletion API and populates the messages on the chat context
        :param messages: the messages on the chat completion context
        :return: A tuple (response, error)
        """

        current_tokens_used = self._count_total_tokens_in_messages(messages)
        response_tokens = self.completion_model.tokens - current_tokens_used

        if self.debug:
            print(f'Token limit: {self.completion_model.tokens}')
            print(f'Send Token Count: {current_tokens_used}')
            print(f'Tokens remaining for response: {response_tokens}')
            print('------------ CONTEXT SENT TO AI ---------------')

        try:
            request = {
                "model": self.chat_completion_model.name,
                "temperature": 1,
                "max_tokens": self.chat_completion_model.tokens,
                "messages": messages
            }
            response = openai.ChatCompletion.create(**request)
            result = response.choices[0].message.content.strip("")
            messages.append({'role': 'assistant', 'content': response})
            if self.debug:
                print('--------------- REPLY FROM OPEN AI API ----------')
                print(result)
            return result, None
        except Exception as e:
            print('Error: ', e)
            return None, e

    def _count_total_tokens_in_messages(self, messages) -> int:
        num_tokens = 0
        for message in messages:
            num_tokens += num_tokens_from_string(message['content'], self.chat_completion_model.name)
        return num_tokens
