import subprocess
import tomllib
import os

from groq import Groq
from InquirerPy import prompt

# load the config file
config = tomllib.loads(open("config.toml").read())

GROQ_API_KEY = config[config["use"]]["api_key"]
GROQ_MODEL = config[config["use"]]["model"]
SYSTEM_PROMPT = config[config["use"]]["system_prompt"]


def get_staged_diff():
    try:
        result = subprocess.run(
            ["git", "diff", "--staged"], capture_output=True, text=True
        )

        if result.returncode != 0:
            print(
                "Error: Could not get the diff. Make sure you're in a git repository and have staged changes."
            )
            print(result.stderr)
        else:
            if result.stdout:
                filtered_diff = []
                for line in result.stdout.splitlines():
                    if not any(
                        filter_word in line
                        for filter_word in [
                            "image/png",
                            "output",
                            "traceback",
                            "evalue",
                            "ename",
                        ]
                    ):
                        filtered_diff.append(line)
                return "\n".join(filtered_diff)
            else:
                print("No changes staged for commit.")
    except Exception as e:
        print(f"An error occurred: {e}")


def get_responses(diff: str) -> list[str]:
    responses = []
    client = Groq(api_key=GROQ_API_KEY)
    for _ in range(3):
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {"role": "user", "content": str(diff)},
            ],
            temperature=1,
            max_tokens=512,
            top_p=1,
            stream=False,
            stop=None,
        )

        response = completion.choices[0].message.content
        try:
            response = eval(str(response))
        except Exception as e:
            print(response)
            break
        responses.append(response["message"])

    return responses


def main():
    diff = get_staged_diff()
    responses = get_responses(diff)
    responses = None
    if responses:
        print("Responses:")
        choices = responses

        questions = [
            {
                "type": "list",
                "message": "Please select an option:",
                "choices": choices,
                "name": "option",
            }
        ]

        result = prompt(questions)

        # git commit -m "Your commit message"
        subprocess.run(["git", "commit", "-m", str(result["option"])])
        print("Committed successfully.")


if __name__ == "__main__":
    main()
