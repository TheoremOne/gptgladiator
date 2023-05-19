import openai
import tiktoken
from gladiator.GPTModel import GptModel

class ChatBot:
    def __init__(self, model: GptModel, temperature=1, messages=[]):
        self.model = model
        self.messages = messages
        self.temperature = temperature


    def get_completion(self, prompt):
        self.messages.append({"role": "user", "content": prompt})

        current_tokens_used = self.count_total_tokens_in_messages(self.messages)
        response_tokens = self.model.tokens - current_tokens_used

        print(f"Token limit: {self.model.tokens}")
        print(f"Send Token Count: {current_tokens_used}")
        print(f"Tokens remaining for response: {response_tokens}")

        if response_tokens < 1000:
            raise ValueError(f"Too many tokens in the input. Max is {self.model.tokens} and you entered {current_tokens_used}. You must reserve 1000 tokens for the response yet you only have {response_tokens}. Remove content from your input and retry.")
        
        try:
            response = openai.ChatCompletion.create(
                model=self.model.name,
                temperature=self.temperature,
                messages=self.messages
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print("Error in chatbot: ", e)    


    def count_total_tokens_in_messages(self, messages) -> int:
        return sum(self.num_tokens_from_string(message) for message in messages)


    def num_tokens_from_string(self, string: str) -> int:
        encoding = tiktoken.encoding_for_model(self.model.name)
        num_tokens = len(encoding.encode(str(string)))
        return num_tokens

