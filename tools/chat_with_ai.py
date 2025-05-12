import os
import logfire
import openai
import cohere


from dotenv import load_dotenv

env_file = ".env.production" if os.getenv("ENV") == "production" else ".env"
load_dotenv(env_file)

logfire.configure(token=os.getenv("LOGFIRE_TOKEN"))

# Set your API keys via environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # for GPT-4 / DeepSeek
CO_API_KEY = os.getenv("CO_API_KEY")  # for Cohere (Command-R+)

# Configure OpenAI client (for both GPT-4 and DeepSeek)
openai.api_key = OPENAI_API_KEY

# Configure Cohere client
co = cohere.Client(CO_API_KEY)


def chat_with_openai(prompt: str, model="gpt-4") -> str:
    response = openai.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    return response.choices[0].message.content.strip()


def chat_with_openai_4o(prompt: str) -> str:
    return chat_with_openai(prompt, model="gpt-4o")


def chat_with_openai_4o_mini(prompt: str) -> str:
    return chat_with_openai(prompt, model="gpt-4o-mini")


def chat_with_openai_41_nano(prompt: str) -> str:
    return chat_with_openai(prompt, model="gpt-4.1-nano")


def chat_with_openai_o1(prompt: str) -> str:
    response = openai.chat.completions.create(
        model="o1", messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()


def chat_with_openai_3_5(prompt: str) -> str:
    return chat_with_openai(prompt, model="gpt-3.5-turbo")


def chat_with_deepseek(prompt: str, model="deepseek-chat") -> str:
    response = openai.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    return response.choices[0].message.content.strip()


def chat_with_command_r_plus(prompt: str) -> str:
    response = co.chat(
        model="command-r-plus",
        message=prompt,
        temperature=0.1,
    )
    return response.text.strip()


def chat_with_grok(prompt: str, model="llama3-8b-8192") -> str:
    client = openai.OpenAI(
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
    )

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    content = response.choices[0].message.content.strip()

    log_data = {
        "model": model,
        "completion_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
        "prompt": prompt,
        "response": content,
        "tags": {
            "total_tokens": response.usage.total_tokens
        },  # Add token count as a tag
    }

    # Format the msg_template manually
    msg_template = (
        f"Model: {log_data['model']}, Tokens: {log_data['total_tokens']}, Prompt: {log_data['prompt']}, "
        f"Response: {log_data['response']}"
    )

    # Log the event
    logfire.log(log_data, msg_template=msg_template)

    return content
